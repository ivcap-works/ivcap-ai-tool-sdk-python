# ivcap_ai_tool: A python library for building AI tools for the IVCAP platform

A python library containing various helper and middleware functions
to simplify developing AI tools to be deployed on IVCAP.

## Content

* [Register a Tool Function](#register)
* [Start the Service](#start)
* [Try-Later Middleware](#try-later)
* [JSON-RPC Middleware](#json-rpc)

### Register a Tool Function <a name="register"></a>

```
class Request(BaseModel):
    jschema: str = Field("urn:sd:schema:some_tool.request.1", alias="$schema")
    ...

class Result(BaseModel):
    jschema: str = Field("urn:sd:schema:some_tool.1", alias="$schema")
    ...

def some_tool(req: Request) -> Result:
    """
    Here should go a quite extensive description of what the tool can be
    used for so that an agent can work out if this tool is useful in
    a specific context.

    DO NOT ADD PARAMTER AND RETURN DECRIPTIONS - DESCRIBE THEM IN THE `Request` MODEL
    """
    ...

    return Result(...)

add_tool_api_route(app, "/", some_tool, opts=ToolOptions(tags=["Great Tool"]))
```

### Start the Service <a name="start"></a>

```
app = FastAPI(
  ..
)

if __name__ == "__main__":
    start_tool_server(app, some_tool)
```

### Try-Later Middleware <a name="try-later"></a>

This middleware is supporting the use case where the execution of a
requested service is taking longer than the caller is willing to wait.
A typical use case is where the service is itself outsourcing the execution
to some other long-running service but may immediately receive a reference
to the eventual result.

In this case, raising a `TryLaterException` will return with a 204
status code and additional information on how to later check back for the
result.

```python
from ivcap_fastapi import TryLaterException, use_try_later_middleware
use_try_later_middleware(app)

@app.post("/big_job")
def big_job(req: Request) -> Response:
    jobID, expected_exec_time = scheduling_big_job(req)
    raise TryLaterException(f"/jobs/{jobID}", expected_exec_time)

@app.get("/jobs/{jobID}")
def get_job(jobID: str) -> Response:
    resp = find_result_for(job_id)
    return resp
```

Specifically, raising `TryLaterException(location, delay)` will
return an HTTP response with a 204 status code with the additional
HTTP headers `Location` and `Retry-Later` set to `location` and
`delay` respectively.

### JSON-RPC Middleware <a name="json-rpc"></a>

This middleware will convert any `POST /` with a payload
following the [JSON-RPC](https://www.jsonrpc.org/specification)
specification to an internal `POST /{method}` and will return
the result formatted according to the JSON-RPC spec.

```python
from ivcap_fastapi import use_json_rpc_middleware
use_json_rpc_middleware(app)
```
