# Glossary

Key terms and concepts used in the IVCAP Lambda SDK.

## Artifact

A file or data object stored in the IVCAP platform. Lambda tools accept artifact URNs as input parameters and upload new artifacts as results.

## Lambda Service

A service that exposes one or more tool functions as HTTP endpoints. Each invocation is independent and returns a result (or defers via the try-later pattern). Contrast with a *batch service*, which processes jobs from a queue.

## Batch Service

A service built with [`ivcap-service`](https://ivcap-works.github.io/ivcap-service-sdk-python/) that processes discrete jobs asynchronously from a platform queue. `ivcap-lambda` extends `ivcap-service` to add HTTP scaffolding.

## JobContext

The context object injected into your tool function by the framework. Provides access to the job ID, `EventReporter`, and the `IVCAP` client for platform APIs.

## Tool Function

A Python function decorated with `@ivcap_lambda` that becomes an HTTP endpoint. Accepts a Pydantic request model and returns a Pydantic result model.

## ToolOptions

A Pydantic model that configures per-tool behaviour: wait timeout, retry interval, OpenAPI tags, service ID, executor options, and readiness check.

## Try-Later / 204 Semantics

The asynchronous response pattern used by lambda services. When a job exceeds `max_wait_time`, the server returns `204 No Content` with `Location` and `Retry-Later` headers so the caller can poll `GET /jobs/{job_id}` later.

## Event / Progress Event

A message sent during tool execution to report progress, errors, or other status information back to the IVCAP platform. Emitted via `JobContext.report`.

## Step

A named phase of tool execution. Steps are reported as structured events with start, optional info updates, and finish markers.

## MCP (Model Context Protocol)

An open standard for AI agents to discover and call tools. The `--with-mcp` flag enables an `/mcp` endpoint on the lambda server that speaks the MCP protocol.

## Request / Result Models

Pydantic `BaseModel` subclasses that define the input (Request) and output (Result) of a tool. Must be decorated with `@with_schema` from `ivcap_service`.

## Schema URN

A `urn:` identifier attached to request/result models via `@with_schema`. Used by the IVCAP platform to identify payload types. Format: `urn:{namespace}:schema:{name}.{version}`.

## ExecutorOpts

Configuration for the per-tool `Executor`: thread pool size, job result cache size, and cache TTL.

## Sidecar Reporter

The component (from `ivcap-service`) that forwards progress events from the tool's execution thread to the IVCAP platform sidecar via HTTP.

## OpenTelemetry / OTEL

An open standard for exporting logs, metrics, and traces. Enabled with `--with-telemetry`; the FastAPI app is automatically instrumented.

## URN

Uniform Resource Name. IVCAP uses URNs to identify resources. Format: `urn:ivcap:{type}:{uuid}`.

## See Also

- [API Reference](../api/overview.md)
- [Getting Started](../getting-started/quick-start.md)
- [ivcap-service Glossary](https://ivcap-works.github.io/ivcap-service-sdk-python/reference/glossary/)
