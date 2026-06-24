# Error Handling Guide

Lambda tool functions are executed in a thread pool inside a `try/except` block. Unhandled exceptions are caught, serialised, and returned as error responses to the caller.

## Automatic Exception Handling

Any exception raised from your tool function is automatically converted to an error response:

- **`ValueError`** → `400 Bad Request` with `{"message": "...", "code": 400}`
- **Any other exception** → `500 Internal Server Error` with `{"$schema": "urn:ivcap:schema.ai-tool.error.1", "message": "...", "traceback": "..."}`

```python
@ivcap_lambda("/divide")
def divide(req: DivideRequest) -> DivideResult:
    """Divide two numbers"""
    if req.divisor == 0:
        raise ValueError("divisor must not be zero")  # → 400
    return DivideResult(result=req.dividend / req.divisor)
```

## Reporting Errors via Events

For errors that occur inside a named step, report them through the event system so the IVCAP platform can track what went wrong:

```python
from ivcap_service import JobContext
from ivcap_service.events import GenericErrorEvent
import traceback

@ivcap_lambda("/process")
def process(req: ProcessRequest, jobCtxt: JobContext) -> ProcessResult:
    """Process data"""
    with jobCtxt.report.step("load", "Loading data") as step:
        try:
            data = load_data(req.source)
            step.finished(f"Loaded {len(data)} records")
        except FileNotFoundError as e:
            step.error(e)  # marks step as failed
            raise ValueError(f"Data source not found: {req.source}") from e

    with jobCtxt.report.step("process", "Processing") as step:
        try:
            result = process_data(data)
            step.finished("Done")
        except Exception as e:
            # Report detailed error event
            jobCtxt.report.emit(GenericErrorEvent(
                error=str(e),
                context="process step failed",
                stacktrace=traceback.format_exc(),
            ))
            step.error(e)
            raise

    return ProcessResult(output=result)
```

## Graceful Degradation

For optional features, catch specific exceptions and fall back gracefully:

```python
@ivcap_lambda("/enrich")
def enrich(req: EnrichRequest, jobCtxt: JobContext) -> EnrichResult:
    """Enrich data with optional external lookup"""
    base_result = compute_base(req)

    # Optional enrichment — fail gracefully
    enrichment = None
    try:
        enrichment = call_external_api(req.id)
    except Exception as e:
        logger.warning(f"Enrichment failed (continuing without): {e}")

    return EnrichResult(
        data=base_result,
        enrichment=enrichment,
    )
```

## Input Validation

Use Pydantic's built-in validation to reject bad inputs before your function runs:

```python
from pydantic import BaseModel, Field, field_validator

@with_schema("urn:example:schema:resize.request.1")
class ResizeRequest(BaseModel):
    artifact_id: str = Field(..., description="Artifact to resize.")
    width: int = Field(..., description="Target width in pixels.", ge=1, le=4096)
    height: int = Field(..., description="Target height in pixels.", ge=1, le=4096)
    format: str = Field("jpeg", description="Output format.")

    @field_validator("format")
    @classmethod
    def format_must_be_valid(cls, v):
        if v.lower() not in ("jpeg", "png", "webp"):
            raise ValueError("format must be jpeg, png, or webp")
        return v.lower()
```

Pydantic validation errors result in a `422 Unprocessable Entity` response from FastAPI, before your function is even called.

## HTTP Error Codes Summary

| Situation | HTTP Status | Body |
|-----------|-------------|------|
| Pydantic validation fails | `422` | FastAPI validation error |
| `ValueError` raised | `400` | `{"message": "...", "code": 400}` |
| Other exception raised | `500` | `{"$schema": "...", "message": "...", "traceback": "..."}` |
| Job still running | `204` | _(empty, Location + Retry-Later headers)_ |
| Job ID not found or expired | `404` | _(plain text message)_ |
| Job completed successfully | `200` | _(result model JSON)_ |

## Best Practices

1. **Raise `ValueError` for user errors** — bad input that the user should fix
2. **Raise other exceptions for system errors** — unexpected failures the user can't fix
3. **Use steps to track where failures occur** — `step.error(e)` marks the step as failed on the platform
4. **Log the exception at `ERROR` level** — before re-raising, so it appears in logs
5. **Don't swallow exceptions silently** — at minimum log a warning so failures are visible

## See Also

- [Tool Functions Guide](tool-functions.md) — Try-later semantics and HTTP status codes
- [Observability Guide](observability.md) — Progress reporting and event types
- [Best Practices](best-practices.md) — Robust error patterns
