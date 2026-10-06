# Track C: Converting an Existing Plain `mcp` SDK Server to `ivcap-lambda`

> Part of the `ivcap-lambda` AI-agent playbook. Start at [`AGENTS.md`](../../AGENTS.md) for the full router and the Shared Reference (symbol table, best practices). This file is self-contained for the specific task of migrating an existing server, so you don't need to read [Track A](track-a-ivcap-service.md) or [Track B](track-b-mcp-first.md) first — but they're useful follow-up reading once the migration is done (Track A covers IVCAP REST deployment details, Track B covers MCP-only concerns in more depth).

If a developer already has a working MCP server built directly on the
official `mcp` Python SDK (`MCPServer`/`FastMCP`, `@mcp.tool()`) and wants to
migrate it onto `ivcap-lambda` — so it keeps working exactly the same for
MCP clients/hosts, but also becomes a clean, first-class IVCAP REST
service — follow this mapping. No MCP-client-facing behaviour needs to
change: tool names, descriptions, and input/output schemas stay the same;
only how the server is *built* changes.

## Concept Mapping

| Plain `mcp` SDK | `ivcap-lambda` equivalent |
|---|---|
| `from mcp.server import MCPServer` (or `mcp.server.fastmcp.FastMCP`) | `from ivcap_lambda import ivcap_lambda, start_lambda_server, logging_init` plus `from ivcap_service import Service, with_schema, JobContext` |
| `mcp = MCPServer("Demo")` | `service = Service(name="Demo")` — there's no single server object to decorate against; tool functions register themselves into a shared module-level registry via `@ivcap_lambda` |
| `@mcp.tool()` on a function with several plain-typed params, e.g. `def add(a: int, b: int) -> int:` | `@ivcap_lambda("/add")` on a function taking **one** Pydantic request model: `def add(req: AddRequest) -> AddResult:` — see [Collapsing Multiple Params](#collapsing-multiple-params-into-one-request-model) below, the one required reshaping step |
| Plain return value (`int`, `str`, `dict`, dataclass, ...) | A single `@with_schema`-decorated Pydantic `BaseModel` returned from the function |
| `ctx: Context` parameter + `await ctx.report_progress(progress, message=...)` | `jobCtxt: JobContext` parameter + `with jobCtxt.report.step("name", "msg") as step: ... step.finished("done")` — bridged automatically to native MCP `notifications/progress`, no `await` needed in tool code |
| `mcp.run(transport="stdio")` | `start_lambda_server(service)` at the bottom of the file, then launch the process with `--with-mcp-stdio` |
| `mcp.run(transport="streamable-http")` / `mcp_server.streamable_http_app(...)` | `start_lambda_server(service)`, then launch with `--with-mcp --port <port>` |
| `@mcp.resource(...)` / `@mcp.prompt(...)` | **Not supported.** `ivcap-lambda` only exposes `@ivcap_lambda`-registered functions as MCP *tools*; it has no equivalent for MCP resources or prompts. If the existing server relies on these, either keep them on a small separate plain-`mcp` server, or redesign them as tools (a "resource" that just returns data can usually become a tool that returns a Pydantic model) |
| `mcp dev server.py` (MCP Inspector) | `npx @modelcontextprotocol/inspector python server.py --with-mcp-stdio` (stdio) or point the Inspector at `http://localhost:<port>/mcp` after starting with `--with-mcp` |

## Collapsing Multiple Params into One Request Model

The one structural change required: the plain `mcp` SDK derives a tool's
input schema from a function's individual typed parameters, while
`ivcap-lambda`'s `@ivcap_lambda` always expects a **single** Pydantic
`BaseModel` as the first parameter (this is what both the REST `POST` body
and the MCP `tools/call` `req` argument serialize to/from). Collect the
scalar parameters into one request model, one `Field(..., description=...)`
per original parameter — every field needs a description, same convention
as the rest of this playbook.

**Before** (plain `mcp` SDK, from the SDK's own "15 lines" example):

```python
from mcp.server import MCPServer

mcp = MCPServer("Demo")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**After** (same tool, same MCP-facing name/behaviour, now on `ivcap-lambda`):

```python
from pydantic import BaseModel, Field
from ivcap_service import Service, with_schema
from ivcap_lambda import ivcap_lambda, start_lambda_server, logging_init

logging_init()

# Only `name` matters to MCP clients; keep it minimal if IVCAP registration
# isn't a goal (yet).
service = Service(name="Demo")


@with_schema("urn:sd:schema:demo.add.request.1")
class AddRequest(BaseModel):
    a: int = Field(..., description="First number.")
    b: int = Field(..., description="Second number.")


@with_schema("urn:sd:schema:demo.add.1")
class AddResult(BaseModel):
    result: int = Field(..., description="a + b.")


@ivcap_lambda("/add")
def add(req: AddRequest) -> AddResult:
    """Add two numbers.

    Returns the sum of the two provided numbers.
    """
    return AddResult(result=req.a + req.b)


if __name__ == "__main__":
    start_lambda_server(service)
```

Run it exactly as the original stdio-launched server was run, just append
the transport flag:

```bash
pip install ivcap-lambda[mcp]
python server.py --with-mcp-stdio
```

Existing Claude Desktop / Cline configs need only the launch `args` updated
— the `mcpServers` entry's shape is unchanged:

```json
{
  "mcpServers": {
    "demo": {
      "command": "python",
      "args": ["server.py", "--with-mcp-stdio"],
      "cwd": "/absolute/path/to/server"
    }
  }
}
```

## Migrating a Tool That Reports Progress

```python
# Before (plain mcp SDK)
from mcp.server.mcpserver import Context

@mcp.tool()
async def long_task(n: int, ctx: Context) -> str:
    """Run a long task."""
    for i in range(n):
        await ctx.report_progress(i, total=n, message=f"step {i}")
    return "done"
```

```python
# After (ivcap-lambda)
@with_schema("urn:sd:schema:demo.long-task.request.1")
class LongTaskRequest(BaseModel):
    n: int = Field(..., description="Number of steps to run.")

@with_schema("urn:sd:schema:demo.long-task.1")
class LongTaskResult(BaseModel):
    status: str = Field(..., description="Final status.")

@ivcap_lambda("/long-task")
def long_task(req: LongTaskRequest, jobCtxt: JobContext) -> LongTaskResult:
    """Run a long task."""
    with jobCtxt.report.step("run", "running") as step:
        for i in range(req.n):
            step.info(f"step {i}")
        step.finished("done")
    return LongTaskResult(status="done")
```

No `await`/`async def` is required just to report progress — `def` and
`async def` tool functions both work identically over MCP; only use
`async def` if the function body itself needs to `await` something.

## What Is Preserved, What Changes

**Preserved (zero MCP-client-visible change):**

- Tool name (defaults to the function name, same as `@mcp.tool()`)
- Tool description (docstring: first paragraph = short description, rest = long description)
- Input/output JSON schema shape, as long as the request/result models' fields match the original parameters/return value
- Progress notifications, `tools/call` semantics, both stdio and Streamable-HTTP transports
- Error behaviour: raising `ValueError` still surfaces as an MCP tool error (`is_error=True`)

**Changes required:**

- Multiple scalar parameters → one `@with_schema`-decorated Pydantic request model
- Plain/primitive return value → one `@with_schema`-decorated Pydantic result model
- `ctx: Context` + `await ctx.report_progress(...)` → `jobCtxt: JobContext` + `with jobCtxt.report.step(...)`
- One `MCPServer`/`FastMCP` instance + `@mcp.tool()` → a `Service(...)` instance (metadata only) + one `@ivcap_lambda(...)` per tool function
- `mcp.run(transport=...)` → `start_lambda_server(service)` + a CLI flag (`--with-mcp-stdio` / `--with-mcp --port ...`) at launch time, not in code
- `@mcp.resource(...)` / `@mcp.prompt(...)` have no equivalent (see Concept Mapping table above)

**Bonus, available afterwards with no further code changes:** the exact
same functions are now also valid IVCAP REST/agent tool endpoints — add
`ToolOptions(service_id=..., tags=[...])` to `@ivcap_lambda(...)` and a
`[tool.poetry-plugin-ivcap]` section to `pyproject.toml` whenever IVCAP
deployment becomes a goal. See [Track A: IVCAP Lambda Service](track-a-ivcap-service.md)
for the full deployment walkthrough (`ToolOptions`, `pyproject.toml`
layout, the IVCAP try-later protocol, etc.) — nothing in that guide
requires undoing anything done here.

That's the end of Track C. See [`AGENTS.md`'s Shared Reference](../../AGENTS.md#shared-reference) for Best Practices and the full symbol table, or [Track B](track-b-mcp-first.md) for more MCP-only depth (testing without a transport, execution semantics, what to ignore for now).
