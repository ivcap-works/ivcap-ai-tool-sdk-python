# Installation

## Prerequisites

- Python 3.11 or higher
- pip or poetry package manager

## From PyPI

The easiest way to install the IVCAP Lambda SDK:

```bash
pip install ivcap-lambda
```

Or with poetry:

```bash
poetry add ivcap-lambda
```

!!! note "Package rename"
    The original package name `ivcap-ai-tool` has been renamed to `ivcap-lambda`. A
    compatibility shim is still published under the old name and will emit a
    `DeprecationWarning`. Please migrate imports to `ivcap_lambda`.

## From Source

For development or to use the latest unreleased features:

```bash
git clone https://github.com/ivcap-works/ivcap-ai-tool-sdk-python.git
cd ivcap-ai-tool-sdk-python
poetry install
```

## Verify Installation

Test your installation:

```bash
python -c "import ivcap_lambda; print(ivcap_lambda.__version__)"
```

You should see the version number printed.

## Dependencies

`ivcap-lambda` depends on:

| Package | Purpose |
|---------|---------|
| `ivcap-service` | Base service primitives, `Service`, `JobContext`, events, logging |
| `fastapi` | HTTP framework for tool endpoints |
| `uvicorn` | ASGI server |
| `pydantic` | Request/result model validation |
| `opentelemetry-instrumentation-fastapi` | Distributed tracing |

All dependencies are installed automatically.

## Optional: Development Dependencies

If you plan to contribute or build documentation locally:

```bash
# Development tools
poetry install --with dev

# Documentation tools
pip install -r docs/requirements-docs.txt
```

## Next Steps

- Read the [Quick Start](quick-start.md) guide
- Build your [First Lambda Service](first-service.md)
- Check out [Examples](../examples/tool-service.md)

## Troubleshooting

### ImportError: No module named 'ivcap_lambda'

Make sure you've installed the package:
```bash
pip install ivcap-lambda
```

If using a virtual environment, ensure it's activated.

### Python Version Error

Check your Python version:
```bash
python --version
```

The SDK requires Python 3.11+. If you have multiple Python versions installed, use:
```bash
python3.11 -m pip install ivcap-lambda
```

### Permission Denied

If you get permission errors during installation, use:
```bash
pip install --user ivcap-lambda
```

## Getting Help

- Check [Best Practices](../guides/best-practices.md#troubleshooting)
- [Open an issue](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/issues)
- See [Contributing](../community/contributing.md)
