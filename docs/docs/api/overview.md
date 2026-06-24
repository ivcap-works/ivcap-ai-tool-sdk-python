# API Reference Overview

The API reference documentation is automatically generated from the Python source code docstrings using [mkdocstrings](https://mkdocstrings.github.io/). This ensures the documentation stays in sync with the actual code.

## ivcap-lambda Symbols

The following symbols are exported directly from `ivcap_lambda`:

| Symbol | Module | Description |
|--------|--------|-------------|
| `ivcap_lambda` | `ivcap_lambda` | Decorator to register a tool function as HTTP endpoints |
| `start_lambda_server` | `ivcap_lambda` | Start the FastAPI/uvicorn server |
| `start_tool_server` | `ivcap_lambda` | Deprecated alias for `start_lambda_server` |
| `ToolOptions` | `ivcap_lambda` | Per-tool configuration options |
| `ExecutionContext` | `ivcap_lambda` | Optional shared context passed to every tool invocation |
| `ExecutorOpts` | `ivcap_lambda` | Thread-pool and job-cache configuration |
| `logging_init` | `ivcap_lambda` | Initialise structured logging (uvicorn-compatible) |
| `get_event_reporter` | `ivcap_lambda` | Get the `EventReporter` for the current thread |
| `get_job_id` | `ivcap_lambda` | Get the job ID for the current thread |
| `get_public_url_prefix` | `ivcap_lambda` | Detect the public URL prefix from request headers |
| `SecretMgrClient` | `ivcap_lambda` | Deprecated shim — use `ivcap_service.secret.SecretMgrClient` |

## Inherited from ivcap-service

`ivcap-lambda` builds on top of `ivcap-service`. The following symbols come from that library and are used directly in lambda services:

| Symbol | Module | Description |
|--------|--------|-------------|
| `Service` | `ivcap_service` | Service metadata (name, contact, license) |
| `ServiceContact` | `ivcap_service` | Typed contact details |
| `ServiceLicense` | `ivcap_service` | Typed license information |
| `JobContext` | `ivcap_service` | Per-job context (ID, reporter, IVCAP client) |
| `with_schema` | `ivcap_service` | Decorator to add a `$schema` URI to a Pydantic model |
| `getLogger` | `ivcap_service` | Get a structured logger |
| `logging_init` | `ivcap_service` | Base logging initialisation (wrapped by `ivcap_lambda.logging_init`) |
| `GenericEvent` | `ivcap_service.events` | Emit a named event |
| `GenericErrorEvent` | `ivcap_service.events` | Emit an error event |

See the [ivcap-service API docs](https://ivcap-works.github.io/ivcap-service-sdk-python/api/overview/) for the full reference.

## Documentation Pages

- **[Decorator (`@ivcap_lambda`)](decorators.md)** — The main decorator for registering tools
- **[Server (`start_lambda_server`)](server.md)** — Starting the HTTP server
- **[Executor & Options](executor.md)** — `ToolOptions`, `ExecutorOpts`, `ExecutionContext`
- **[Types](types.md)** — Helper types and models
- **[Utilities](utilities.md)** — Logging and context helpers
