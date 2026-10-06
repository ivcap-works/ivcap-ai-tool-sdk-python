# MCP & Agent Integration Guide

`ivcap-lambda` tools can be exposed as a spec-compliant [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server — built on the official [`mcp`](https://pypi.org/project/mcp/) Python SDK, not a custom reimplementation — making them directly callable by AI agent frameworks and MCP hosts such as Claude Desktop, Cursor, Cline, and others.

This guide covers both ways people arrive at MCP support:

- **[I have (or am building) an IVCAP lambda service and want to add MCP](#adding-mcp-to-an-ivcap-lambda-service)** — MCP is an add-on, zero code changes
- **[I'm building an MCP server first, and IVCAP deployment is a bonus](#mcp-first-development)** — start from an MCP-only mindset

See also [AGENTS.md](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/AGENTS.md) (Track A / Track B) for the same split aimed at AI coding agents.

## What is MCP?

The Model Context Protocol is an open standard that lets AI models discover and call tools via a standardised interface, supporting both HTTP (Streamable-HTTP) and stdio transports. By enabling MCP, your `ivcap-lambda` service becomes a first-class tool provider for any MCP-compatible host, in addition to (or instead of) being an IVCAP REST tool.

## Adding MCP to an IVCAP Lambda Service

Install the optional `mcp` extra, then pass `--with-mcp` when starting the server:

```bash
pip install ivcap-lambda[mcp]
python my_service.py --with-mcp --port 8090
```

This mounts a `/mcp` endpoint (Streamable-HTTP transport) on the running FastAPI app, alongside your existing REST endpoints. It speaks the MCP protocol and exposes every registered `@ivcap_lambda` tool automatically — no changes are required in tool code.

### Running as a stdio MCP server

For local development with stdio-based MCP hosts (Claude Desktop, Cline, the MCP Inspector's stdio mode) that launch your tool as a subprocess instead of connecting over HTTP, use `--with-mcp-stdio` instead of `--with-mcp`. This skips the FastAPI/uvicorn HTTP server entirely — no REST, Swagger, or health endpoints are started:

```bash
python my_service.py --with-mcp-stdio
```

`--with-mcp` and `--with-mcp-stdio` are mutually exclusive. Tool registration, schema generation, and progress-notification bridging are identical either way — the same tool code works unchanged over both transports.

### Sync and async tool functions both work over MCP

A tool function registered with `@ivcap_lambda` can be either a plain `def` or an `async def` — this is detected automatically (via `asyncio.iscoroutinefunction`) and handled transparently by the same `Executor` regardless of which transport (REST or MCP) the call came in on:

```python
@ivcap_lambda("/greet-async", opts=ToolOptions(tags=["Greeter"]))
async def greet_async(req: GreetRequest) -> GreetResult:
    """Greet a person asynchronously"""
    await asyncio.sleep(0)  # yield once
    return GreetResult(greeting=f"Hello, {req.name}!")
```

Calling `greet_async` over MCP's `tools/call` works exactly like calling a synchronous tool — no special handling, `await`, or extra configuration is required on the client side. See [Async Tools](tool-functions.md#async-tools) in the Tool Functions Guide for more detail, and `examples/test-mcp/mcp-service.py`'s `echo` tool for a complete, runnable example of an `async def` tool exposed over MCP.

## Tool Description Endpoints

Even without `--with-mcp`, each tool has a `GET` endpoint that returns a description:

```bash
# Get tool description at the tool's path
curl http://localhost:8090/greet
```

This returns a JSON description suitable for agent frameworks that consume OpenAPI-style tool definitions. The description is generated from the function's docstring, Pydantic model fields, and `ToolOptions`.

## Configuring the Service ID

When AI agents call your tool, they need a stable service ID to identify where to send follow-up requests. Set `service_id` in `ToolOptions` to a path; the server will prepend the public URL prefix automatically:

```python
@ivcap_lambda("/greet", opts=ToolOptions(tags=["Greeter"], service_id="/greet"))
def greet(req: GreetRequest) -> GreetResult:
    """Greet a person

    Generates a personalised greeting.
    """
    ...
```

If the service is running behind a reverse proxy with the `X-Forwarded-For` or `X-Forwarded-Proto` headers, the public URL is detected automatically.

## Writing Good Tool Descriptions

AI agents use the docstring to decide when and how to call your tool. Follow these conventions for maximum agent compatibility:

```python
@ivcap_lambda("/analyse-sentiment", opts=ToolOptions(tags=["NLP"]))
def analyse_sentiment(req: SentimentRequest) -> SentimentResult:
    """Analyse the sentiment of a piece of text

    Given an input string, this tool returns a sentiment label
    (positive, negative, or neutral) and a confidence score between 0 and 1.

    Use this tool when you need to determine the emotional tone of user-provided
    text, product reviews, social media posts, or any other natural-language input.

    The tool processes text in English only. For multilingual text, pre-translate
    to English first.
    """
    ...
```

Key points:
- **First paragraph** — one-line summary (used as the OpenAPI endpoint summary)
- **Body** — detailed description of what the tool does, when to use it, and any constraints
- **Field descriptions** — every request and result field must have a clear `description` in `Field()`

## Connecting an MCP Client

### Claude Desktop / Cline (stdio)

Stdio-based hosts launch your service as a subprocess, so point them at `--with-mcp-stdio`, not `--with-mcp` (which starts the HTTP transport instead). Add to your Claude Desktop configuration (`~/.claude_desktop_config.json`) or Cline's MCP settings:

```json
{
  "mcpServers": {
    "my-lambda-service": {
      "command": "python",
      "args": ["my_service.py", "--with-mcp-stdio"],
      "cwd": "/absolute/path/to/your/service"
    }
  }
}
```

### MCP Inspector (for development)

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) lets you test MCP servers interactively, against either transport:

```bash
# HTTP (server already running with --with-mcp)
npx @modelcontextprotocol/inspector http://localhost:8090/mcp

# stdio (inspector launches the server itself)
npx @modelcontextprotocol/inspector python my_service.py --with-mcp-stdio
```

### Custom MCP Client (Python)

Use the official `mcp` SDK's `Client` to connect over Streamable-HTTP:

```python
import asyncio
import mcp

async def main():
    async with mcp.Client("http://localhost:8090/mcp") as client:
        tools = await client.list_tools()
        print([t.name for t in tools.tools])

        result = await client.call_tool("greet", {"req": {"name": "IVCAP"}})
        print(result.structured_content)

asyncio.run(main())
```

`Client` can also launch a local server as a stdio subprocess directly — see the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) docs for `StdioServerParameters`.

## Example: MCP-Ready Service

```python
from pydantic import BaseModel, Field
from ivcap_service import Service, ServiceContact, with_schema
from ivcap_lambda import start_lambda_server, ivcap_lambda, ToolOptions, logging_init

logging_init()

service = Service(
    name="NLP Tools",
    contact=ServiceContact(name="Dev Team", email="dev@example.com"),
)


@with_schema("urn:example:schema:word-count.request.1")
class WordCountRequest(BaseModel):
    text: str = Field(..., description="The text to count words in.")


@with_schema("urn:example:schema:word-count.1")
class WordCountResult(BaseModel):
    word_count: int = Field(..., description="Number of words in the text.")
    char_count: int = Field(..., description="Number of characters in the text.")


@ivcap_lambda("/word-count", opts=ToolOptions(tags=["NLP"], service_id="/word-count"))
def word_count(req: WordCountRequest) -> WordCountResult:
    """Count words and characters in a piece of text

    Returns the word count and character count of the provided text.
    Use this tool when you need to check text length constraints or
    estimate reading time for a given piece of content.
    """
    return WordCountResult(
        word_count=len(req.text.split()),
        char_count=len(req.text),
    )


if __name__ == "__main__":
    start_lambda_server(service)
```

Start with MCP enabled:

```bash
python my_service.py --with-mcp --port 8090
```

---

## MCP-First Development

If your primary goal is to build an **MCP server** — for Claude Desktop, Cursor, Cline, or any other MCP host — and the ability to *also* run on IVCAP is a bonus rather than the focus, you can start from `ivcap-lambda` without touching any IVCAP-specific concepts at all. The `@ivcap_lambda` decorator, `@with_schema`, and `JobContext` are the same building blocks either way — this section just reorders what matters first.

### Why use `ivcap-lambda` for an MCP-only project?

Because its MCP support is built on the **official `mcp` Python SDK** rather than a custom protocol implementation, you get spec-correct session handling, both Streamable-HTTP and stdio transports, and progress notifications for free. On top, `ivcap-lambda` adds Pydantic-model-driven schemas, a thread pool so blocking tool code doesn't need to be rewritten as `async def`, and automatic bridging of `jobCtxt.report.step(...)` calls to native `notifications/progress` messages.

### A minimal MCP-only service

```python
from pydantic import BaseModel, Field
from ivcap_service import Service, with_schema
from ivcap_lambda import ivcap_lambda, start_lambda_server, logging_init

logging_init()

# Only `name` is surfaced to MCP clients (as the server's reported name) —
# keep Service minimal if you don't care about IVCAP registration.
service = Service(name="My MCP Server")


@with_schema("urn:sd:schema:my-mcp-server.add.request.1")
class AddRequest(BaseModel):
    a: int = Field(..., description="First number.")
    b: int = Field(..., description="Second number.")


@with_schema("urn:sd:schema:my-mcp-server.add.1")
class AddResult(BaseModel):
    sum: int = Field(..., description="a + b.")


@ivcap_lambda("/add")
def add(req: AddRequest) -> AddResult:
    """Add two numbers

    Returns the sum of the two provided numbers.
    """
    return AddResult(sum=req.a + req.b)


if __name__ == "__main__":
    start_lambda_server(service)
```

Run it purely as an MCP server over stdio (no HTTP port, no FastAPI, nothing IVCAP-specific) — ideal for Claude Desktop/Cline, which launch the server as a subprocess:

```bash
pip install ivcap-lambda[mcp]
python my_mcp_server.py --with-mcp-stdio
```

Or over HTTP for remote clients / the MCP Inspector:

```bash
python my_mcp_server.py --with-mcp --port 8090
```

### What you can ignore (for now)

These only matter for IVCAP REST deployment and have no effect over MCP:

- `ToolOptions.max_wait_time` / `refresh_interval` — MCP's `tools/call` always awaits the result directly; there is no REST-style "poll me later" (`204`) equivalent in the base MCP spec
- `ToolOptions.service_id` — only populates the IVCAP tool-description endpoint
- `JobContext.ivcap` / `JobContext.job_authorization` — only relevant if your tool talks to IVCAP artifacts/services
- `--print-tool-description` / `--print-service-description` and `[tool.poetry-plugin-ivcap]` — only needed for IVCAP platform registration

### What still matters

- **`@with_schema`** — generates the MCP tool's input/output JSON schema from your Pydantic model; still required
- **Docstrings** — the first paragraph becomes the MCP tool's short description surfaced to the model; the rest is the longer description
- **`JobContext` for progress** — accept it as an optional parameter and use `jobCtxt.report.step(...)` for anything that takes more than a second or two, so MCP clients show live progress instead of appearing to hang (bounded by an internal 600s call timeout)
- **Raising `ValueError`** for bad input — surfaces as an MCP tool error (`is_error=True`) the model can read and react to, instead of a crash
- **`def` or `async def`, your choice** — a tool function can be written either way; `ivcap-lambda` detects which at registration time and runs it correctly either way (see [Sync and async tool functions both work over MCP](#sync-and-async-tool-functions-both-work-over-mcp) above)

### Testing without a real transport

```python
import asyncio
from ivcap_lambda.mcp import _build_mcp_server
import mcp

async def main():
    server = _build_mcp_server("My MCP Server", "0.1.0")
    async with mcp.Client(server) as client:          # in-memory, no network/subprocess
        result = await client.call_tool("add", {"req": {"a": 1, "b": 2}})
        print(result.structured_content)  # {'sum': 3}

asyncio.run(main())
```

See `examples/test-mcp/` in the [source repository](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python) for a complete runnable example covering both transports, including a plain-curl Streamable-HTTP test client. Its `echo` tool is defined with `async def` and demonstrates that async tool functions work identically to synchronous ones over MCP.

### Deploying to IVCAP later

Nothing in your tool code needs to change — add `ToolOptions(service_id=..., tags=[...])` and a `[tool.poetry-plugin-ivcap]` section to `pyproject.toml`, and follow the rest of this guide plus the [Deployment Guide](deployment.md). MCP was never a fork of the REST path; it's an additional transport over the same tool registry.

## See Also

- [AGENTS.md](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/AGENTS.md) — the same IVCAP-first / MCP-first split, aimed at AI coding agents
- [Tool Functions Guide](tool-functions.md) — Writing good tool functions
- [Best Practices](best-practices.md) — Docstring and naming conventions
- [MCP Protocol Specification](https://modelcontextprotocol.io/specification)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) — the upstream SDK this support is built on
- [`start_lambda_server` API](../api/server.md)
