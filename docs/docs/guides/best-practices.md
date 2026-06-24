# Best Practices

Production patterns and tips for building high-quality IVCAP lambda services.

## Code Organization

### Minimal File Layout

```
my-service/
├── pyproject.toml       # Project & ivcap plugin config
├── my_service.py        # Tool implementation (entry point)
├── Dockerfile
├── tests/
│   ├── call-greet.json  # Test payloads for ivcap run
│   └── call-process.json
└── README.md
```

### Larger Projects

```
my-service/
├── pyproject.toml
├── my_service.py        # Entry point — imports and registers tools
├── tools/
│   ├── __init__.py
│   ├── greet.py         # Individual tool modules
│   └── process.py
├── models/
│   ├── __init__.py
│   ├── greet.py         # Request/Result Pydantic models
│   └── process.py
├── Dockerfile
└── tests/
```

## Request & Result Models

- **Use `@with_schema("urn:...")`** on every model — never add `$schema` manually
- **Write descriptions for every field** — agents use these to understand the API
- **Use sensible defaults** — mark truly required fields with `Field(...)`
- **Add validators** for complex constraints using `@field_validator`
- **Keep schemas versioned** — e.g. `my-service.request.1`, `my-service.request.2`

```python
@with_schema("urn:my-service:schema:analyse.request.1")
class AnalyseRequest(BaseModel):
    """Request to run text analysis."""
    text: str = Field(..., description="Text to analyse. Must not be empty.", min_length=1)
    language: str = Field("en", description="ISO 639-1 language code (default: en).")
    max_tokens: int = Field(512, description="Maximum tokens to process.", ge=1, le=8192)
```

## Tool Function Design

- **Write comprehensive docstrings** — the first paragraph becomes the Swagger summary; the rest is the description shown to agents
- **Keep tools focused** — one clear purpose per tool
- **Accept `JobContext` when you need progress reporting or artifact access**
- **Don't store per-job state at module level** — tools may run concurrently

```python
@ivcap_lambda("/analyse", opts=ToolOptions(tags=["NLP"], service_id="/analyse"))
def analyse(req: AnalyseRequest, jobCtxt: JobContext) -> AnalyseResult:
    """Analyse text for key entities and sentiment

    Processes the provided text and returns a list of named entities
    (people, places, organisations) and an overall sentiment score.

    Use this tool when you need to extract structured information from
    natural-language text. Supports English, French, and German.
    """
    ...
```

## Performance

### Use a Fixed Thread Pool for Heavy Tools

By default, a new thread is created per job. For tools with high startup cost (e.g. model loading), use a fixed thread pool:

```python
from ivcap_lambda.executor import ExecutorOpts

@ivcap_lambda(
    "/predict",
    opts=ToolOptions(executor_opts=ExecutorOpts(max_workers=2))
)
def predict(req: PredictRequest) -> PredictResult:
    ...
```

### Cache Expensive Resources at Module Level

Load models once at startup, not per-job:

```python
# Module level — loaded once
_model = None

def _load_model():
    global _model
    _model = load_my_model("model.pkl")
    logger.info("Model loaded")

# Call at startup before start_lambda_server
_load_model()

@ivcap_lambda("/predict")
def predict(req: PredictRequest) -> PredictResult:
    return PredictResult(label=_model.predict(req.text))
```

### Report Progress on Long Jobs

Users and the IVCAP platform benefit from knowing job status. Always use steps for operations that take more than a second:

```python
with jobCtxt.report.step("inference", "Running inference...") as step:
    result = run_model(data)
    step.finished(f"Score: {result.score:.3f}")
```

## Testing

### Test JSON Files

Create JSON test files in a `tests/` directory matching the request schema:

```json
{
  "$schema": "urn:my-service:schema:analyse.request.1",
  "text": "Hello, IVCAP!",
  "language": "en"
}
```

Use the IVCAP CLI to test:

```bash
ivcap run --test-file tests/call-analyse.json
```

Or call the running service directly:

```bash
curl -X POST http://localhost:8090/analyse \
  -H "content-type: application/json" \
  -d @tests/call-analyse.json
```

### Unit Testing Without HTTP

Test tool logic directly without starting the server:

```python
# tests/test_analyse.py
from my_service import analyse, AnalyseRequest

def test_analyse_basic():
    req = AnalyseRequest(text="Hello world", language="en")
    result = analyse(req)
    assert result.word_count == 2
```

## Documentation

- **Write a clear README** with installation, usage, and example calls
- **Include sample test JSON files** in the `tests/` directory
- **Document environment variables** your service requires
- **Keep AGENTS.md up to date** — agents use it to understand how to build services

## Security

- **Never log authorization headers or tokens** at `INFO` or `DEBUG` level
- **Validate all user inputs** with Pydantic constraints before processing
- **Use `SecretMgrClient`** (from `ivcap_service`) for secrets rather than environment variables where possible
- **Don't expose internal error details** in `ValueError` messages shown to users

## Common Pitfalls

| Pitfall | Solution |
|---------|---------|
| Module-level state mutated per-job | Use `contextvars` or pass state explicitly |
| Forgetting `@with_schema` | Always decorate request/result models |
| No docstring on tool function | Agents see an empty description; always write one |
| Blocking the event loop in async tools | Use `await asyncio.to_thread()` for blocking calls |
| Unbounded job cache | Set `ExecutorOpts(job_cache_size=N)` for high-traffic tools |

## Troubleshooting

### Service won't start

Check that `logging_init()` is called before `start_lambda_server()`, and that at least one `@ivcap_lambda` tool is registered.

### Tool not visible in Swagger

The path must start with `/`. Check `@ivcap_lambda("/my-tool", ...)`.

### Jobs always return 204

Your tool is taking longer than `max_wait_time` (default 5 s). Increase it in `ToolOptions` or switch clients to the async polling pattern.

### Pydantic validation errors on startup

Ensure all `@with_schema` decorators reference valid URN strings and that you're not adding a `$schema` field manually.

## See Also

- [Tool Functions Guide](tool-functions.md) — Decorator usage
- [Error Handling Guide](error-handling.md) — Robust patterns
- [Deployment Guide](deployment.md) — Production configuration
- [API Reference](../api/overview.md) — Complete API docs
