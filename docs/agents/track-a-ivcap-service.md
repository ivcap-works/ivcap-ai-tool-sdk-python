# Track A: IVCAP Lambda Service

> Part of the `ivcap-lambda` AI-agent playbook. Start at [`AGENTS.md`](../../AGENTS.md) if you haven't already — it routes to this file, [Track B](track-b-mcp-first.md), and [Track C](track-c-migrate-from-mcp.md), and holds the Shared Reference (symbol table, best practices) that applies here too.

For developers whose primary goal is a service deployed on the IVCAP platform, reachable via REST and the IVCAP tool-description protocol. MCP support (Track B) can be bolted on later with zero code changes via `--with-mcp`/`--with-mcp-stdio`.

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
--with-mcp-stdio             Run as an MCP server over stdio instead of HTTP (for Claude Desktop/Cline)
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

## Optional: Also Expose as MCP

Everything registered via `@ivcap_lambda(...)` can *also* be exposed as a
spec-compliant MCP server with **zero code changes** — just install the
extra and pass a flag at startup:

```bash
pip install ivcap-lambda[mcp]
python my_service.py --with-mcp --port 8090        # HTTP (Streamable-HTTP transport)
python my_service.py --with-mcp-stdio              # stdio (local dev, Claude Desktop/Cline)
```

If MCP is your primary interface rather than a bonus on top of a REST/IVCAP
service, read **[Track B: MCP-First Server](track-b-mcp-first.md)**
instead — it covers starting from an MCP-only mindset and treating
IVCAP deployment as the add-on. The underlying mechanism (same registry,
same `Executor`, same progress bridging) is identical either way; only the
starting point and which CLI flags/pieces of `ToolOptions`/`JobContext` you
actually need differs.

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

That's the end of Track A. See [`AGENTS.md`'s Shared Reference](../../AGENTS.md#shared-reference) for Best Practices and the full symbol table (applicable to both tracks), or continue to [Track B](track-b-mcp-first.md) if MCP is also (or primarily) a goal.
