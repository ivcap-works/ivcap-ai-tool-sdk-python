from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .utils import find_first
from .version import resolve_service_version

# A readiness check returns True (ready), False (legacy not-ready), a dict or a
# pydantic model of extra info to add to the health reply (ready). Raising
# NotReadyYet also means not-ready. Sync or async.
ReadyResult = bool | dict[str, Any] | BaseModel
ReadyFn = Callable[[], ReadyResult | Awaitable[ReadyResult]]

# Global registry of readiness handlers
_ready_handlers: list[ReadyFn] = []


class NotReadyYet(Exception):
    """Raised by an `is_ready` callback when the tool is not ready yet.

    Args:
        retry_after: optional expected time in seconds until the tool is ready.
            Reported to callers as the `Retry-After` header on `/_healtz`.
    """

    def __init__(self, retry_after: float | None = None):
        super().__init__("Not ready yet")
        self.retry_after = retry_after


def add_ready_handler(ready_fn: ReadyFn | None) -> None:
    """
    Register a readiness handler in the global list. Called from builder when
    a tool is registered with opts.is_ready set.
    """
    if ready_fn is not None:
        _ready_handlers.append(ready_fn)


async def healtz_handler(name: str | None = None, version: str | None = None) -> dict:
    """
    Check all registered readiness handlers.

    - Dict results are merged into the reply. `name` and `version` always win
      over a key of the same name.
    - `version` is the VERSION env var if set, otherwise the declared service
      version, otherwise "???". `name` is only reported when given.
    - If every handler is ready (True, a dict, or no handlers at all), return
      {**extra_info, "name": ..., "version": ...}.
    - If any handler returns False or raises NotReadyYet, raise a 503. When
      NotReadyYet carries retry_after, the largest value is sent as the
      `Retry-After` header in whole seconds (rounded up).
    """
    info: dict[str, Any] = {}
    not_ready = False
    retry_after: float | None = None

    for handler in _ready_handlers:
        try:
            result: Any = handler()
            if asyncio.iscoroutine(result):
                result = await result
        except NotReadyYet as ex:
            not_ready = True
            if ex.retry_after is not None:
                retry_after = max(retry_after or 0.0, ex.retry_after)
            continue

        if isinstance(result, BaseModel):
            result = result.model_dump(by_alias=True)

        if isinstance(result, dict):
            info.update(result)
        elif not result:
            not_ready = True

    if not_ready:
        headers = None
        if retry_after is not None:
            headers = {"Retry-After": str(max(0, math.ceil(retry_after)))}
        raise HTTPException(
            status_code=503, detail="Service Unavailable", headers=headers
        )

    identity: dict[str, Any] = {}
    if name is not None:
        identity["name"] = name
    identity["version"] = resolve_service_version(version)
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

        async def _healtz() -> dict:
            return await healtz_handler(name=name, version=version)

        app.add_api_route("/_healtz", _healtz, methods=["GET"], tags=["System"])
