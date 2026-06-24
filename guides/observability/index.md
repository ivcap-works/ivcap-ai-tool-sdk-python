# Observability & Logging Guide

Monitor and debug your lambda services with structured logging, progress events, and distributed tracing.

## Structured Logging

Initialize logging at startup with `logging_init` (from `ivcap_lambda`) and use `getLogger` (from `ivcap_service`):

```python
from ivcap_lambda import logging_init
from ivcap_service import getLogger

logging_init()
logger = getLogger("my_service")

logger.info("Service started")
logger.warning("Warning message")
logger.error("Error occurred", exc_info=True)
```

!!! note "Import paths"
    `logging_init` comes from `ivcap_lambda` (it sets up uvicorn-compatible structured logging).
    `getLogger` comes from `ivcap_service` (the base library shared with batch services).

## Job-Specific Logging

Log with job context for easier filtering in log aggregation:

```python
from ivcap_service import JobContext

@ivcap_lambda("/process")
def process(req: MyRequest, jobCtxt: JobContext) -> MyResult:
    job_logger = getLogger(f"process.{jobCtxt.job_id[:8]}")
    job_logger.info("Starting processing")
    ...
```

## Progress Reporting with Steps

Use `jobCtxt.report.step()` to report structured progress back to the IVCAP platform. Steps are the recommended way to track long-running operations:

```python
@ivcap_lambda("/analyse")
def analyse(req: AnalyseRequest, jobCtxt: JobContext) -> AnalyseResult:
    """Analyse data"""
    with jobCtxt.report.step("load", "Loading data...") as step:
        data = load_data(req.source)
        step.finished(f"Loaded {len(data)} records")

    with jobCtxt.report.step("process", "Processing records") as step:
        results = []
        for i, record in enumerate(data):
            results.append(process_record(record))
            if i % 100 == 0:
                from ivcap_service.events import GenericEvent
                step.info(GenericEvent(
                    name="progress",
                    options={"processed": i, "total": len(data)}
                ))
        step.finished(f"Processed {len(results)} records")

    return AnalyseResult(count=len(results))
```

## Emitting Events Directly

For fine-grained control, emit events without a step context manager:

```python
from ivcap_service.events import GenericEvent, GenericErrorEvent

@ivcap_lambda("/pipeline")
def pipeline(req: PipelineRequest, jobCtxt: JobContext) -> PipelineResult:
    """Run analysis pipeline"""
    report = jobCtxt.report

    # Start a named step
    report.step_started("init", msg="Initialising pipeline")
    try:
        init_pipeline()
        report.step_finished("init", msg="Pipeline ready")
    except Exception as e:
        report.step_error("init", error=str(e), context="Init failed")
        raise

    # Emit a one-off generic event
    report.emit(GenericEvent(name="pipeline-started", options={"version": "2.0"}))
    ...
```

## Available Event Types

From `ivcap_service.events`:

| Class | Schema URI | Use |
|---|---|---|
| `GenericEvent(name, options)` | `urn:ivcap:schema:service.event.generic.1` | General-purpose named event |
| `GenericErrorEvent(error, context, stacktrace)` | `urn:ivcap:schema:service.event.error.1` | Error/exception reporting |

Custom events can be created by subclassing `BaseEvent` and defining a `SCHEMA` class variable.

## OpenObserve Integration

Configure environment variables to export logs and metrics automatically:

```bash
export OPENOBSERVE_URL="https://observe.example.com"
export OPENOBSERVE_ORG="myorg"
export OPENOBSERVE_USERNAME="service@example.com"
export OPENOBSERVE_TOKEN="<api-token>"
```

All logs via `getLogger()` are automatically sent to OpenObserve. No code changes required.

## OpenTelemetry Tracing

Enable distributed tracing with the `--with-telemetry` flag:

```bash
python my_service.py --with-telemetry --port 8090
```

Configure the OTLP exporter endpoint:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4318"
```

The SDK automatically:

- Creates spans for each HTTP request (FastAPI instrumentation)
- Creates a span per job execution with `job.id` and `job.name` attributes
- Records job outcomes (success/error) including exception details
- Propagates trace context across thread-pool boundaries

You can also control telemetry programmatically:

```python
# Force-enable telemetry
start_lambda_server(service, with_telemetry=True)

# Force-disable telemetry (e.g. in tests)
start_lambda_server(service, with_telemetry=False)
```

## Getting the Current Event Reporter

In code that doesn't have direct access to `JobContext`, use the helpers from `ivcap_lambda`:

```python
from ivcap_lambda import get_event_reporter, get_job_id

def some_helper():
    reporter = get_event_reporter()
    if reporter:
        reporter.emit(GenericEvent(name="helper-called", options={}))

    job_id = get_job_id()
    logger.debug(f"Running in job {job_id}")
```

These helpers read the job context from the current thread's context variable, so they work correctly in the thread-pool execution environment.

## Health Check

The `/_healtz` endpoint is automatically registered and returns the running service version:

```bash
curl http://localhost:8090/_healtz
# {"version": "1.2.3"}
```

Use this for Kubernetes liveness/readiness probes.

## Best Practices

1. **Call `logging_init()` once at module level** — before any loggers are created
2. **Use `getLogger("component-name")`** for module-specific loggers, not the root logger
3. **Report progress with steps** — wrapping work in `report.step()` helps users and agents understand execution state
4. **Include context in log messages** — `job_id`, input sizes, key parameters
5. **Log at appropriate levels** — `DEBUG` for internal state, `INFO` for milestones, `WARNING` for unexpected-but-handled, `ERROR` for failures

## See Also

- [Events API](../api/types.md) — `EventReporter` and event classes
- [Utilities API](../api/utilities.md) — `get_event_reporter`, `get_job_id`
- [Error Handling Guide](error-handling.md) — Reporting errors
- [Best Practices](best-practices.md) — Production patterns
- [Environment Variables](../reference/environment-variables.md) — OpenObserve and OTEL configuration
