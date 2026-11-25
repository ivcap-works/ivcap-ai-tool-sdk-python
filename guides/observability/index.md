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

## The Event Reporter, Steps and Tracing

Every job gets a `JobContext`. Declare it as a parameter and the SDK injects it; leave it out if the tool doesn't need it:

```python
from ivcap_service import JobContext

@ivcap_lambda("/summarise")
def summarise(req: SummariseRequest, jobCtxt: JobContext) -> SummariseResult:
    ...
```

`JobContext` has three useful fields:

- `job_id`: the ID of this job.
- `report`: the event reporter. Use it to send progress to the platform.
- `ivcap`: the IVCAP client, for artifacts and secrets.

The canonical way to report progress is a **step**. A step is a context manager:

```python
with jobCtxt.report.step("my-step", "Doing the work") as step:
    result = do_work()
    step.finished("Work done")
```

Each step does two things at once:

1. **Sends IVCAP events** to the platform: a start event when the block is entered, and a finish event when it exits. `step.finished(...)` sets the message and any extra fields on that finish event. If you don't call it, a default finish event is sent on exit.
2. **Creates an OpenTelemetry span** named `ivcap.event:<step name>`. It is a child of the job's `RUN <tool name>` span, so it appears in your traces under the job. The step's `message` and any extra keyword arguments become span attributes (`ivcap.event.<key>`). Values that OTel can't represent, such as dicts, are skipped.

If the block raises an exception, the step:

- sends a step error event with the exception text and traceback,
- records the exception on its span and marks the span as `ERROR`,
- re-raises the exception, so the job fails as normal.

To send an intermediate update without ending the step, call `step.info(...)` with a `GenericEvent` or a dict. Intermediate updates are events only; they don't create extra spans.

This works the same over MCP: the tool's `JobContext` reports its steps through the MCP progress channel instead of the IVCAP sidecar. Tool code doesn't change.

### Reporting Without a Step

For a one-off event, use the reporter directly. This sends an event but creates no span:

```python
from ivcap_service.events import GenericEvent

jobCtxt.report.emit(GenericEvent(name="cache-miss", options={"key": key}))
```

### Where the Reporter Comes From

You usually don't create the reporter yourself. For REST jobs, the executor builds it per job and sends events to the IVCAP sidecar. For MCP tool calls, it's an MCP-backed reporter tied to that call. Either way, `jobCtxt.report` has the same interface, so the same step code works in both.

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

Exporter/provider setup is supplied by the underlying `ivcap-service` SDK and
is initialized automatically by `start_lambda_server()`. A standard OTLP
endpoint is sufficient to export logs, metrics, and traces:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4318"
python my_service.py
```

OpenObserve-specific variables are optional and add authentication, routing,
and endpoint information:

```bash
export OPENOBSERVE_URL="https://observe.example.com"
export OPENOBSERVE_ORG="myorg"
export OPENOBSERVE_USERNAME="service@example.com"
export OPENOBSERVE_TOKEN="<api-token>"
```

All logs via `getLogger()` are then exported automatically. No
`opentelemetry-instrument` wrapper or code changes are required.

See the [`ivcap-service` OpenTelemetry / OpenObserve
integration](https://ivcap-works.github.io/ivcap-service-sdk-python/guides/observability/#opentelemetry--openobserve-integration)
for the authoritative exporter behavior and configuration model.

## OpenTelemetry Tracing

For how steps map onto spans, see [The Event Reporter, Steps and Tracing](#the-event-reporter-steps-and-tracing).

Setting `OTEL_EXPORTER_OTLP_ENDPOINT` automatically enables tracing and
FastAPI instrumentation; no CLI flag is normally needed:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4318"
python my_service.py --port 8090
```

Use `--with-telemetry` to force-enable instrumentation when no endpoint is
configured, or `--without-telemetry` to force-disable framework and outbound
HTTP instrumentation. CLI flags take precedence over the
`with_telemetry` argument, which takes precedence over endpoint-based
auto-detection. Exporter configuration remains environment-driven.

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

The `/_healtz` endpoint is automatically registered. It describes the whole service. When the service is ready, it returns the service name and version from the `Service` object, the versions of `ivcap-lambda` and `ivcap-service` under `libraries`, plus any info published by functions marked with `@ivcap_health_info`:

```bash
curl http://localhost:8090/_healtz
# {"model": "resnet-50", "name": "cas9-ivcap", "version": "0.1.0", "libraries": {...}}
```

The `version` value is resolved in this order: the `VERSION` environment variable, then `Service.version`, then `???`.

`/_healtz` returns `503 Service Unavailable` while the service is not ready, for example until an `on_startup` function given to `start_lambda_server` has completed. A tool's own `is_ready` check does not affect `/_healtz`; it only gates that tool's endpoint. See [Tool Readiness](tool-functions.md#tool-readiness).

Use this for Kubernetes readiness probes. For liveness probes, prefer a TCP check so that a slow model load does not cause the pod to be restarted.

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
- [`ivcap-service` Observability Guide](https://ivcap-works.github.io/ivcap-service-sdk-python/guides/observability/#opentelemetry--openobserve-integration) — Authoritative exporter and OpenObserve configuration
