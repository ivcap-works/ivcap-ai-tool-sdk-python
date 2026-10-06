# Track B: MCP-First Server

> Part of the `ivcap-lambda` AI-agent playbook. Start at [`AGENTS.md`](../../AGENTS.md) if you haven't already — it routes to [Track A](track-a-ivcap-service.md), this file, and [Track C](track-c-migrate-from-mcp.md), and holds the Shared Reference (symbol table, best practices) that applies here too. If you already have a working plain-`mcp`-SDK server and want to migrate it onto `ivcap-lambda`, skip straight to **[Track C: Converting an Existing Plain `mcp` SDK Server](track-c-migrate-from-mcp.md)** instead — it's self-contained and doesn't require reading this file first.

For developers whose primary goal is building an **MCP server** — one that works well in Claude Desktop, Cursor, Cline, or any other MCP host — where the ability to *also* run as an IVCAP lambda service is a nice-to-have, not the focus. You write exactly the same `@ivcap_lambda`-decorated functions as [Track A](track-a-ivcap-service.md); the difference is which parts of the library you actually need to think about, and which CLI flag you reach for first.

## Why `ivcap-lambda` for an MCP-only project?

Even if you never plan to deploy to IVCAP, `ivcap-lambda` gives you a production-quality MCP server for very little code because it's built on the **official `mcp` Python SDK** (not a custom reimplementation): spec-correct session handling, Streamable-HTTP *and* stdio transports, resumability, and progress notifications all come from that upstream dependency. On top, `ivcap-lambda` adds:

- Pydantic-model-driven tool schemas (define a request/result model once, get the MCP input/output schema and the REST schema for free)
- A thread pool + job-result cache so slow/blocking tool functions don't need to be rewritten as `async def`
- `jobCtxt.report.step(...)` progress reporting that is automatically bridged to native MCP `notifications/progress` messages
- A Swagger/OpenAPI UI (`/api`) and a tool-description endpoint "for free" if you ever *do* want to expose the same tool over plain REST

## Minimal MCP-Only Service

```python
from pydantic import BaseModel, Field
from ivcap_service import Service, with_schema
from ivcap_lambda import ivcap_lambda, start_lambda_server, logging_init

logging_init()

# `Service` metadata is still required by start_lambda_server(), but none of
# its fields matter for MCP clients — only `name` is used (as the MCP
# server's reported name). Keep it minimal.
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

Run it as a pure MCP server — no HTTP port, no FastAPI server, nothing IVCAP-specific — ideal for local development against Claude Desktop/Cline, which launch the server as a stdio subprocess:

```bash
pip install ivcap-lambda[mcp]
python my_mcp_server.py --with-mcp-stdio
```

Or expose it over HTTP (Streamable-HTTP transport) for remote MCP clients / the MCP Inspector:

```bash
python my_mcp_server.py --with-mcp --port 8090
# then: npx @modelcontextprotocol/inspector http://localhost:8090/mcp
```

`--with-mcp` and `--with-mcp-stdio` are mutually exclusive. With `--with-mcp-stdio`, no REST/Swagger/health endpoints are started at all — the process is purely an MCP server over stdio for as long as the host keeps the connection open.

## Things You Can Mostly Ignore in an MCP-First Project

These exist for IVCAP deployment and are safe to skip unless/until you decide to also run on IVCAP:

- `ToolOptions.max_wait_time` / `refresh_interval` — only affect the REST "try-later" (`204`) path; MCP's `tools/call` always awaits the result directly (see [Execution Semantics](#execution-semantics-mcp-vs-rest) below)
- `ToolOptions.service_id` — only used to populate the IVCAP tool-description endpoint's `service_id` field
- `JobContext.ivcap` / `JobContext.job_authorization` — IVCAP platform client and auth token; irrelevant unless your tool talks to IVCAP artifacts/services
- `--print-tool-description` / `--print-service-description` — only needed for IVCAP platform registration
- `[tool.poetry-plugin-ivcap]` in `pyproject.toml` — only needed if/when you register the service with IVCAP

## Things Worth Using Even in an MCP-First Project

- **`@with_schema` on request/result models** — still the mechanism that generates the MCP tool's input/output JSON schema from your Pydantic model; skipping it is not an option, it's load-bearing for both transports
- **Docstrings** — the first paragraph becomes the MCP tool's short description surfaced to the LLM; the rest becomes the longer description. Same conventions as Track A: explain what the tool does, when to use it, and any constraints
- **`JobContext` (optional parameter) for progress reporting** — if a tool can take more than a second or two, accept `jobCtxt: JobContext` and wrap the slow part in `with jobCtxt.report.step(...)`; this shows up as live progress in MCP clients that render `notifications/progress` (e.g. the MCP Inspector), with zero MCP-specific code
- **Raising `ValueError` for bad input** — surfaces as a proper MCP tool error (`is_error=True`) that the calling model can read and react to, instead of a crash

## Execution Semantics: MCP vs REST

MCP's `tools/call` is a single request/response RPC with progress delivered as notifications on the *same* call — there is no REST-style "it's taking a while, poll me later" (`204`/`Retry-Later`) equivalent in the base MCP spec. So when a tool is invoked over MCP, `ivcap-lambda` always waits for the result (bounded by an internal `600s` timeout) rather than ever deferring it. Implications for MCP-first design:

- Don't rely on `ToolOptions.max_wait_time` to bound how long an MCP client waits — it has no effect over MCP
- If a tool can genuinely take minutes, report progress via `jobCtxt.report.step(...)` so the client/host shows the user something is happening, rather than appearing to hang
- The REST "try-later" protocol (described in [Track A](track-a-ivcap-service.md#async-try-later-protocol)) only matters if/when the same tool is also exposed over plain REST

## Testing an MCP-First Service

```python
# Using the official mcp SDK's in-memory client (no network, no subprocess)
import asyncio
from ivcap_lambda.mcp import _build_mcp_server  # or call register_mcp(app) and use its return value
import mcp

async def main():
    server = _build_mcp_server("My MCP Server", "0.1.0")
    async with mcp.Client(server) as client:
        tools = await client.list_tools()
        print([t.name for t in tools.tools])
        result = await client.call_tool("add", {"req": {"a": 1, "b": 2}})
        print(result.structured_content)  # {'sum': 3}

asyncio.run(main())
```

For an end-to-end example testing both the stdio and HTTP transports (including a plain-curl Streamable-HTTP client and progress-notification capture), see `examples/test-mcp/` in this repository — particularly `tests/mcp-call.sh` and the `make run-mcp-stdio` / `make test-*` targets. Its `echo` tool is defined with `async def` (not plain `def`) and confirms async tool functions work identically over MCP's `tools/call` as they do over REST (both tracks share the same `Executor`, which detects `async def` via `asyncio.iscoroutinefunction` and awaits it on a dedicated event loop — see [Track A, "Async Tools"](track-a-ivcap-service.md#10-async-tools)).

## Deploying to IVCAP Later (Optional)

If a service built MCP-first later needs to also run on IVCAP, nothing in the tool code changes — add `ToolOptions(service_id=..., tags=[...])`, a `[tool.poetry-plugin-ivcap]` section to `pyproject.toml`, and follow [Track A's Project Structure](track-a-ivcap-service.md#project-structure) / deployment steps. The same `@ivcap_lambda`-decorated function is already a valid REST endpoint; MCP was never a fork, just an additional transport over the same registry.

That's the end of Track B. See [`AGENTS.md`'s Shared Reference](../../AGENTS.md#shared-reference) for Best Practices and the full symbol table, or go to **[Track C: Converting an Existing Plain `mcp` SDK Server](track-c-migrate-from-mcp.md)** if you're migrating an existing server rather than starting fresh.
