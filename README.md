# ivcap_fastapi: Python helpers for building FastAPI based IVCAP services

A python library containing various helper and middleware functions
to support converting FastAPI based tools into IVCAP services.

## Content

* [Try-Later Middleware](#try-later)
* [JSON-RPC Middleware](#json-rpc)

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
