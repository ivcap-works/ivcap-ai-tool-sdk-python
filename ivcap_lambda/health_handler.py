from __future__ import annotations

import asyncio
import inspect
import math
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from ivcap_service import get_version as get_service_version
from ivcap_service import getLogger
from pydantic import BaseModel

from .utils import find_first
from .version import get_version, resolve_service_version

logger = getLogger("health")

# Service-level gates. Each returns True when the whole service is ready. They
# are registered by `start_lambda_server(on_startup=...)` and gate `/_healtz`.
ReadyFn = Callable[[], bool | Awaitable[bool]]
_ready_handlers: list[ReadyFn] = []

# Functions marked with `@ivcap_health_info`. Each returns a dict or pydantic
# model whose entries are merged into the `/_healtz` reply.
InfoResult = dict[str, Any] | BaseModel
InfoFn = Callable[[], InfoResult | Awaitable[InfoResult]]
_health_info: list[InfoFn] = []


class NotReadyYet(Exception):
    """Raised by a readiness check to report that it is not ready yet.

    Args:
        retry_after: optional expected time in seconds until ready. Sent as the
            `Retry-After` header on the 503 response, rounded up to whole seconds.
    """

    def __init__(self, retry_after: float | None = None):
        super().__init__("Not ready yet")
        self.retry_after = retry_after


def add_ready_handler(ready_fn: ReadyFn | None) -> None:
    """Register a service-level readiness gate that `/_healtz` evaluates."""
    if ready_fn is not None:
        _ready_handlers.append(ready_fn)


class StartupState:
    """Status of the `on_startup` hook, reported in the `/_healtz` 503 body.

    `status` is one of "loading", "ready" or "failed". After a failure, `error`
    holds the exception type and message (the full traceback is only logged).
    """

    def __init__(self) -> None:
        self.status = "loading"
        self.error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status}
        if self.error is not None:
            out["error"] = self.error
        return out


startup_state = StartupState()


def describe_error(ex: BaseException) -> str:
    """Short, non-sensitive description of an exception: its type and message."""
    message = str(ex).strip()
    return f"{type(ex).__name__}: {message}" if message else type(ex).__name__


def ivcap_health_info(fn: InfoFn) -> InfoFn:
    """Mark a function whose dict or pydantic model is added to the `/_healtz` reply.

    The function is called on each `GET /_healtz` once the service is ready. Its
    entries are merged with those of other marked functions, later ones winning.
    `name`, `version` and `libraries` always take precedence. If the function
    raises, the error is logged and its entries are left out; the reply is still 200.
    """
    if fn not in _health_info:
        _health_info.append(fn)
    return fn


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def check_tool_ready(is_ready: Callable[[], Any] | None) -> None:
    """Raise NotReadyYet unless a per-tool `is_ready` check reports ready.

    A check returning False, or raising NotReadyYet, means not ready. Any other
    exception propagates. The check is called on the event loop, so keep it cheap.
    """
    if is_ready is None:
        return
    if not await _resolve(is_ready()):
        raise NotReadyYet()


def not_ready_http_error(retry_after: float | None = None) -> HTTPException:
    """Build the 503 response for a not-ready tool or service."""
    headers = None
    if retry_after is not None:
        headers = {"Retry-After": str(max(0, math.ceil(retry_after)))}
    return HTTPException(status_code=503, detail="Service Unavailable", headers=headers)


def service_not_ready_response(retry_after: float | None = None) -> JSONResponse:
    """503 for the whole service, with a flat JSON body that includes the `on_startup` status."""
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(max(0, math.ceil(retry_after)))
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Service Unavailable",
            "startup": startup_state.as_dict(),
        },
        headers=headers or None,
    )


async def _call_info(fn: InfoFn) -> Any:
    if inspect.iscoroutinefunction(fn):
        return await fn()
    # sync functions may block (e.g. probing a model); keep the event loop free
    return await asyncio.to_thread(fn)


def _library_versions() -> dict[str, str]:
    return {
        "ivcap-lambda": get_version(),
        "ivcap-service": get_service_version(),
    }


async def healtz_handler(
    name: str | None = None, version: str | None = None
) -> dict | JSONResponse:
    """
    Build the `/_healtz` reply.

    - Service-level gates are evaluated first. If any returns False or raises
      NotReadyYet, a 503 JSON response is returned (with the `on_startup` status)
      and no info is gathered. The largest `retry_after` becomes `Retry-After`.
    - Otherwise the results of `@ivcap_health_info` functions are merged in.
    - `name` (when given), `version` and `libraries` always win over info keys.
    """
    retry_after: float | None = None
    not_ready = False

    for gate in _ready_handlers:
        try:
            ready = await _resolve(gate())
        except NotReadyYet as ex:
            ready = False
            if ex.retry_after is not None:
                retry_after = max(retry_after or 0.0, ex.retry_after)
        if not ready:
            not_ready = True

    if not_ready:
        return service_not_ready_response(retry_after)

    info: dict[str, Any] = {}
    for fn in _health_info:
        try:
            result = await _call_info(fn)
        except Exception:
            logger.exception(
                "health info %s failed - leaving it out of /_healtz", fn.__name__
            )
            continue
        if isinstance(result, BaseModel):
            result = result.model_dump(by_alias=True)
        if not isinstance(result, dict):
            logger.warning(
                "health info %s did not return a dict or model - ignored", fn.__name__
            )
            continue
        info.update(result)

    identity: dict[str, Any] = {}
    if name is not None:
        identity["name"] = name
    identity["version"] = resolve_service_version(version)
    identity["libraries"] = _library_versions()
    return {**info, **identity}


def add_health_route(
    app: FastAPI, *, name: str | None = None, version: str | None = None
) -> None:
    """
    Register `GET /_healtz` backed by `healtz_handler`, unless the app already
    serves that path.

    Args:
        app: the FastAPI app to add the route to.
        name: service name to report in the reply.
        version: declared service version. The VERSION env var takes precedence
            when set.
    """
    if find_first(app.routes, lambda r: r.path == "/_healtz") is None:

        async def _healtz() -> Any:
            # a JSONResponse (not ready) is returned as-is; otherwise the dict
            return await healtz_handler(name=name, version=version)

        app.add_api_route("/_healtz", _healtz, methods=["GET"], tags=["System"])
