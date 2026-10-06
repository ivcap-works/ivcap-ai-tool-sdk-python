# ivcap-lambda: Python SDK for Lambda-Style IVCAP Services

> **Package renamed:** `ivcap-ai-tool` has been renamed to `ivcap-lambda` to reflect that
> the library is useful for any lambda-style IVCAP service, not just AI agent tools.
> A [compatibility shim](./compat/) is published under the old name — existing apps
> will continue to work but will see a `DeprecationWarning` prompting migration.

<a href="https://scan.coverity.com/projects/ivcap-works-ivcap-ai-tool-sdk-python">
  <img alt="Coverity Scan Build Status"
       src="https://img.shields.io/coverity/scan/31491.svg"/>
</a>

`ivcap-lambda` is a Python library that turns a plain Python function into a set of
**IVCAP-compatible HTTP endpoints** and/or a **spec-compliant MCP (Model Context
Protocol) server**, from the same tool code. It sits on top of
[`ivcap-service`](https://pypi.org/project/ivcap-service/) and
[FastAPI](https://fastapi.tiangolo.com/), and handles:

- Registering tool functions as HTTP endpoints (with async "try-later" semantics)
- Job execution in threads, result caching, and graceful shutdown
- Event/progress reporting back to the IVCAP platform
- Automatic tool-description endpoints (for AI agents) and an optional MCP endpoint
  (built on the official [`mcp`](https://pypi.org/project/mcp/) Python SDK)

**📖 Full documentation:** <https://ivcap-works.github.io/ivcap-ai-tool-sdk-python/>

**🚀 New to the library?** Depending on your goal:

- Building a service for the **IVCAP platform** (MCP optional) → see
  [AGENTS.md, Track A](./AGENTS.md#track-a-ivcap-lambda-service) or the
  [Quick Start guide](https://ivcap-works.github.io/ivcap-ai-tool-sdk-python/getting-started/quick-start/)
- Building an **MCP server** first, with IVCAP deployment as a bonus → see
  [AGENTS.md, Track B](./AGENTS.md#track-b-mcp-first-server) or the
  [MCP guide's MCP-first section](https://ivcap-works.github.io/ivcap-ai-tool-sdk-python/guides/mcp/#mcp-first-development)
- A ready-to-clone starter project →
  [ivcap-python-ai-tool-template](https://github.com/ivcap-works/ivcap-python-ai-tool-template)

---

## Installation

```bash
pip install ivcap-lambda

# To also expose tools as an MCP server:
pip install ivcap-lambda[mcp]
```

## Minimal Example

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

Run and test it:

```bash
python my_service.py --port 8090
curl -X POST http://localhost:8090/ -H "content-type: application/json" -d '{"message": "Hello, IVCAP!"}'

# Or, with the mcp extra installed, run the exact same tool as an MCP server instead:
python my_service.py --with-mcp-stdio
```

For everything else — defining tools, `ToolOptions`, `JobContext`, progress
reporting, artifacts, MCP, project layout, deployment, Docker — see the
**[full documentation](https://ivcap-works.github.io/ivcap-ai-tool-sdk-python/)**
and **[AGENTS.md](./AGENTS.md)**. This README intentionally stays limited to
installation/quick-start plus notes for anyone working on `ivcap-lambda`
itself (below), to avoid duplicating content that's already maintained in the
docs site.

---

## Migration from `ivcap-ai-tool`

| Old (deprecated) | New |
|---|---|
| `pip install ivcap-ai-tool` | `pip install ivcap-lambda` |
| `from ivcap_ai_tool import ...` | `from ivcap_lambda import ...` |
| `@ivcap_ai_tool(...)` | `@ivcap_lambda(...)` |

The old `ivcap-ai-tool` package is a compatibility shim that re-exports everything from `ivcap-lambda`. It will emit a `DeprecationWarning` at import time. No code changes beyond the import are required.

---

## Contributing / Developing `ivcap-lambda` Itself

The sections below are for anyone extending, fixing, or releasing this
library — not for consumers of the package. See also
[CONTRIBUTING.md](./CONTRIBUTING.md), [DESIGN.md](./DESIGN.md) (internal
architecture), and [CONDUCT.md](./CONDUCT.md).

### Repository Layout

```
ivcap-ai-tool/
├── ivcap_lambda/    # the library itself
├── compat/          # ivcap-ai-tool deprecation shim (old package name)
├── docs/            # MkDocs documentation site (docs/docs) + build output (docs/site)
├── examples/        # runnable example services (test-tool, test-mcp)
├── tests/           # unit tests
├── AGENTS.md        # user-facing reference for AI coding agents
├── DESIGN.md        # internal architecture & design rationale
└── pyproject.toml
```

### Setup, Tests & Checks

```bash
poetry install
make test    # pytest --cov=ivcap_lambda
make check   # test + ruff check + mypy
```

### Running the Example Services

```bash
cd examples/test-tool && poetry install && make run   # REST example
cd examples/test-mcp  && poetry install && make run   # MCP example (HTTP)
cd examples/test-mcp  && make run-mcp-stdio            # MCP example (stdio)
```

### Building & Serving the Documentation Site

```bash
make docs-serve   # live-reload at a random local port
make docs-build   # build static site into docs/site
```

### Releasing

Versioning/publishing is driven by `semantic_release` config in
`pyproject.toml` on `main`. `make build` / `make publish` wrap `poetry
build`/`poetry publish`.

### License

Licensed under the BSD-style license in [LICENSE](./LICENSE). See
[AUTHORS.md](./AUTHORS.md) for contributors.
