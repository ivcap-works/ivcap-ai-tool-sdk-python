# ivcap-lambda: Python SDK for Lambda-Style IVCAP Services

> **Package renamed:** `ivcap-ai-tool` has been renamed to `ivcap-lambda` to reflect that
> the library is useful for any lambda-style IVCAP service, not just AI agent tools.
> A [compatibility shim](./compat/) is published under the old name — existing apps
> will continue to work but will see a `DeprecationWarning` prompting migration.

<a href="https://scan.coverity.com/projects/ivcap-works-ivcap-ai-tool-sdk-python">
  <img alt="Coverity Scan Build Status"
       src="https://img.shields.io/coverity/scan/31491.svg"/>
</a>

`ivcap-lambda` is a Python library that provides the scaffolding for building **lambda-style services** on the [IVCAP platform](https://github.com/ivcap-works). It sits on top of [`ivcap-service`](https://pypi.org/project/ivcap-service/) and [FastAPI](https://fastapi.tiangolo.com/) and handles:

- Registering tool functions as HTTP endpoints (with async "try-later" semantics)
- Job execution in threads, result caching, and graceful shutdown
- Event/progress reporting back to the IVCAP platform
- Automatic tool-description endpoints (for AI agents and the MCP protocol)
- Optional OpenTelemetry tracing and an MCP endpoint

> **Template repository:** A ready-to-clone project template is available at
> [ivcap-works/ivcap-python-ai-tool-template](https://github.com/ivcap-works/ivcap-python-ai-tool-template).

---

## Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Defining a Tool](#defining-a-tool)
  - [Request & Result models](#request--result-models)
  - [The `@ivcap_lambda` decorator](#the-ivcap_lambda-decorator)
  - [Accessing the Job Context](#accessing-the-job-context)
  - [Async tools](#async-tools)
- [Starting the Server](#starting-the-server)
- [Endpoints Created per Tool](#endpoints-created-per-tool)
- [Reporting Progress Events](#reporting-progress-events)
- [Accessing IVCAP Artifacts](#accessing-ivcap-artifacts)
- [Project Layout & Configuration](#project-layout--configuration)
- [Running Locally](#running-locally)
- [Building & Deploying a Docker Image](#building--deploying-a-docker-image)
- [Migration from `ivcap-ai-tool`](#migration-from-ivcap-ai-tool)

---

## Installation

```bash
pip install ivcap-lambda
```

Or with Poetry:

```bash
poetry add ivcap-lambda
```

---

## Quick Start

The simplest possible lambda service:

```python
from pydantic import BaseModel, Field
from ivcap_service import Service, getLogger, with_schema
from ivcap_lambda import start_lambda_server, ivcap_lambda, ToolOptions, logging_init

logging_init()
logger = getLogger("my-service")

service = Service(
    name="My IVCAP Service",
    description="A minimal example service.",
    contact={"name": "Alice", "email": "alice@example.com"},
    license={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
)


@with_schema("urn:example:schema:echo.request.1")
class EchoRequest(BaseModel):
    message: str = Field(..., description="The message to echo back.")


@with_schema("urn:example:schema:echo.1")
class EchoResult(BaseModel):
    echo: str = Field(..., description="The echoed message.")


@ivcap_lambda("/", opts=ToolOptions(tags=["Echo"]))
def echo(req: EchoRequest) -> EchoResult:
    """Echo a message

    Returns the message passed in the request unchanged.
    """
    return EchoResult(echo=req.message)


if __name__ == "__main__":
    start_lambda_server(service)
```

Run it:

```bash
python my_service.py --port 8090
```

Test it:

```bash
curl -X POST http://localhost:8090/ \
  -H "content-type: application/json" \
  -d '{"message": "Hello, IVCAP!"}'
```

---

## Defining a Tool

### Request & Result models

Tool inputs and outputs are [Pydantic](https://docs.pydantic.dev/) `BaseModel` classes. Use the `@with_schema` decorator (from `ivcap_service`) to annotate them with an IVCAP schema URI — this adds a `$schema` field that the platform uses to identify payloads.

```python
from pydantic import BaseModel, Field
from ivcap_service import with_schema

@with_schema("urn:example:schema:my-tool.request.1")
class MyRequest(BaseModel):
    name: str = Field(..., description="Name to greet.")
    count: int = Field(1, description="Number of times to repeat the greeting.", ge=1)

@with_schema("urn:example:schema:my-tool.1")
class MyResult(BaseModel):
    greeting: str = Field(..., description="The generated greeting.")
```

### The `@ivcap_lambda` decorator

Use `@ivcap_lambda` to register a function as a tool endpoint:

```python
from ivcap_lambda import ivcap_lambda, ToolOptions

@ivcap_lambda("/greet", opts=ToolOptions(tags=["Greeter"], service_id="/greet"))
def greet(req: MyRequest) -> MyResult:
    """Greet a person

    Generates a personalised greeting the requested number of times.
    Describe your tool here — this text is surfaced to AI agents to
    help them decide whether to use it.
    """
    return MyResult(greeting=(f"Hello, {req.name}! " * req.count).strip())
```

**`ToolOptions` fields:**

| Field | Default | Description |
|---|---|---|
| `name` | (inferred from path) | Human-readable name for the tool endpoint |
| `tags` | (inferred from path) | OpenAPI tags for grouping endpoints |
| `max_wait_time` | `5.0` | Seconds the `POST` waits before returning `204 Try-Later` |
| `refresh_interval` | `3` | `Retry-Later` header value (seconds) returned with `204` |
| `service_id` | `None` | Overrides the service ID reported in the tool description |
| `post_route_opts` | `{}` | Additional kwargs forwarded to the FastAPI route constructor |
| `executor_opts` | `None` | `ExecutorOpts` (job cache size/TTL, thread pool size) |

**`service_id`:** If set to a path (e.g. `"/"` or `"/greet"`), the server prepends the public URL prefix automatically, so agents receive a fully-qualified service ID.

### Accessing the Job Context

Your tool function can optionally accept a `JobContext` (from `ivcap_service`) as a keyword argument. The framework detects it by type annotation and injects it automatically. Through `JobContext` you can:

- Report progress events back to the platform
- Access IVCAP artifacts and other platform resources

```python
from ivcap_service import JobContext
from fastapi import Request as FRequest

@ivcap_lambda("/process", opts=ToolOptions(tags=["Processor"]))
def process(req: MyRequest, freq: FRequest, jobCtxt: JobContext) -> MyResult:
    """Process a request

    Detailed description for agents.
    """
    logger.info(f"job_id={jobCtxt.job_id}")
    with jobCtxt.report.step("work", "Starting work...") as step:
        result = do_work(req)
        step.finished(f"Finished in {len(result)} steps")
    return MyResult(...)
```

`JobContext` fields:

| Field | Type | Description |
|---|---|---|
| `job_id` | `str` | The unique job identifier (URN) |
| `report` | `EventReporter` | For emitting progress events to the platform |
| `job_authorization` | `str \| None` | Bearer token for authenticated calls |
| `ivcap` | `IVCAP` | IVCAP client for artifacts, services, etc. |

The `fastapi.Request` (`freq`) parameter is also optional and, like `JobContext`, is injected by type.

### Async tools

Async functions are fully supported:

```python
@ivcap_lambda("/async-greet", opts=ToolOptions(tags=["Greeter"]))
async def async_greet(req: MyRequest) -> MyResult:
    """Greet asynchronously

    Same as greet but runs in an async context.
    """
    await asyncio.sleep(0)  # yield once
    return MyResult(greeting=f"Hello, {req.name}!")
```

---

## Starting the Server

```python
if __name__ == "__main__":
    start_lambda_server(service)
```

`start_lambda_server` accepts:

| Argument | Description |
|---|---|
| `service` | A `Service` instance (name, contact, license) |
| `custom_args` | `Callable[[ArgumentParser], Namespace]` — add your own CLI flags |
| `run_opts` | Extra kwargs forwarded to `uvicorn.Config` |
| `with_telemetry` | `True` / `False` to force-enable or force-disable OpenTelemetry |

**Built-in CLI flags** (available to every service):

```
--host HOST                  Bind address (default: 0.0.0.0 / $HOST)
--port PORT                  Port to listen on (default: 8090 / $PORT)
--with-telemetry             Initialise OpenTelemetry tracing
--with-mcp                   Expose an MCP endpoint at /mcp
--print-tool-description     Print the tool description JSON and exit
--print-service-description  Print the full service description JSON and exit
```

**Custom CLI flags example:**

```python
def custom_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    parser.add_argument("--my-flag", type=str, help="My custom flag")
    args = parser.parse_args()
    if args.my_flag:
        os.environ["MY_FLAG"] = args.my_flag
    return args

if __name__ == "__main__":
    start_lambda_server(service, custom_args=custom_args)
```

---

## Endpoints Created per Tool

For each `@ivcap_lambda`-decorated function at path `{prefix}`, three routes are registered:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `{prefix}` | Submit a job (execute the tool) |
| `GET` | `{prefix}` | Return a tool description (for agents / MCP) |
| `GET` | `/jobs/{job_id}` | Poll for the result of a deferred job |

Additionally, the framework registers:

- `GET /_healtz` — health check (returns `{"version": "..."}`)
- `GET /api` — Swagger/OpenAPI UI
- `GET /mcp` — MCP endpoint (only if `--with-mcp` is passed)

### Asynchronous ("try-later") semantics

When a job takes longer than `ToolOptions.max_wait_time` (default 5 s), the `POST` returns **`204 No Content`** with:

```
Location: /jobs/{job_id}
Retry-Later: 3
```

The caller can then `GET /jobs/{job_id}` after the indicated delay to collect the result.

You can force asynchronous behaviour by sending `Prefer: respond-async` or control the timeout per request with a `Timeout: <seconds>` header.

---

## Reporting Progress Events

`JobContext.report` is an `EventReporter`. Use it to stream structured progress information to the IVCAP platform.

```python
from ivcap_service.events import GenericEvent

# Structured step (emits a start event, then a finish event automatically)
with jobCtxt.report.step("download", "Downloading data...") as step:
    for i, chunk in enumerate(data_stream):
        process(chunk)
        step.info(GenericEvent(name="progress", options={"chunk": i}))
    step.finished(f"Downloaded {i+1} chunks")

# Emit a one-off event
jobCtxt.report.emit(GenericEvent(name="done", options={"count": 42}))
```

**Available event types** (from `ivcap_service.events`):

| Class | Schema URI | Use |
|---|---|---|
| `GenericEvent(name, options)` | `urn:ivcap:schema:service.event.generic.1` | General-purpose named event |
| `GenericErrorEvent(error, context, stacktrace)` | `urn:ivcap:schema:service.event.error.1` | Error/exception reporting |

Custom events can be created by subclassing `BaseEvent` and defining a `SCHEMA` class variable.

---

## Accessing IVCAP Artifacts

`JobContext.ivcap` is an `IVCAP` client instance (from [`ivcap-client`](https://pypi.org/project/ivcap-client/)). Use it to interact with platform resources such as artifacts.

```python
def my_tool(req: MyRequest, jobCtxt: JobContext) -> MyResult:
    artifact = jobCtxt.ivcap.get_artifact(req.artifact_id)

    with jobCtxt.report.step("download", f"Streaming {artifact.id}") as step:
        bytes_received = 0
        for chunk in artifact.as_stream(chunk_size=8192):
            bytes_received += len(chunk)
            step.info(GenericEvent(name="chunk", options={"bytes": bytes_received}))
        step.finished(f"Downloaded {bytes_received} bytes")

    return MyResult(size=bytes_received)
```

---

## Project Layout & Configuration

A typical project looks like this:

```
my-service/
├── pyproject.toml
├── my_service.py      # tool implementation (entry point)
├── Dockerfile
└── tests/
    └── echo.json
```

**`pyproject.toml`** — include the `ivcap` plugin section to integrate with the `poetry-plugin-ivcap` tooling:

```toml
[project]
name = "my-service"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["ivcap-lambda"]

[tool.poetry-plugin-ivcap]
service-file = "my_service.py"      # entry-point script
service-id   = "urn:ivcap:service:<uuid>"   # stable service URN
service-type = "lambda"
port         = 8095
```

---

## Running Locally

```bash
# Install dependencies
poetry install

# Run the service (uses port from pyproject.toml [tool.poetry-plugin-ivcap])
poetry ivcap run

# Or run directly
python my_service.py --port 8095
```

**Quick test with `curl`:**

```bash
# Synchronous call (waits up to max_wait_time)
curl -X POST http://localhost:8095/ \
  -H "content-type: application/json" \
  -d '{"message": "Hello!"}'

# Async call — get a 204 immediately with a Location header
curl -i -X POST http://localhost:8095/ \
  -H "content-type: application/json" \
  -H "Prefer: respond-async" \
  -d '{"message": "Hello!"}'

# Collect the result (replace JOB_ID)
curl http://localhost:8095/jobs/JOB_ID
```

**With IVCAP authentication:**

```bash
curl -X POST http://localhost:8095/ \
  -H "content-type: application/json" \
  -H "job-id: urn:ivcap:job:<uuid>" \
  -H "Authorization: Bearer $(ivcap context get access-token --refresh-token)" \
  -d '{"message": "Hello!"}'
```

**Print service/tool description (useful for IVCAP deployment):**

```bash
python my_service.py --print-service-description
python my_service.py --print-tool-description
```

---

## Building & Deploying a Docker Image

A minimal `Dockerfile`:

```dockerfile
FROM python:3.11-slim-bookworm
WORKDIR /app
COPY pyproject.toml ./
RUN pip install poetry \
  && poetry config virtualenvs.create false \
  && poetry install --no-root \
  && pip uninstall -y poetry

COPY my_service.py ./

ARG VERSION=???
ENV VERSION=$VERSION
ENV PORT=80

ENTRYPOINT ["python", "/app/my_service.py"]
```

Build and run:

```bash
docker build -t my-service .
docker run -p 8095:80 my-service
```

---

## Migration from `ivcap-ai-tool`

| Old (deprecated) | New |
|---|---|
| `pip install ivcap-ai-tool` | `pip install ivcap-lambda` |
| `from ivcap_ai_tool import ...` | `from ivcap_lambda import ...` |
| `@ivcap_ai_tool(...)` | `@ivcap_lambda(...)` |

The old `ivcap-ai-tool` package is a compatibility shim that re-exports everything from `ivcap-lambda`. It will emit a `DeprecationWarning` at import time. No code changes beyond the import are required.

---

## Key Symbols

| Symbol | Package | Description |
|---|---|---|
| `ivcap_lambda` | `ivcap_lambda` | Decorator to register a tool function |
| `start_lambda_server` | `ivcap_lambda` | Start the FastAPI/uvicorn server |
| `start_tool_server` | `ivcap_lambda` | Deprecated alias for `start_lambda_server` |
| `ToolOptions` | `ivcap_lambda` | Options for `@ivcap_lambda` |
| `logging_init` | `ivcap_lambda` | Initialise structured logging |
| `Service` | `ivcap_service` | Service metadata (name, contact, license) |
| `JobContext` | `ivcap_service` | Per-job context (ID, reporter, IVCAP client) |
| `with_schema` | `ivcap_service` | Decorator to add a `$schema` URI to a model |
| `getLogger` | `ivcap_service` | Get a structured logger |
| `GenericEvent` | `ivcap_service.events` | Emit a named event |
| `GenericErrorEvent` | `ivcap_service.events` | Emit an error event |
