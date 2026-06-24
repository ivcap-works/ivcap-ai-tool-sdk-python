# AGENTS.md: Building IVCAP Lambda Services

This document provides comprehensive instructions for AI coding agents on how to use the `ivcap-lambda` library to build IVCAP lambda-style services.

## Overview

`ivcap-lambda` is a Python library for building **lambda-style HTTP services** on the IVCAP platform. It extends [`ivcap-service`](https://github.com/ivcap-works/ivcap-service-sdk-python) (which provides base primitives for all IVCAP services) and adds FastAPI/uvicorn HTTP scaffolding.

**Key distinction:**
- `ivcap-service` — batch services that poll a job queue (long-running workers)
- `ivcap-lambda` — lambda/HTTP services that respond to individual tool invocations via REST endpoints

Both share the same `Service`, `JobContext`, `EventReporter`, `with_schema`, `getLogger`, and artifact infrastructure from `ivcap-service`.

## Architecture

```
ivcap-service  (batch + base primitives)
      │
      └── ivcap-lambda  (lambda / HTTP)
                │
                └── Your Tool Service
                        │
                        ├── POST /tool  ← submit job
                        ├── GET  /tool  ← get tool description (for agents)
                        └── GET  /jobs/{id}  ← poll deferred result
```

## Quick Start

```python
from pydantic import BaseModel, Field
from ivcap_service import Service, ServiceContact, ServiceLicense, JobContext, getLogger, with_schema
from ivcap_lambda import start_lambda_server, ivcap_lambda, ToolOptions, logging_init

logging_init()
logger = getLogger("my_service")

service = Service(
    name="My Lambda Service",
    contact=ServiceContact(name="Your Name", email="you@example.com"),
    license=ServiceLicense(name="MIT", url="https://opensource.org/license/MIT"),
)


@with_schema("urn:sd:schema:my_service.request.1")
class MyRequest(BaseModel):
    text: str = Field(..., description="Text to process.")


@with_schema("urn:sd:schema:my_service.1")
class MyResult(BaseModel):
    output: str = Field(..., description="Processing result.")


@ivcap_lambda("/process", opts=ToolOptions(tags=["Text"], service_id="/process"))
def process(req: MyRequest, jobCtxt: JobContext) -> MyResult:
    """Process text

    Takes input text and returns a processed version.
    Describe what the tool does for agent consumers here.
    """
    logger.info(f"job={jobCtxt.job_id}")
    with jobCtxt.report.step("work", "Processing...") as step:
        result = req.text.upper()
        step.finished("Done")
    return MyResult(output=result)


if __name__ == "__main__":
    start_lambda_server(service)
```

## Step-by-Step Guide

### 1. Import Required Components

```python
from pydantic import BaseModel, Field
from ivcap_service import (
    Service,
    ServiceContact,
    ServiceLicense,
    JobContext,
    getLogger,
    with_schema,
)
from ivcap_lambda import (
    start_lambda_server,
    ivcap_lambda,
    ToolOptions,
    logging_init,
)
```

Key imports:
- `Service`, `ServiceContact`, `ServiceLicense` — service metadata (from `ivcap_service`)
- `JobContext` — per-invocation context with job ID, reporter, and IVCAP client (from `ivcap_service`)
- `getLogger` — structured logger (from `ivcap_service`)
- `with_schema` — decorator to attach `$schema` URN to a Pydantic model (from `ivcap_service`)
- `start_lambda_server` — start the FastAPI/uvicorn HTTP server (from `ivcap_lambda`)
- `ivcap_lambda` — decorator to register a tool function (from `ivcap_lambda`)
- `ToolOptions` — per-tool configuration (from `ivcap_lambda`)
- `logging_init` — initialise structured logging (from `ivcap_lambda`)

### 2. Initialize Logging

```python
logging_init()  # call once at module level
logger = getLogger("my_service")
```

### 3. Define the Service

```python
service = Service(
    name="My Lambda Service",
    contact=ServiceContact(name="Your Name", email="you@example.com"),
    license=ServiceLicense(name="MIT", url="https://opensource.org/license/MIT"),
)
```

### 4. Define Request and Result Models

- Must inherit from `pydantic.BaseModel`
- Must be decorated with `@with_schema("urn:...")`
- Every field must have a `description` in `Field()`
- Do **NOT** add a `$schema` or `jschema` field manually

```python
@with_schema("urn:sd:schema:my_service.request.1")
class MyRequest(BaseModel):
    param1: str = Field(..., description="First parameter.")
    param2: int = Field(10, description="Optional integer parameter.", ge=1)

@with_schema("urn:sd:schema:my_service.1")
class MyResult(BaseModel):
    result: str = Field(..., description="The result.")
    count: int = Field(..., description="Number of items processed.")
```

**Schema URN format:**
- Request: `urn:{namespace}:schema:{service-name}.request.{version}`
- Result:  `urn:{namespace}:schema:{service-name}.{version}`

### 5. Register a Tool Function with `@ivcap_lambda`

```python
@ivcap_lambda("/process", opts=ToolOptions(tags=["Category"], service_id="/process"))
def process(req: MyRequest, jobCtxt: JobContext) -> MyResult:
    """One-line summary for Swagger/agents

    Detailed description of what this tool does, when to use it,
    and any constraints. This text is shown to AI agents.
    """
    ...
    return MyResult(result=..., count=...)
```

**Function signature rules:**
- First parameter: the request model type (required)
- Additional parameters (optional, detected by type annotation):
  - `JobContext` — injected automatically
  - `fastapi.Request` — injected automatically
  - `ExecutionContext` subclass — injected if passed to decorator
- Return type: the result model type (required)

### 6. `ToolOptions` Fields

| Field | Default | Description |
|---|---|---|
| `name` | inferred | Human-readable tool name |
| `tags` | inferred | OpenAPI tags |
| `max_wait_time` | `5.0` | Seconds POST waits before returning `204 Try-Later` |
| `refresh_interval` | `3` | `Retry-Later` header value |
| `service_id` | `None` | Overrides service ID in tool description; prepend `/` to auto-prefix URL |
| `executor_opts` | `None` | `ExecutorOpts(max_workers, job_cache_size, job_cache_ttl)` |
| `is_ready` | `None` | `Callable[[], bool]` — readiness check |
| `post_route_opts` | `{}` | Extra kwargs for FastAPI route |

### 7. Using JobContext

```python
def process(req: MyRequest, jobCtxt: JobContext) -> MyResult:
    # Job identifier
    job_id = jobCtxt.job_id  # str URN

    # Progress reporting
    with jobCtxt.report.step("step-name", "Human message") as step:
        do_work()
        step.finished("Work done")

    # IVCAP platform client (lazy property)
    ivcap = jobCtxt.ivcap
    artifact = ivcap.get_artifact(req.artifact_id)
    data = b"".join(artifact.as_stream())
```

**JobContext fields:**
- `job_id` (`str`) — unique job URN
- `report` (`EventReporter`) — emit progress events
- `job_authorization` (`str | None`) — bearer token for downstream requests
- `ivcap` (`IVCAP`) — IVCAP client (artifacts, services, aspects)

### 8. Progress Reporting

```python
from ivcap_service.events import GenericEvent, GenericErrorEvent

# Step context manager (recommended)
with jobCtxt.report.step("download", "Downloading data") as step:
    data = download(url)
    step.info(GenericEvent(name="progress", options={"bytes": len(data)}))
    step.finished(f"Downloaded {len(data)} bytes")

# Direct methods
jobCtxt.report.step_started("init", msg="Starting")
jobCtxt.report.step_finished("init", msg="Ready")
jobCtxt.report.step_error("init", error=str(e), context="Init failed")

# One-off event
jobCtxt.report.emit(GenericEvent(name="custom", options={"key": "value"}))
```

### 9. Artifact Handling

```python
import io
ivcap = jobCtxt.ivcap

# Download
artifact = ivcap.get_artifact(req.artifact_id)
data = b"".join(artifact.as_stream(chunk_size=65536))

# Stream to temp file (auto-deleted)
with artifact.as_local_file() as path:
    content = path.read_bytes()

# Upload
result = ivcap.upload_artifact(
    name="output.json",
    io_stream=io.BytesIO(output_bytes),
    content_type="application/json",
    content_size=len(output_bytes),
)
result_urn = result.id
```

### 10. Async Tools

Async functions are fully supported:

```python
import asyncio

@ivcap_lambda("/async-process")
async def async_process(req: MyRequest) -> MyResult:
    """Process asynchronously"""
    await asyncio.sleep(0)
    return MyResult(result=req.text.upper(), count=1)
```

### 11. Error Handling

```python
@ivcap_lambda("/safe")
def safe(req: MyRequest) -> MyResult:
    if not req.param1:
        raise ValueError("param1 must not be empty")  # → 400 Bad Request
    try:
        result = risky_operation(req)
    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        raise  # → 500 Internal Server Error with traceback
    return MyResult(result=result, count=1)
```

- `ValueError` → `400 Bad Request`
- Other exceptions → `500 Internal Server Error`
- Pydantic validation failures → `422 Unprocessable Entity` (before function runs)

### 12. Start the Server

```python
if __name__ == "__main__":
    start_lambda_server(service)
```

**Built-in CLI flags:**
```
--host HOST                  Bind address (default 0.0.0.0)
--port PORT                  Port (default 8090)
--with-telemetry             Enable OpenTelemetry
--with-mcp                   Enable MCP endpoint at /mcp
--print-tool-description     Print tool description JSON and exit
--print-service-description  Print service description JSON and exit
```

## Async (Try-Later) Protocol

When a job takes longer than `max_wait_time`:

```
POST /tool {payload}
→ 204 No Content
  Location: /jobs/{job_id}
  Retry-Later: 3

GET /jobs/{job_id}
→ 200 OK {result}
```

Force async: send `Prefer: respond-async` header.
Custom timeout: send `Timeout: <seconds>` header.

## MCP Support

Enable for AI agent tooling:

```bash
python my_service.py --with-mcp --port 8090
```

This registers `/mcp` (Model Context Protocol endpoint) exposing all registered tools.

## Project Structure

```
my-service/
├── pyproject.toml
├── my_service.py          # entry point
├── Dockerfile
└── tests/
    └── call-process.json  # test payload
```

**pyproject.toml:**
```toml
[tool.poetry.dependencies]
python = ">=3.11,<4.0"
ivcap-lambda = ">=0.7"

[tool.poetry-plugin-ivcap]
service-file = "my_service.py"
service-id   = "urn:ivcap:service:<uuid>"
service-type = "lambda"
port         = 8095
```

## Best Practices

1. **Always use `@with_schema`** on request/result models
2. **Write comprehensive docstrings** — agents use these to decide when to call your tool
3. **Describe every field** with `Field(description="...")`
4. **Accept `JobContext`** when you need progress reporting or artifact access
5. **Use steps** for long operations: `with jobCtxt.report.step("name", "msg") as step:`
6. **Raise `ValueError`** for user input errors, other exceptions for system errors
7. **Call `logging_init()` once** at module level before any loggers
8. **Don't mutate module-level state** per job — tools may run concurrently

## Key Symbols Summary

| Symbol | Package | Description |
|--------|---------|-------------|
| `ivcap_lambda` | `ivcap_lambda` | Decorator to register a tool function |
| `start_lambda_server` | `ivcap_lambda` | Start the HTTP server |
| `ToolOptions` | `ivcap_lambda` | Per-tool configuration |
| `ExecutorOpts` | `ivcap_lambda.executor` | Thread-pool and cache configuration |
| `logging_init` | `ivcap_lambda` | Initialise structured logging |
| `get_event_reporter` | `ivcap_lambda` | Get `EventReporter` for current thread |
| `get_job_id` | `ivcap_lambda` | Get job ID for current thread |
| `Service` | `ivcap_service` | Service metadata |
| `ServiceContact` | `ivcap_service` | Contact details model |
| `ServiceLicense` | `ivcap_service` | License model |
| `JobContext` | `ivcap_service` | Per-job context |
| `with_schema` | `ivcap_service` | Add `$schema` URN to a Pydantic model |
| `getLogger` | `ivcap_service` | Structured logger |
| `GenericEvent` | `ivcap_service.events` | Named progress event |
| `GenericErrorEvent` | `ivcap_service.events` | Error event |

## Related Documentation

- [Full docs](https://ivcap-works.github.io/ivcap-ai-tool-sdk-python/)
- [ivcap-service SDK](https://ivcap-works.github.io/ivcap-service-sdk-python/) — base library
- [Template repository](https://github.com/ivcap-works/ivcap-python-ai-tool-template) — ready-to-clone starter
- [IVCAP Platform](https://ivcap.works)
- [Pydantic Docs](https://docs.pydantic.dev/)
- [MCP Specification](https://modelcontextprotocol.io/specification)
