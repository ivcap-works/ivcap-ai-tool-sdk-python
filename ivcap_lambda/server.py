#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import argparse
import os
import sys
from collections.abc import Callable
from logging import Logger
from signal import SIGTERM, signal
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response
from ivcap_service import (
    Service,
    SidecarReporter,
    getLogger,
    otel_instrument,
    print_tool_definition,
    service_log_config,
    set_context,
    set_event_reporter_factory,
)
from ivcap_service import (
    get_version as get_service_version,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# from .context import set_context, otel_instrument
from .builder import tools
from .executor import Executor, get_job_context
from .utils import find_first
from .version import get_version

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


def start_lambda_server(
    service: Service,
    *,
    logger: Logger | None = None,
    custom_args: Callable[[argparse.ArgumentParser], argparse.Namespace] | None = None,
    run_opts: dict[str, Any] | None = None,
    with_telemetry: bool | None = None,
):
    """A helper function to start a FastAPI server for a lambda-style IVCAP service.

    Args:
        service (Service): service description
        logger (Logger): optional logger instance; defaults to getLogger("app")
        custom_args (Optional[Callable[[argparse.ArgumentParser], argparse.Namespace]], optional): callback to add extra CLI arguments. Defaults to None.
        run_opts (Optional[Dict[str, Any]], optional): extra options forwarded to uvicorn.Config. Defaults to None.
        with_telemetry: (Optional[bool]): Instantiate or block use of OpenTelemetry tracing
    """
    if len(tools) == 0:
        raise ValueError(
            "No tools have been registered. Please register at least one tool using the ivcap_lambda decorator."
        )

    app = get_fast_app()
    app.title = service.name
    app.version = service.version or os.environ.get("VERSION", "???")
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
    parser.add_argument(
        "--with-telemetry", action="store_true", help="Initialise OpenTelemetry"
    )
    parser.add_argument("--with-mcp", action="store_true", help="Add an MCP endpoint")
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
        "--print-tool-description",
        type=str,
        metavar="NAME",
        nargs="?",
        const=tool_names[0],
        default=None,
        help=f"Print tool description to stdout [{','.join(tool_names)}]",
    )

    if custom_args is not None:
        args = custom_args(parser)
    else:
        args = parser.parse_args()

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
        print_rest_service_definition(service, tool.worker_fn)
        sys.exit(0)

    logger.info(
        f"{title} - {os.getenv('VERSION')} - v{get_version()}|v{get_service_version()}"
    )

    # Check for '_healtz' service
    healtz = find_first(app.routes, lambda r: r.path == "/_healtz")
    if healtz is None:

        @app.get("/_healtz", tags=["System"])
        def healtz():
            return {"version": os.environ.get("VERSION", "???")}

    if args.with_mcp:
        from .mcp import register_mcp

        register_mcp(app, "/mcp")

    # print(f">>>> OTEL_EXPORTER_OTLP_ENDPOINT: {os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT')}")
    set_event_reporter_factory(SidecarReporter)  # type: ignore[arg-type]

    def get_context():
        jctxt = get_job_context()
        if jctxt is None or jctxt.job_id is None:
            logger.warning("missing job context in thread")
            return None
        return jctxt

    set_context(get_context)

    otel_instrument(
        with_telemetry, lambda _: FastAPIInstrumentor.instrument_app(app), logger
    )

    async def _add_version(request: Request, call_next) -> Response:
        from .version import __version__

        resp = await call_next(request)
        resp.headers["Ivcap-AI-Tool-Version"] = __version__
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

    server = Server(
        config=uvicorn.Config(
            app,
            host=args.host,
            port=args.port,
            log_config=service_log_config(),
            **run_opts,
        )
    )

    # Start the server
    server.run()

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
