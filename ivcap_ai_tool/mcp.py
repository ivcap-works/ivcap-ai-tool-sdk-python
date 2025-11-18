#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import asyncio
from pydantic import BaseModel
from typing import Dict, Any, Union
import json
from pydantic import BaseModel
from typing import Any
from typing import Dict, List, Optional, Union
from typing_extensions import Literal
import json
from typing import Optional, Union
from fastapi import FastAPI, Request, Response, status

from ivcap_service import getLogger, IvcapResult, ExecutionError

from .builder import ToolDescription, tools

logger = getLogger("mcp")

class Notification(BaseModel):
    type: str = "notification"
    message: str

# {
#   "jsonrpc": "2.0",
#   "id": 5,
#   "result": {
#     "content": [
#       {
#         "type": "text",
#         "text": "{\"temperature\": 22.5, \"conditions\": \"Partly cloudy\", \"humidity\": 65}"
#       }
#     ],
#     "structuredContent": {
#       "temperature": 22.5,
#       "conditions": "Partly cloudy",
#       "humidity": 65
#     }
#   }
# }
class Result(BaseModel):
    type: str = "result"
    data: Any

class JsonRpcRequest(BaseModel):
    """
    Pydantic model for a JSON-RPC 2.0 request object.
    """
    jsonrpc: Literal["2.0"]
    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None
    id: Union[int, str, None] = None


class JsonRpcSuccessResponse(BaseModel):
    """
    Pydantic model for a JSON-RPC 2.0 success response.
    """
    jsonrpc: Literal["2.0"]
    result: Any
    id: Union[int, str, None]


class JsonRpcErrorObject(BaseModel):
    """
    Pydantic model for the error object in a JSON-RPC 2.0 error response.
    """
    code: int
    message: str
    data: Optional[Any] = None


class JsonRpcErrorResponse(BaseModel):
    """
    Pydantic model for a JSON-RPC 2.0 error response.
    """
    jsonrpc: Literal["2.0"]
    error: JsonRpcErrorObject
    id: Union[int, str, None]

#JsonRpcResponse = JsonRpcSuccessResponse | JsonRpcErrorResponse

# === Tool Runner (non-streaming path) ===
async def run_tool_once(req_id: str, tool_name: str, input: dict, httpReq: Request) -> Result:
    tool = next((t for t in tools if t.name == tool_name), None)
    if not tool:
        return Result(type="error", data=f"Tool '{tool_name}' not found")

    try:
        input_model = tool.input[0]
        if input_model:
            # verify parameters
            m = input_model(**input)
        else:
            m = input
        queue = await tool.executor.execute(m, f"urn:mcp:{req_id}", httpReq, report_result=False)
        result = await asyncio.wait_for(queue.get(), timeout=600)
        queue.task_done()
    except (asyncio.CancelledError, GeneratorExit):
        # allow cooperative shutdown; propagate cancellation cleanly
        raise
    except Exception as e:
        return Result(type="error", data=str(e))

    if isinstance(result, IvcapResult):
        if isinstance(result.raw, BaseModel):
            try:
                data = result.raw.model_dump()
                return Result(type="result", data=data)
            except Exception:
                pass

        try:
            data = str(result.content)
            return Result(type="result", data=data)
        except Exception as ex:
            result = ExecutionError(error=f"while converting result to string - {ex}", type="")

    if not isinstance(result, ExecutionError):
        # this should never happen
        logger.error(f"expected 'ExecutionError' but got {type(result)}")
        result = ExecutionError(
            error="please report unexpected internal error - expected 'ExecutionError' but got {type(result)}",
            type="internal_error",
        )
    return Result(type="error", data=str(result.error))

async def handle_tools_call(req_id, params, req: JsonRpcRequest, httpReq: Request):
    tool_name = params["name"]
    tool_args = params.get("arguments", {})

    message = await run_tool_once(req_id, tool_name, tool_args, httpReq)
    mtype = message.type
    if mtype == "error":
        data = message.data or "???"
        error = JsonRpcErrorObject(
            code=1000,
            message=str(data),
            data=data
        )
        return JsonRpcErrorResponse(id=req_id, error=error, jsonrpc="2.0")

    elif mtype == "notification":
        # Not expected in non-streaming mode; treat as no-op
        error = JsonRpcErrorObject(
            code=1001,
            message="Unexpected notification message type in non-streaming mode",
        )
        return JsonRpcErrorResponse(id=req_id, error=error, jsonrpc="2.0")

    elif mtype == "result":
        return _result_response(req_id, message)

    else:
        error = JsonRpcErrorObject(
            code=1002,
            message=f"Unknown message type `{mtype}' received from tool",
        )
        return JsonRpcErrorResponse(id=req_id, error=error, jsonrpc="2.0")

def _result_response(req_id, message):
        # If result is not a string, convert to string
        data = message.data or ""
        result = {}
        if not isinstance(data, str):
            text = json.dumps(data)
            result["structuredContent"] = data
        else:
            text = data

        result["content"] = [
            {
                "type": "text",
                "text": text
            }
        ]
        return JsonRpcSuccessResponse(id=req_id, result=result, jsonrpc="2.0")


def register_mcp(app: FastAPI, path_prefix: str = "/mcp"):
    """
    Register the MCP JSON-RPC handler on the given FastAPI app and path_prefix.
    This replaces the @app.post(...) decorator usage.
    The worker_fn and executor parameters are accepted for API symmetry but are not
    directly used by the MCP route.
    """

    async def handle_rpc(rpcReq: JsonRpcRequest, httpReq: Request) -> Union[JsonRpcSuccessResponse, JsonRpcErrorResponse, Response]:
        method = rpcReq.method
        req_id = rpcReq.id
        params = rpcReq.params

        if method == "tools/call":
            return await handle_tools_call(req_id, params, rpcReq, httpReq)

        elif method == "tools/list":
            return await handle_tools_list(req_id)

        elif method == "initialize":
            return await handle_initialize(req_id, app)

        elif method == "notifications/initialized":
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        return await handle_unknown_method(req_id)

    app.add_api_route(
        path_prefix,
        handle_rpc,
        methods=["POST"],
        response_model=None,
        response_model_exclude_none=True,
        response_model_by_alias=True,
    )
    logger.info(f"Added MCP endpoint at '{path_prefix}'")


async def handle_unknown_method(req_id):
    return JsonRpcErrorResponse({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": JsonRpcErrorObject(code=-32601, message="Unknown method"),
    })

async def handle_tools_list(req_id) -> JsonRpcSuccessResponse:
    def f(td: ToolDescription):
        _, description = (td.worker_fn.__doc__.lstrip() + "\n").split("\n", 1)
        input_type = td.input[0]
        return {
            "name": td.name,
            "description": description.strip(),
            "inputSchema": input_type.model_json_schema(),
        }
    tl = [f(t) for t in tools]
    result = { "tools": tl, "isLast": True} # "nextCursor": None }
    return JsonRpcSuccessResponse(id=req_id, result=result, jsonrpc="2.0")

async def handle_initialize(req_id, app) -> JsonRpcSuccessResponse:
    result = {
        "protocolVersion": "2024-11-05",
        "serverInfo": {
            "name": f"MCP Server for {app.title}",
            "version": app.version
        },
        "capabilities": {
            "tools": {
                "listChanged": False
            },
            # "resources": {},
            # "prompts": {},
            "toolProvider": {
                "version": "1.0.0",
                "toolInvocationModes": ["standard", "streaming"]
            }
        }
    }
    return JsonRpcSuccessResponse(id=req_id, result=result, jsonrpc="2.0")
