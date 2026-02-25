
from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable, List, Optional

from fastapi import HTTPException

from .builder import ToolOptions

# Global registry of readiness handlers
_ready_handlers: List[Callable[[], Awaitable[bool]]] = []


def add_ready_handler(opts: Optional[ToolOptions]) -> None:
    """
    Register the given ToolOptions.is_ready handler (if any) in the global list.
    """
    if opts is not None and opts.is_ready is not None:
        _ready_handlers.append(opts.is_ready)


async def healthz_handler() -> dict:
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
