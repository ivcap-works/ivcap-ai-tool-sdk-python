# Advanced Patterns

Advanced usage patterns for production IVCAP lambda services.

## Model Loading with Readiness Check

Load a machine-learning model at startup and prevent the health check from succeeding until loading is complete:

```python
import time
from ivcap_lambda import ivcap_lambda, ToolOptions, start_lambda_server, logging_init
from ivcap_service import Service, ServiceContact, with_schema, getLogger

logging_init()
logger = getLogger("ml_service")

service = Service(
    name="ML Inference Service",
    contact=ServiceContact(name="ML Team", email="ml@example.com"),
)

# ── Model loading ─────────────────────────────────────────────────────────────

_model = None
_model_ready = False

def is_ready() -> bool:
    return _model_ready

def load_model():
    global _model, _model_ready
    logger.info("Loading model…")
    time.sleep(2)  # simulate load
    _model = {"type": "mock"}
    _model_ready = True
    logger.info("Model ready")


@with_schema("urn:example:schema:predict.request.1")
class PredictRequest(BaseModel):
    text: str = Field(..., description="Text to classify.")


@with_schema("urn:example:schema:predict.1")
class PredictResult(BaseModel):
    label: str = Field(..., description="Predicted label.")
    confidence: float = Field(..., description="Confidence score (0–1).", ge=0, le=1)


@ivcap_lambda(
    "/predict",
    opts=ToolOptions(tags=["ML"], is_ready=is_ready, max_wait_time=30.0),
)
def predict(req: PredictRequest) -> PredictResult:
    """Classify text using the loaded model

    Returns a label and confidence score for the provided text.
    The service will report 503 until the model is fully loaded.
    """
    # Use the pre-loaded model
    label = "positive" if len(req.text) % 2 == 0 else "negative"
    return PredictResult(label=label, confidence=0.95)


# Load model at module level, before start_lambda_server
load_model()

if __name__ == "__main__":
    start_lambda_server(service)
```

## Custom CLI Arguments

Add service-specific command-line flags:

```python
import argparse
import os
from ivcap_lambda import start_lambda_server

def parse_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    parser.add_argument(
        "--model-path",
        type=str,
        default=os.environ.get("MODEL_PATH", "model.pkl"),
        help="Path to the model file",
    )
    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=int(os.environ.get("CACHE_TTL", "3600")),
        help="Job result cache TTL in seconds",
    )
    args = parser.parse_args()
    # Propagate to environment for later use
    os.environ["MODEL_PATH"] = args.model_path
    os.environ["CACHE_TTL"] = str(args.cache_ttl)
    return args

if __name__ == "__main__":
    start_lambda_server(service, custom_args=parse_args)
```

## Shared Execution Context

Pass a shared context object to every tool invocation:

```python
from ivcap_lambda import ivcap_lambda, ToolOptions
from ivcap_lambda.executor import ExecutionContext

class DatabaseContext(ExecutionContext):
    def __init__(self, db_url: str):
        self.db = connect(db_url)

db_context = DatabaseContext(db_url="sqlite:///my.db")

@ivcap_lambda(
    "/lookup",
    opts=ToolOptions(tags=["Data"]),
    context=db_context,
)
def lookup(req: LookupRequest, ctx: DatabaseContext) -> LookupResult:
    """Look up a record in the database"""
    record = ctx.db.query(req.id)
    return LookupResult(data=record)
```

## Registering Routes Programmatically

Use `add_tool_api_route` instead of the decorator when you want to register tools in a loop or factory:

```python
from ivcap_lambda.builder import add_tool_api_route, ToolOptions
from ivcap_lambda.server import get_fast_app

app = get_fast_app()

for tool_name, handler, request_cls, result_cls in tool_definitions:
    add_tool_api_route(
        app,
        f"/{tool_name}",
        handler,
        opts=ToolOptions(tags=[tool_name.title()]),
    )
```

## Streaming Progress with Fine-Grained Events

Emit detailed progress events for long-running batch operations:

```python
from ivcap_service.events import GenericEvent

@ivcap_lambda("/batch-process")
def batch_process(req: BatchRequest, jobCtxt: JobContext) -> BatchResult:
    """Process a batch of items"""
    total = len(req.items)
    results = []

    with jobCtxt.report.step("process", f"Processing {total} items") as step:
        for i, item in enumerate(req.items):
            result = process_item(item)
            results.append(result)

            # Emit progress every 10 items
            if (i + 1) % 10 == 0 or (i + 1) == total:
                step.info(GenericEvent(
                    name="batch-progress",
                    options={
                        "processed": i + 1,
                        "total": total,
                        "pct": round((i + 1) / total * 100, 1),
                    },
                ))
        step.finished(f"Processed {total} items")

    return BatchResult(results=results, count=total)
```

## Using Secrets

Access platform secrets via `SecretMgrClient` (from `ivcap_service`):

```python
from ivcap_service.secret import SecretMgrClient

_secret_client = SecretMgrClient()

@ivcap_lambda("/call-api")
def call_api(req: ApiRequest, jobCtxt: JobContext) -> ApiResult:
    """Call an external API using a stored secret"""
    api_key = _secret_client.get_secret("external-api-key")
    response = requests.get(
        req.url,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return ApiResult(status=response.status_code, body=response.text)
```

## See Also

- [Tool Functions Guide](../guides/tool-functions.md)
- [Deployment Guide](../guides/deployment.md)
- [Best Practices](../guides/best-practices.md)
- [API Reference: Executor & Options](../api/executor.md)
