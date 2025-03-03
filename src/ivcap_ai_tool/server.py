#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import argparse
from logging import Logger
from typing import Any, Callable, Dict, Optional
from fastapi import FastAPI
import uvicorn
import os
import sys

from ivcap_fastapi import service_log_config, getLogger
from .tool_definition import print_tool_definition
from .utils import find_first

def start_tool_server(
    app:FastAPI,
    tool_fn: Callable[..., Any],
    *,
    logger: Optional[Logger] = None,
    custom_args: Optional[Callable[[argparse.ArgumentParser], argparse.Namespace]] = None,
    run_opts: Optional[Dict[str, Any]] = None
):
    """A helper function to start a FastApi server

    Args:
        app (FastAPI): the FastAPI instance
        title (str): the tile
        tool_fn (Callable[..., Any]): _description_
        logger (Logger): _description_
        custom_args (Optional[Callable[[argparse.ArgumentParser], argparse.Namespace]], optional): _description_. Defaults to None.
        run_opts (Optional[Dict[str, Any]], optional): _description_. Defaults to None.
    """
    title = app.title
    if logger is None:
        logger = getLogger("app")

    parser = argparse.ArgumentParser(description=title)
    parser.add_argument('--host', type=str, default=os.environ.get("HOST", "0.0.0.0"), help='Host address')
    parser.add_argument('--port', type=int, default=os.environ.get("PORT", "8090"), help='Port number')
    if tool_fn:
        parser.add_argument('--print-tool-description', action="store_true", help='Print tool description to stdout')

    if custom_args is not None:
        args = custom_args(parser)
    else:
        args = parser.parse_args()

    if args.print_tool_description:
        print_tool_definition(tool_fn)
        sys.exit(0)

    # Check for '_healtz' service
    healtz = find_first(app.routes, lambda r: r.path == "/_healtz")
    if healtz is None:
        @app.get("/_healtz", tags=["system"])
        def healtz():
            return {"version": os.environ.get("VERSION", "???")}

    logger.info(f"{title} - {os.getenv('VERSION')}")
    if run_opts is None:
        run_opts = {}
    uvicorn.run(app, host=args.host, port=args.port, log_config=service_log_config(), **run_opts)