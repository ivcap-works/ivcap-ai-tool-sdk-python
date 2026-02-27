
from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

from fastapi import HTTPException

# Global registry of readiness handlers (sync or async callables returning bool)
_ready_handlers: list[Callable[[], bool | Awaitable[bool]]] = []


def add_ready_handler(ready_fn: Callable[[], bool | Awaitable[bool]] | None) -> None:
    """
    Register a readiness handler in the global list. Called from builder when
    a tool is registered with opts.is_ready set.
    """
    if ready_fn is not None:
        _ready_handlers.append(ready_fn)


async def healtz_handler() -> dict:
    """
    Check all registered readiness handlers.

    - If there are no handlers, or all handlers report ready, return
      {"version": os.environ.get("VERSION", "???")}.
    - If any handler reports not-ready, raise a 503 Service Unavailable.
    """

    # No handlers registered -> consider service ready
    if not _ready_handlers:
        return {"version": os.environ.get("VERSION", "???")}

    for handler in _ready_handlers:
        result = handler()
        if asyncio.iscoroutine(result):
            result = await result

        if not result:
            # At least one handler reports not-ready
            raise HTTPException(status_code=503, detail="Service Unavailable")

    return {"version": os.environ.get("VERSION", "???")}
