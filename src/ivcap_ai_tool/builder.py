#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import asyncio
from fastapi import FastAPI, Response, status, Request
from pydantic import BaseModel, Field
from typing import Optional, Callable, TypeVar
from uuid6 import uuid6

from ivcap_fastapi import getLogger

from .executor import ExecutionContext, ExecutionError, Executor, ExecutorOpts
from .utils import _get_input_type, _get_function_return_type, _get_title_from_path
from .tool_definition import ToolDefinition, create_tool_definition



class ErrorModel(BaseModel):
    message: str
    code: int

logger = getLogger("wrapper")

class ToolOptions(BaseModel):
    name: Optional[list[str]] = Field(None, description="Name to be used for this tool")
    tag: Optional[list[str]] = Field(None, description="OpenAPI tag for this set of functions")
    max_wait_time: Optional[float] = Field(5.0, description="max. time in seconds to wait for result and before returning RetryLater")
    refresh_interval: Optional[int] = Field(3, description="Time in seconds to wait before chacking again for a job result (used in RetryLater)")
    executor_opts: Optional[ExecutorOpts] = Field(None, description="Options for the executor")


# Define a generic type for Pydantic models
T = TypeVar("T", bound=BaseModel)

def add_tool_api_route(
    app: FastAPI,
    path_prefix: str,
    worker_fn: Callable[[BaseModel, Optional[ExecutionContext], Optional[Response]], BaseModel],
    *,
    opts: Optional[ToolOptions] = ToolOptions(),
    context: Optional[ExecutionContext] = None
):
    """Add a few routes to `app` for use with an AI tool.

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
        app (FastAPI): The FastAPI context
        path_prefix (str): The path prefix to use for this set of endpoints
        worker_fn (Callable[[BaseModel, Optional[ExecutionContext], Optional[Response]], BaseModel]): _description_
        opts (Optional[ToolOptions], optional): Additional behaviour settings. Defaults to ToolOptions().
        context (Optional[ExecutionContext], optional): An optional context to be provided to every invocation of `worker_fn`. Defaults to None.
    """
    def_name, def_tag = _get_title_from_path(path_prefix)
    if opts.tag is None:
       opts.tag = def_tag
    if opts.name is None:
        opts.name = def_name

    output_model = _get_function_return_type(worker_fn)
    executor = Executor[output_model](worker_fn, opts=opts.executor_opts, context=context)

    _add_do_job_route(app, path_prefix, worker_fn, executor, opts)
    _add_get_job_route(app, path_prefix, worker_fn, executor, opts)
    _add_get_tool_def_route(app, path_prefix, worker_fn, opts)

def _add_do_job_route(app: FastAPI, path_prefix: str, worker_fn: Callable, executor: Executor, opts: ToolOptions):
    input_model, _ = _get_input_type(worker_fn)
    output_model = _get_function_return_type(worker_fn)
    summary, description = worker_fn.__doc__.split("\n", 1)

    async def route(data: input_model, req: Request) -> output_model:  # type: ignore
        job_id = str(uuid6())
        queue = await executor.execute(data, job_id, req)
        try:
            el = await asyncio.wait_for(queue.get(), timeout=opts.max_wait_time)
            queue.task_done()
            return _return_job_result(el, job_id)
        except asyncio.TimeoutError:
            headers = {
                "Location": f"{path_prefix}/{job_id}",
                "Retry-Later": f"{opts.refresh_interval}",
            }
            return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)

    responses = {
        204: {
            "headers": {
                "Location": {
                    "description": "The URL where to pick up the result of this request",
                    "type": "string",
                },
                "Retry-Later": {
                    "description": "The time to wait before checking for a result",
                    "type": "integer",
                },
            },
        },
        400: { "model": ErrorModel, },
        # 400: {"model": Error}, 401: {"model": Error}, 429: {"model": Error}},
    }
    app.add_api_route(
        path_prefix,
        route,
        summary=summary,
        description=description,
        methods=["POST"],
        responses=responses,
        tags=[opts.tag],
        response_model_exclude_none=True,
        response_model_by_alias=True,
    )

def _add_get_job_route(app: FastAPI, path_prefix: str, worker_fn: Callable, executor: Executor, opts: ToolOptions):
    output_model = _get_function_return_type(worker_fn)
    def route(job_id: str) -> output_model: # type: ignore
        try:
            result = executor.lookup_job(job_id)
            return _return_job_result(result, job_id)
        except KeyError:
            return Response(status_code=status.HTTP_404_NOT_FOUND,
                            content=f"job {job_id} can't be found. It either never existed or its result is no longer cached.")

    responses = {
        400: { "model": ErrorModel, },
    }
    path = "/" + "{job_id}" if path_prefix == "/" else f"{path_prefix}/" + "{job_id}"
    app.add_api_route(
        path,
        route,
        summary="Returns the description of this tool. Primarily used by agents.",
        methods=["GET"],
        responses=responses,
        tags=[opts.tag],
        response_model_exclude_none=True,
        response_model_by_alias=True,
    )

def _return_job_result(el, job_id):
    if isinstance(el, ExecutionError):
        if el.type == ValueError:
            m = ErrorModel(message=el.error, code=400)
            return Response(status_code=status.HTTP_400_BAD_REQUEST, content=m)
        raise Exception()
    else:
        return el

def _add_get_tool_def_route(app: FastAPI, path_prefix: str, worker_fn: Callable, opts: ToolOptions):
    async def route() -> ToolDefinition:  # type: ignore
        return create_tool_definition(worker_fn, name=opts.name)

    app.add_api_route(
        path_prefix,
        route,
        summary="Returns the description of this tool. Primarily used by agents.",
        methods=["GET"],
        tags=[opts.tag],
        response_model_exclude_none=True,
        response_model_by_alias=True,
    )
