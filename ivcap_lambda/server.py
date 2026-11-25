#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import argparse
import asyncio
import json
import os
import socket
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from logging import Logger
from signal import SIGTERM, signal
from threading import current_thread
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response
from ivcap_service import (
    ExecutionError,
    IvcapResult,
    Service,
    SidecarReporter,
    getLogger,
    init_openobserve_from_env,
    otel_instrument,
    print_tool_definition,
    service_log_config,
    set_context,
    set_event_reporter_factory,
    set_sidecar_delivery_disabled,
)
from ivcap_service import (
    get_version as get_service_version,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from starlette.requests import Request as StarletteRequest

# from .context import set_context, otel_instrument
from .builder import ToolDescription, tools
from .executor import Executor, get_job_context
from .health_handler import (
    add_health_route,
    add_ready_handler,
    describe_error,
    startup_state,
)
from .version import get_version, resolve_service_version

# shutdown pod cracefully
signal(SIGTERM, lambda _1, _2: sys.exit(0))

_app = FastAPI(
    docs_url="/api",
)


def get_fast_app() -> FastAPI:
    """Get the FastAPI app instance.

    Returns:
        FastAPI: The FastAPI app instance.
    """
    return _app


def run_test_file(path: str, tool: ToolDescription) -> None:
    """Run `tool` once on a job file in the ivcap-service batch format and print the result.

    The job file has the same shape as the ones used by ivcap-service's
    `--test-file`: `id`, `in-content-type` and `in-content`.

    Args:
        path (str): path to the job JSON file
        tool (ToolDescription): the registered tool to execute
    """
    with open(path) as f:
        job = json.load(f)
    job_id = job.get("id", "unknown_job_id")
    ct = job["in-content-type"]
    if ct != "application/json":
        raise ValueError(f"cannot handle content-type '{ct}'")
    input_model, _ = tool.input
    if input_model is None:
        raise ValueError(f"tool '{tool.name}' has no input model")
    param = input_model(**job["in-content"])

    scope = {
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "server": ("localhost", 8090),
        "path": "/",
        "query_string": b"",
        "headers": [],
    }

    async def _execute():
        queue = await tool.executor.execute(
            param, job_id, StarletteRequest(scope), report_result=False
        )
        return await queue.get()

    res = asyncio.run(_execute())
    if isinstance(res, IvcapResult):
        content = res.content
        try:
            if not isinstance(content, (bytes, str)):
                raise ValueError("content is not in-memory")
            print(json.dumps(json.loads(content), indent=2))
        except ValueError:
            print(content)
    else:
        print(res.model_dump_json(indent=2))
        if isinstance(res, ExecutionError):
            sys.exit(1)


# same default as uvicorn.Config.backlog
_LISTEN_BACKLOG = 2048


def _bind_listen_socket(host: str, port: int, logger: Logger) -> socket.socket:
    """Bind the HTTP listening socket before anything else starts.

    Binding here, rather than letting uvicorn bind later, means a port conflict is
    reported before `on_startup` begins and before anything claims the service is up.
    On failure this logs an actionable error and exits with status 1.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family=family, type=socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as ex:
        sock.close()
        logger.error(f"FATAL - Could not bind to port {port}: {ex.strerror or ex}")
        logger.error(f"Please check for conflicting processes (lsof -i :{port})")
        logger.error("Exiting with error code 1")
        sys.exit(1)
    sock.listen(_LISTEN_BACKLOG)
    sock.set_inheritable(True)
    return sock


def start_lambda_server(
    service: Service,
    *,
    logger: Logger | None = None,
    custom_args: Callable[[argparse.ArgumentParser], argparse.Namespace] | None = None,
    run_opts: dict[str, Any] | None = None,
    with_telemetry: bool | None = None,
    on_startup: Callable[[], Any] | None = None,
):
    """A helper function to start a FastAPI server for a lambda-style IVCAP service.

    Args:
        service (Service): service description
        logger (Logger): optional logger instance; defaults to getLogger("app")
        custom_args (Optional[Callable[[argparse.ArgumentParser], argparse.Namespace]], optional): callback to add extra CLI arguments. Defaults to None.
        run_opts (Optional[Dict[str, Any]], optional): extra options forwarded to uvicorn.Config. Defaults to None.
        with_telemetry: (Optional[bool]): Tri-state control of OpenTelemetry
            instrumentation. CLI flags take precedence over this parameter.
        on_startup (Optional[Callable[[], Any]], optional): sync or async callable run
            in the background once the HTTP server is up. `/_healtz` returns 503
            until it completes. If it raises, the error is logged and the service
            stays not ready. Not run for --test-file or --with-mcp-stdio. Defaults to None.
    """
    if len(tools) == 0:
        raise ValueError(
            "No tools have been registered. Please register at least one tool using the ivcap_lambda decorator."
        )

    app = get_fast_app()
    app.title = service.name
    service_version = resolve_service_version(service.version)
    app.version = service_version
    app.contact = dict(service.contact) if service.contact else None
    app.license_info = dict(service.license) if service.license else None

    title = service.name
    if logger is None:
        logger = getLogger("app")

    tool_names = [tool.name for tool in tools]
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host address",
    )
    parser.add_argument(
        "--port", type=int, default=os.environ.get("PORT", "8090"), help="Port number"
    )
    telemetry_group = parser.add_mutually_exclusive_group()
    telemetry_group.add_argument(
        "--with-telemetry",
        action="store_true",
        help="Force-enable OpenTelemetry instrumentation",
    )
    telemetry_group.add_argument(
        "--without-telemetry",
        action="store_true",
        help="Force-disable OpenTelemetry instrumentation",
    )
    parser.add_argument("--with-mcp", action="store_true", help="Add an MCP endpoint")
    parser.add_argument(
        "--with-mcp-stdio",
        action="store_true",
        help=(
            "Run as an MCP server over stdio instead of starting the HTTP "
            "server (for local development with stdio-based MCP clients, "
            "e.g. Claude Desktop, Cline). Requires the 'mcp' extra."
        ),
    )
    parser.add_argument(
        "--list-services",
        action="store_true",
        help="List the names of all registered services/tools and exit",
    )
    parser.add_argument(
        "--print-service-description",
        type=str,
        metavar="NAME",
        nargs="?",
        const=tool_names[0],
        default=None,
        help=f"Print service description to stdout [{','.join(tool_names)}]",
    )
    parser.add_argument(
        "--service-name",
        type=str,
        default=None,
        help=(
            "Override the service name used in --print-service-description "
            "(defaults to the tool name, with '_' replaced by '-')"
        ),
    )
    parser.add_argument(
        "--print-tool-description",
        type=str,
        metavar="NAME",
        nargs="?",
        const=tool_names[0],
        default=None,
        help=f"Print tool description to stdout [{','.join(tool_names)}]",
    )

    parser.add_argument(
        "--test-file",
        type=str,
        help=(
            "Run the first tool on a job file (ivcap-service format with 'id', "
            "'in-content-type' and 'in-content') and print the result, then exit"
        ),
    )
    parser.add_argument(
        "--without-sidecar",
        "--test-without-sidecar",
        dest="without_sidecar",
        action="store_true",
        help=(
            "Silently drop any attempt to deliver events or results to the "
            "sidecar (no HTTP calls, no retries, no warnings). Useful for "
            "local testing (typically together with --test-file) without a "
            "reachable IVCAP_BASE_URL/sidecar. Can also be set via the "
            "IVCAP_WITHOUT_SIDECAR environment variable."
        ),
    )

    if custom_args is not None:
        args = custom_args(parser)
    else:
        args = parser.parse_args()

    if args.with_mcp_stdio and args.with_mcp:
        parser.error("--with-mcp-stdio and --with-mcp are mutually exclusive")

    if args.list_services:
        for name in tool_names:
            print(name)
        sys.exit(0)

    if args.print_tool_description:
        tool = next((t for t in tools if t.name == args.print_tool_description), None)
        if tool is None:
            print(
                f"Tool '{args.print_tool_description}' not found. Available tools: {', '.join(tool_names)}",
                file=sys.stderr,
            )
            sys.exit(1)
        print_tool_definition(tool.worker_fn)
        sys.exit(0)

    if args.print_service_description:
        from .service_definition import print_rest_service_definition

        tool = next(
            (t for t in tools if t.name == args.print_service_description), None
        )
        if tool is None:
            print(
                f"Tool '{args.print_service_description}' not found. Available tools: {', '.join(tool_names)}",
                file=sys.stderr,
            )
            sys.exit(1)
        tool_slug = tool.name.replace("_", "-")
        name = args.service_name or f"{service.name}-{tool_slug}"
        print_rest_service_definition(
            service,
            tool.worker_fn,
            name=name,
            path=tool.path_prefix,
            service_timeout=tool.service_timeout,
        )
        sys.exit(0)

    logger.info(
        f"{title} - {os.getenv('VERSION')} - v{get_version()}|v{get_service_version()}"
    )

    try:
        init_openobserve_from_env(
            logger=logger,
            service_name=service.name,
            service_version=service_version,
        )
    except Exception as exc:
        logger.warning("OpenTelemetry initialization failed: %s", exc)

    effective_with_telemetry = with_telemetry
    if getattr(args, "without_telemetry", False):
        effective_with_telemetry = False
    elif getattr(args, "with_telemetry", False):
        effective_with_telemetry = True

    env_without_sidecar = os.getenv("IVCAP_WITHOUT_SIDECAR", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )
    if args.without_sidecar or env_without_sidecar:
        logger.info(
            "without-sidecar set - events/results will not be delivered to the sidecar"
        )
        set_sidecar_delivery_disabled(True)

    set_event_reporter_factory(SidecarReporter)  # type: ignore[arg-type]

    def get_context():
        jctxt = get_job_context()
        if jctxt is None or jctxt.job_id is None:
            if not current_thread().name.startswith("Otel"):
                logger.warning("missing job context in thread")
            return None
        return jctxt

    set_context(get_context)

    if args.test_file is not None:
        run_test_file(args.test_file, tools[0])
        return

    if args.with_mcp_stdio:
        # Run as a stdio MCP server instead of the HTTP/uvicorn server: no
        # FastAPI app involved, so there is nothing to instrument there, but
        # outbound httpx/requests calls (e.g. via JobContext.ivcap) are still
        # instrumented the same way as for the HTTP server.
        from .mcp import run_mcp_stdio

        otel_instrument(effective_with_telemetry, None, logger)
        run_mcp_stdio(service.name, app.version)
        return

    add_health_route(app, name=service.name, version=service.version)

    if on_startup is not None:
        # Fresh state for this server run; the gate reads it on every /_healtz.
        startup_state.status = "loading"
        startup_state.error = None

        def _startup_ready() -> bool:
            return startup_state.status == "ready"

        add_ready_handler(_startup_ready)

        async def _run_startup() -> None:
            try:
                if asyncio.iscoroutinefunction(on_startup):
                    await on_startup()
                else:
                    # run sync startup code off the event loop so /_healtz keeps answering
                    await asyncio.to_thread(on_startup)
            except asyncio.CancelledError:
                # shutdown while loading: not a failure, just stop
                raise
            except BaseException as ex:
                # Any error (including SystemExit/KeyboardInterrupt raised by the hook)
                # must not take the server down silently: record it and stay not ready.
                startup_state.status = "failed"
                startup_state.error = describe_error(ex)
                logger.exception(
                    "on_startup failed - service stays not ready: %s",
                    startup_state.error,
                )
                return
            startup_state.status = "ready"
            logger.info("on_startup completed - service is ready")

        previous_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def _startup_lifespan(app: FastAPI):
            async with previous_lifespan(app):
                task = asyncio.create_task(_run_startup())
                try:
                    yield
                finally:
                    task.cancel()

        app.router.lifespan_context = _startup_lifespan

    if args.with_mcp:
        from .mcp import register_mcp

        register_mcp(app, "/mcp")

    otel_instrument(
        effective_with_telemetry,
        lambda _: FastAPIInstrumentor.instrument_app(app),
        logger,
    )

    async def _add_version(request: Request, call_next) -> Response:
        from .version import __version__

        resp = await call_next(request)
        resp.headers["Ivcap-Lambda-Version"] = __version__
        resp.headers["Ivcap-Service-Name"] = service.name
        resp.headers["Ivcap-Service-Version"] = service_version
        return resp

    app.middleware("http")(_add_version)

    if run_opts is None:
        run_opts = {}

    class Server(uvicorn.Server):
        def handle_exit(self, sig: int, frame: Any) -> None:
            logger.info(  # type: ignore[union-attr]
                "Received request for shutdown. Waiting for all running requests to finish first."
            )
            Executor.wait_for_exit_ready()
            super().handle_exit(sig, frame)

    listen_socket = _bind_listen_socket(args.host, args.port, logger)

    server = Server(
        config=uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            log_config=service_log_config(),
            **run_opts,
        )
    )

    # Start the server on the socket bound above, so uvicorn does not bind again.
    server.run(sockets=[listen_socket])

    # uvicorn.run(app, host=args.host, port=args.port, log_config=service_log_config(), **run_opts)


# Backward-compatible alias
def start_tool_server(*args, **kwargs):
    """Deprecated alias for :func:`start_lambda_server`.

    .. deprecated::
        Use :func:`start_lambda_server` instead.
    """
    import warnings

    warnings.warn(
        "start_tool_server() is deprecated; use start_lambda_server() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return start_lambda_server(*args, **kwargs)
