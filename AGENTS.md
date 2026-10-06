# AGENTS.md: Building Services with `ivcap-lambda`

This document provides comprehensive instructions for AI coding agents on how to use the `ivcap-lambda` library. There are two primary development paths — pick the one matching the developer's goal, or read both if a project needs to do both.

## Overview

`ivcap-lambda` turns a plain Python function into:

- A set of **IVCAP-compatible HTTP endpoints** (REST, with async "try-later" semantics), and/or
- A **spec-compliant MCP (Model Context Protocol) server** (Streamable-HTTP or stdio transport)

...from the *same* tool-function code, using the *same* Pydantic request/result models and docstrings. It extends [`ivcap-service`](https://github.com/ivcap-works/ivcap-service-sdk-python) (base primitives shared by all IVCAP services) and adds FastAPI/uvicorn HTTP scaffolding plus the MCP adapter.

**Key distinction from `ivcap-service`:**
- `ivcap-service` — batch services that poll a job queue (long-running workers)
- `ivcap-lambda` — lambda/HTTP/MCP services that respond to individual tool invocations

## Which Track Do I Need?

| Your primary goal | Read this |
|---|---|
| Build a service to deploy on the IVCAP platform (REST tool/agent endpoint); MCP is optional or not needed | **[Track A: IVCAP Lambda Service](#track-a-ivcap-lambda-service)** |
| Build an MCP server (for Claude Desktop, Cursor, Cline, etc.); the ability to *also* run on IVCAP is a bonus, not the focus | **[Track B: MCP-First Server](#track-b-mcp-first-server)** |
| Both — ship a service that's a first-class IVCAP tool *and* a first-class MCP server | Read Track A fully, then skim Track B for what changes when MCP is the primary interface |

Both tracks share the same core building blocks (`@ivcap_lambda`, `ToolOptions`, `JobContext`, `@with_schema`) — see [Shared Reference](#shared-reference) at the end for the full symbol table.

## Architecture

```
ivcap-service  (batch + base primitives)
      │
      └── ivcap-lambda  (lambda / HTTP / MCP)
                │
                └── Your Tool Function
                        │
                        ├── POST /tool          ← submit job (REST)
                        ├── GET  /tool          ← tool description (agents)
                        ├── GET  /jobs/{id}     ← poll deferred result (REST)
                        └── /mcp or stdio       ← MCP tools/call (--with-mcp[-stdio])
```

---

# Track A: IVCAP Lambda Service

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
service, read **[Track B: MCP-First Server](#track-b-mcp-first-server)**
below instead — it covers starting from an MCP-only mindset and treating
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

That's the end of Track A. See [Shared Reference](#shared-reference) below for Best Practices and the full symbol table (applicable to both tracks), or continue to Track B if MCP is also (or primarily) a goal.

---

# Track B: MCP-First Server

For developers whose primary goal is building an **MCP server** — one that works well in Claude Desktop, Cursor, Cline, or any other MCP host — where the ability to *also* run as an IVCAP lambda service is a nice-to-have, not the focus. You write exactly the same `@ivcap_lambda`-decorated functions as Track A; the difference is which parts of the library you actually need to think about, and which CLI flag you reach for first.

## Why `ivcap-lambda` for an MCP-only project?

Even if you never plan to deploy to IVCAP, `ivcap-lambda` gives you a production-quality MCP server for very little code because it's built on the **official `mcp` Python SDK** (not a custom reimplementation): spec-correct session handling, Streamable-HTTP *and* stdio transports, resumability, and progress notifications all come from that upstream dependency. On top, `ivcap-lambda` adds:

- Pydantic-model-driven tool schemas (define a request/result model once, get the MCP input/output schema and the REST schema for free)
- A thread pool + job-result cache so slow/blocking tool functions don't need to be rewritten as `async def`
- `jobCtxt.report.step(...)` progress reporting that is automatically bridged to native MCP `notifications/progress` messages
- A Swagger/OpenAPI UI (`/api`) and a tool-description endpoint "for free" if you ever *do* want to expose the same tool over plain REST

## Minimal MCP-Only Service

```python
from pydantic import BaseModel, Field
from ivcap_service import Service, with_schema
from ivcap_lambda import ivcap_lambda, start_lambda_server, logging_init

logging_init()

# `Service` metadata is still required by start_lambda_server(), but none of
# its fields matter for MCP clients — only `name` is used (as the MCP
# server's reported name). Keep it minimal.
service = Service(name="My MCP Server")


@with_schema("urn:sd:schema:my-mcp-server.add.request.1")
class AddRequest(BaseModel):
    a: int = Field(..., description="First number.")
    b: int = Field(..., description="Second number.")


@with_schema("urn:sd:schema:my-mcp-server.add.1")
class AddResult(BaseModel):
    sum: int = Field(..., description="a + b.")


@ivcap_lambda("/add")
def add(req: AddRequest) -> AddResult:
    """Add two numbers

    Returns the sum of the two provided numbers.
    """
    return AddResult(sum=req.a + req.b)


if __name__ == "__main__":
    start_lambda_server(service)
```

Run it as a pure MCP server — no HTTP port, no FastAPI server, nothing IVCAP-specific — ideal for local development against Claude Desktop/Cline, which launch the server as a stdio subprocess:

```bash
pip install ivcap-lambda[mcp]
python my_mcp_server.py --with-mcp-stdio
```

Or expose it over HTTP (Streamable-HTTP transport) for remote MCP clients / the MCP Inspector:

```bash
python my_mcp_server.py --with-mcp --port 8090
# then: npx @modelcontextprotocol/inspector http://localhost:8090/mcp
```

`--with-mcp` and `--with-mcp-stdio` are mutually exclusive. With `--with-mcp-stdio`, no REST/Swagger/health endpoints are started at all — the process is purely an MCP server over stdio for as long as the host keeps the connection open.

## Things You Can Mostly Ignore in an MCP-First Project

These exist for IVCAP deployment and are safe to skip unless/until you decide to also run on IVCAP:

- `ToolOptions.max_wait_time` / `refresh_interval` — only affect the REST "try-later" (`204`) path; MCP's `tools/call` always awaits the result directly (see [Execution Semantics](#execution-semantics-mcp-vs-rest) below)
- `ToolOptions.service_id` — only used to populate the IVCAP tool-description endpoint's `service_id` field
- `JobContext.ivcap` / `JobContext.job_authorization` — IVCAP platform client and auth token; irrelevant unless your tool talks to IVCAP artifacts/services
- `--print-tool-description` / `--print-service-description` — only needed for IVCAP platform registration
- `[tool.poetry-plugin-ivcap]` in `pyproject.toml` — only needed if/when you register the service with IVCAP

## Things Worth Using Even in an MCP-First Project

- **`@with_schema` on request/result models** — still the mechanism that generates the MCP tool's input/output JSON schema from your Pydantic model; skipping it is not an option, it's load-bearing for both transports
- **Docstrings** — the first paragraph becomes the MCP tool's short description surfaced to the LLM; the rest becomes the longer description. Same conventions as Track A: explain what the tool does, when to use it, and any constraints
- **`JobContext` (optional parameter) for progress reporting** — if a tool can take more than a second or two, accept `jobCtxt: JobContext` and wrap the slow part in `with jobCtxt.report.step(...)`; this shows up as live progress in MCP clients that render `notifications/progress` (e.g. the MCP Inspector), with zero MCP-specific code
- **Raising `ValueError` for bad input** — surfaces as a proper MCP tool error (`is_error=True`) that the calling model can read and react to, instead of a crash

## Execution Semantics: MCP vs REST

MCP's `tools/call` is a single request/response RPC with progress delivered as notifications on the *same* call — there is no REST-style "it's taking a while, poll me later" (`204`/`Retry-Later`) equivalent in the base MCP spec. So when a tool is invoked over MCP, `ivcap-lambda` always waits for the result (bounded by an internal `600s` timeout) rather than ever deferring it. Implications for MCP-first design:

- Don't rely on `ToolOptions.max_wait_time` to bound how long an MCP client waits — it has no effect over MCP
- If a tool can genuinely take minutes, report progress via `jobCtxt.report.step(...)` so the client/host shows the user something is happening, rather than appearing to hang
- The REST "try-later" protocol (described in Track A) only matters if/when the same tool is also exposed over plain REST

## Testing an MCP-First Service

```python
# Using the official mcp SDK's in-memory client (no network, no subprocess)
import asyncio
from ivcap_lambda.mcp import _build_mcp_server  # or call register_mcp(app) and use its return value
import mcp

async def main():
    server = _build_mcp_server("My MCP Server", "0.1.0")
    async with mcp.Client(server) as client:
        tools = await client.list_tools()
        print([t.name for t in tools.tools])
        result = await client.call_tool("add", {"req": {"a": 1, "b": 2}})
        print(result.structured_content)  # {'sum': 3}

asyncio.run(main())
```

For an end-to-end example testing both the stdio and HTTP transports (including a plain-curl Streamable-HTTP client and progress-notification capture), see `examples/test-mcp/` in this repository — particularly `tests/mcp-call.sh` and the `make run-mcp-stdio` / `make test-*` targets. Its `echo` tool is defined with `async def` (not plain `def`) and confirms async tool functions work identically over MCP's `tools/call` as they do over REST (both tracks share the same `Executor`, which detects `async def` via `asyncio.iscoroutinefunction` and awaits it on a dedicated event loop — see section 10, "Async Tools", above).

## Deploying to IVCAP Later (Optional)

If a service built MCP-first later needs to also run on IVCAP, nothing in the tool code changes — add `ToolOptions(service_id=..., tags=[...])`, a `[tool.poetry-plugin-ivcap]` section to `pyproject.toml`, and follow Track A's [Project Structure](#project-structure) / deployment steps. The same `@ivcap_lambda`-decorated function is already a valid REST endpoint; MCP was never a fork, just an additional transport over the same registry.

That's the end of Track B.

---

# Shared Reference

## Best Practices (Both Tracks)

1. **Always use `@with_schema`** on request/result models
2. **Write comprehensive docstrings** — both AI agents (IVCAP) and MCP hosts/models use these to decide when and how to call your tool
3. **Describe every field** with `Field(description="...")`
4. **Accept `JobContext`** when you need progress reporting or artifact access
5. **Use steps** for long operations: `with jobCtxt.report.step("name", "msg") as step:`
6. **Raise `ValueError`** for user input errors, other exceptions for system errors
7. **Call `logging_init()` once** at module level before any loggers
8. **Don't mutate module-level state** per job — tools may run concurrently (true for both REST and MCP invocations)

## Key Symbols Summary

| Symbol | Package | Description | Track |
|--------|---------|-------------|-------|
| `ivcap_lambda` | `ivcap_lambda` | Decorator to register a tool function | Both |
| `start_lambda_server` | `ivcap_lambda` | Start the HTTP server, or the MCP server over stdio with `--with-mcp-stdio` | Both |
| `ToolOptions` | `ivcap_lambda` | Per-tool configuration | Both (some fields REST-only, see Track B) |
| `ExecutorOpts` | `ivcap_lambda.executor` | Thread-pool and cache configuration | Both |
| `logging_init` | `ivcap_lambda` | Initialise structured logging | Both |
| `get_event_reporter` | `ivcap_lambda` | Get `EventReporter` for current thread | Both |
| `get_job_id` | `ivcap_lambda` | Get job ID for current thread | Both |
| `register_mcp` | `ivcap_lambda.mcp` | Mount the MCP Streamable-HTTP server onto a FastAPI app programmatically | MCP |
| `run_mcp_stdio` | `ivcap_lambda.mcp` | Run the MCP server over stdio programmatically | MCP |
| `Service` | `ivcap_service` | Service metadata | Both (minimal for MCP-only) |
| `ServiceContact` | `ivcap_service` | Contact details model | IVCAP-focused |
| `ServiceLicense` | `ivcap_service` | License model | IVCAP-focused |
| `JobContext` | `ivcap_service` | Per-job context | Both |
| `with_schema` | `ivcap_service` | Add `$schema` URN to a Pydantic model | Both |
| `getLogger` | `ivcap_service` | Structured logger | Both |
| `GenericEvent` | `ivcap_service.events` | Named progress event | Both |
| `GenericErrorEvent` | `ivcap_service.events` | Error event | Both |

## Related Documentation

- [Full docs](https://ivcap-works.github.io/ivcap-ai-tool-sdk-python/)
- [MCP & Agent Integration guide](https://ivcap-works.github.io/ivcap-ai-tool-sdk-python/guides/mcp/) — full MCP walkthrough including both tracks
- [DESIGN.md](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/DESIGN.md) — internal architecture, for anyone extending `ivcap-lambda` itself
- [ivcap-service SDK](https://ivcap-works.github.io/ivcap-service-sdk-python/) — base library
- [Template repository](https://github.com/ivcap-works/ivcap-python-ai-tool-template) — ready-to-clone starter
- [IVCAP Platform](https://ivcap.works)
- [Pydantic Docs](https://docs.pydantic.dev/)
- [MCP Specification](https://modelcontextprotocol.io/specification)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) — the upstream SDK `ivcap-lambda`'s MCP support is built on
