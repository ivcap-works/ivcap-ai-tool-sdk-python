#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
from typing import Optional

from .builder import ToolOptions, add_tool_api_route, WorkerFn
from .executor import ExecutionContext
from .server import get_fast_app

def ivcap_ai_tool(
    path_prefix: str,
    *,
    opts: Optional[ToolOptions] = ToolOptions(),
    context: Optional[ExecutionContext] = None
):
    """Add a few routes to the service for use with an AI tool.

    The tool itself is implemented in `worker_fn` where the first
    argument is a pydantic model describing all the tool's "public" parameters.
    The function is also expected to return it's result as a single pydantic model.
    The tool function can have two optioanl paramters, one with the same type as
    `context` and the second one with `fastapi.Request`. The context paramter will
    be identical to the above `context`, while the `request` will be the incoming
    request.

    This function then sets up three endpoints:
    - POST {path_prefix}: To request the execution of the tool (the 'job')
    - GET {path_prefix}/{job_id}: To collect the result of a tool execution
    - GET {path_prefix}: To obtain a description of the tool suitable for most agent frameworks

    The POST request will only wait `opts.max_wait_time` for the tool to finish. If it
    hasn't finished by then, a `204 No Content` code will be returned with additional
    header fields `Location` and `Retry-later` to inform the caller where and approx.
    when the result can be collected later.

    The `opts` parameter allows for customization of the endpoints. See `ToolOptions`
    for a more detailed description.

    Args:
        path_prefix (str): The path prefix to use for this set of endpoints
        opts (Optional[ToolOptions], optional): Additional behaviour settings. Defaults to ToolOptions().
        context (Optional[ExecutionContext], optional): An optional context to be provided to every invocation of `worker_fn`. Defaults to None.
    """
    def decorator(worker_fn: WorkerFn):
        """
        Args:
        worker_fn (Callable[[BaseModel, Optional[ExecutionContext], Optional[Response]], BaseModel]): _description_
        opts (Optional[ToolOptions], optional): Additional behaviour settings. Defaults to ToolOptions().
        context (Optional[ExecutionContext], optional): An optional context to be provided to every invocation of `worker_fn`. Defaults to None.
        """
        add_tool_api_route(get_fast_app(), path_prefix, worker_fn, opts=opts, context=context)
        return worker_fn

    return decorator