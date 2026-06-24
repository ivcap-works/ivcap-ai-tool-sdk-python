# Types

Helper types and models used across `ivcap_lambda`.

## Error Response Models

These models are used internally by the framework to serialise error responses:

::: ivcap_lambda.builder.ErrorModel

::: ivcap_lambda.builder.ExecutionErrorModel

## Job Context (from ivcap-service)

`JobContext` is provided by the base `ivcap_service` library and is injected into your tool function automatically. Refer to the [ivcap-service API docs](https://ivcap-works.github.io/ivcap-service-sdk-python/api/job-context/) for the full reference.

Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | `str` | Unique job identifier (URN format) |
| `report` | `EventReporter` | For emitting progress events |
| `job_authorization` | `str \| None` | Bearer token for downstream calls |
| `ivcap` | `IVCAP` | IVCAP client for platform APIs |

## WorkerFn

The type alias for a tool worker function:

```python
WorkerFn = Callable[[BaseModel, ExecutionContext | None, Response | None], BaseModel]
```

In practice, the framework inspects type annotations to inject `JobContext`, `ExecutionContext`, and `fastapi.Request` parameters by type, so your function signature just needs the right type hints.
