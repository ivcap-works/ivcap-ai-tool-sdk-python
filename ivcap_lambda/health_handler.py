from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .utils import find_first

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


async def healtz_handler() -> dict:
    """
    Check all registered readiness handlers.

    - Dict results are merged into the reply. `version` always wins over a
      key of the same name.
    - If every handler is ready (True, a dict, or no handlers at all), return
      {"version": ..., **extra_info}.
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

    return {**info, "version": os.environ.get("VERSION", "???")}


def add_health_route(app: FastAPI) -> None:
    """
    Register `GET /_healtz` backed by `healtz_handler`, unless the app already
    serves that path.
    """
    if find_first(app.routes, lambda r: r.path == "/_healtz") is None:
        app.add_api_route("/_healtz", healtz_handler, methods=["GET"], tags=["System"])
