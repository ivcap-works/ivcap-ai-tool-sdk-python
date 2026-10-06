#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Model Context Protocol (MCP) support for ivcap-lambda.

Exposes every tool registered via `@ivcap_lambda(...)` as a spec-compliant MCP
server (Streamable HTTP transport), built on top of the official `mcp` Python
SDK (https://github.com/modelcontextprotocol/python-sdk).

Each registered tool is re-registered, unchanged, as an MCP tool: the same
Pydantic request/result models and docstring used for the REST endpoint are
reused to build the MCP tool's input/output schema and description. Progress
reported via `jobCtxt.report.step(...)` (the `EventReporter` API) is bridged
to native MCP `notifications/progress` messages when a tool is invoked over
MCP - no changes are required in tool code.

Requires the optional `mcp` package: `pip install ivcap-lambda[mcp]`.
"""

# NOTE: intentionally no `from __future__ import annotations` here. Tool
# wrappers are built dynamically with a *local variable* (`input_model`) as a
# parameter annotation (see `_make_mcp_tool`); the MCP SDK resolves string
# annotations via `typing.get_type_hints()`/`eval_str=True` against the
# function's `__globals__`, which would fail to find a local variable name.

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from ivcap_service import (
    EventReporter,
    ExecutionError,
    IvcapResult,
    get_function_return_type,
    getLogger,
)
from pydantic import BaseModel
from uuid6 import uuid6

from .builder import ToolDescription, tools

logger = getLogger("mcp")

try:
    from mcp.server.mcpserver import Context, MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.server.transport_security import TransportSecuritySettings

    _MCP_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when extra isn't installed
    _MCP_SDK_AVAILABLE = False

# Max. time to wait for a tool invoked over MCP to complete. MCP's base
# `tools/call` is a single request/response round-trip (progress is streamed
# as notifications on the same call, not a separate poll), so - unlike the
# REST "try-later" protocol - there is no fallback to defer the result.
MCP_CALL_TIMEOUT = 600.0


class _MCPRequestShim:
    """Minimal stand-in for `fastapi.Request` used when invoking a tool's
    `Executor` from within an MCP tool call.

    `Executor.execute()` only ever calls `req.headers.get(...)`, so a plain
    object carrying a header mapping is sufficient here; it avoids requiring a
    real `starlette.requests.Request` (MCP clients speak a different
    transport/protocol than IVCAP's REST job submission, so there is no
    equivalent "job-id"/"authorization" header convention to rely on beyond
    whatever the MCP transport happened to carry).
    """

    def __init__(self, headers: dict[str, str] | None):
        self.headers: dict[str, str] = headers or {}


def _event_message(event) -> str:
    """Best-effort extraction of a human-readable message from an
    `ivcap_service.events.BaseEvent` for forwarding as an MCP progress
    notification's `message`."""
    options = getattr(event, "options", None)
    if options and options.get("message"):
        return str(options["message"])
    error = getattr(event, "error", None)
    if error:
        return str(error)
    name = getattr(event, "name", None)
    return str(name) if name else event.__class__.__name__


def _log_progress_delivery_error(future) -> None:
    try:
        future.result()
    except Exception as ex:  # pragma: no cover - best-effort logging only
        logger.debug(f"failed to deliver MCP progress notification - {ex}")


class McpEventReporter(EventReporter):
    """Bridges `jobCtxt.report` calls (the `EventReporter` API used by tool
    code) to native MCP `notifications/progress` messages, so that a tool
    written against `jobCtxt.report.step(...)` gets progress reporting
    whether it is invoked over REST (sidecar events) or MCP - with no changes
    required in tool code.

    `EventReporter` methods are synchronous and are invoked from the
    `Executor`'s worker thread, while MCP's `ctx.report_progress()` is a
    coroutine that must run on the event loop owning the MCP session. This
    reporter schedules it there via `asyncio.run_coroutine_threadsafe()`,
    best-effort: a failure to deliver a progress notification never breaks
    the tool call itself.
    """

    def __init__(
        self,
        job_id: str,
        job_authorization: str | None,
        ctx: "Context",
        loop: asyncio.AbstractEventLoop,
    ):
        super().__init__(job_id, job_authorization)
        self._ctx = ctx
        self._loop = loop
        self._progress = 0.0

    def _send(self, event) -> None:
        # Always log locally too (matches the base EventReporter's behaviour).
        super()._send(event)
        try:
            self._progress += 1.0
            message = _event_message(event)
            future = asyncio.run_coroutine_threadsafe(
                self._ctx.report_progress(self._progress, message=message),
                self._loop,
            )
            future.add_done_callback(_log_progress_delivery_error)
        except Exception as ex:  # pragma: no cover - defensive, must not raise
            logger.debug(f"{self.job_id}: failed to forward event to MCP - {ex}")


def _make_mcp_tool(td: ToolDescription):
    """Builds an async function suitable for `MCPServer.add_tool()` that
    delegates to the same `Executor` (and hence the same worker-thread pool,
    job cache, and OTEL instrumentation) used by `td`'s REST endpoint.

    The wrapper's signature is `(req: <input_model>, ctx: Context) ->
    <output_model | Any>` - the exact same shape `@ivcap_lambda` already
    expects from tool functions - so the MCP SDK derives the tool's input and
    output JSON schemas from the very same Pydantic models used for the REST
    `POST`/`GET` endpoints.
    """
    input_model, _ = td.input
    if input_model is None:
        raise ValueError(
            f"cannot expose tool '{td.name}' over MCP: it has no Pydantic "
            "input model (first argument must be a `pydantic.BaseModel`)"
        )
    output_model = get_function_return_type(td.worker_fn)

    async def _tool(req: input_model, ctx: Context):  # type: ignore[valid-type]
        job_id = f"mcp:{uuid6()}"
        headers = dict(ctx.headers) if ctx.headers else {}
        shim_req = _MCPRequestShim(headers)
        loop = asyncio.get_running_loop()
        authorization = headers.get("authorization")
        reporter = McpEventReporter(job_id, authorization, ctx, loop)

        queue = await td.executor.execute(
            req,
            job_id,
            shim_req,  # type: ignore[arg-type]
            report_result=False,
            reporter=reporter,
        )
        try:
            result = await asyncio.wait_for(queue.get(), timeout=MCP_CALL_TIMEOUT)
            queue.task_done()
        except TimeoutError as ex:
            raise ToolError(
                f"tool '{td.name}' did not complete within "
                f"{MCP_CALL_TIMEOUT:.0f} seconds"
            ) from ex

        if isinstance(result, ExecutionError):
            raise ToolError(result.error)
        if isinstance(result, IvcapResult):
            if isinstance(result.raw, BaseModel):
                return result.raw
            return result.content
        return result

    _tool.__name__ = td.worker_fn.__name__
    _tool.__doc__ = td.worker_fn.__doc__
    if output_model is not None:
        _tool.__annotations__["return"] = output_model
    return _tool


def _require_mcp_sdk() -> None:
    if not _MCP_SDK_AVAILABLE:
        raise ImportError(
            "MCP support requires the optional 'mcp' package. Install it with "
            "`pip install ivcap-lambda[mcp]` (or `poetry add ivcap-lambda -E mcp`)."
        )


def _build_mcp_server(name: str, version: str = "") -> "MCPServer":
    """Build an `MCPServer` registering every tool from `@ivcap_lambda(...)`,
    shared by both the HTTP (`register_mcp`) and stdio (`run_mcp_stdio`)
    entry points so tool registration logic lives in exactly one place.
    """
    _require_mcp_sdk()

    mcp_server = MCPServer(name or "ivcap-lambda", version=version or "")
    for td in tools:
        mcp_server.add_tool(
            _make_mcp_tool(td),
            name=td.name,
            description=td.worker_fn.__doc__,
        )
    return mcp_server


def register_mcp(app: FastAPI, path_prefix: str = "/mcp") -> "MCPServer":
    """Build an MCP server from every tool registered via `@ivcap_lambda(...)`
    and mount it onto `app` at `path_prefix` (Streamable HTTP transport).

    Requires the optional `mcp` package: `pip install ivcap-lambda[mcp]`.

    Args:
        app (FastAPI): The FastAPI app to mount the MCP server on.
        path_prefix (str): The path to mount the MCP endpoint at. Defaults to "/mcp".

    Returns:
        The underlying `mcp.server.mcpserver.MCPServer` instance, e.g. for use
        with `mcp.Client(mcp_server)` in tests (no network required).
    """
    mcp_server = _build_mcp_server(app.title, app.version)

    mcp_asgi_app = mcp_server.streamable_http_app(
        streamable_http_path=path_prefix,
        # The service is typically deployed behind an IVCAP ingress/proxy under
        # an arbitrary hostname, not `localhost`; the default DNS-rebinding
        # protection would otherwise reject every request with a 421.
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )
    # Mount at the application root ("") rather than at `path_prefix` itself:
    # `mcp_asgi_app` already serves its one route at `streamable_http_path`, so
    # mounting it again under `path_prefix` would require clients to hit
    # `{path_prefix}{path_prefix}` and trips Starlette's trailing-slash
    # redirect when `path_prefix` is mounted verbatim as a sub-app.
    app.mount("", mcp_asgi_app)

    # `streamable_http_app()` returns a Starlette app whose own lifespan must
    # be entered for the session manager's background work to run. FastAPI's
    # router already owns a `lifespan_context`; wrap it so both run.
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        async with previous_lifespan(app):
            async with mcp_server.session_manager.run():
                yield

    app.router.lifespan_context = combined_lifespan

    logger.info(f"Added MCP endpoint at '{path_prefix}' ({len(tools)} tool(s))")
    return mcp_server


def run_mcp_stdio(name: str, version: str = "") -> None:
    """Run every tool registered via `@ivcap_lambda(...)` as an MCP server
    over the **stdio** transport instead of HTTP.

    This is a blocking call (it owns the process's stdin/stdout for as long
    as the MCP host keeps the connection open) intended for local
    development with stdio-based MCP clients/hosts (Claude Desktop, Cline,
    the MCP Inspector, etc.) that launch the tool as a subprocess rather than
    connecting over HTTP - useful for iterating on a tool without deploying
    it or running the full FastAPI/uvicorn HTTP server.

    Requires the optional `mcp` package: `pip install ivcap-lambda[mcp]`.

    Args:
        name (str): Name to report to the MCP client as `serverInfo.name`.
        version (str): Version to report to the MCP client as `serverInfo.version`.
    """
    mcp_server = _build_mcp_server(name, version)
    logger.info(f"Starting MCP stdio server ({len(tools)} tool(s))")
    # `mcp_server.run()` is synchronous (it owns the event loop via `anyio.run`
    # internally) and blocks until the client disconnects/EOF on stdin.
    mcp_server.run(transport="stdio")
