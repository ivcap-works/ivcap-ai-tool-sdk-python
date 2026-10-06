# test-mcp

A standalone example service demonstrating `ivcap-lambda`'s MCP (Model
Context Protocol) support. It exposes three tools:

- **`compute`** (`POST /compute`) - `ConsumeComputeTester` / `consume_compute()`:
  a CPU load test that emits periodic progress events
  (`progress_interval_seconds`) - useful for exercising MCP's
  `notifications/progress` bridging. Can also be used to test error
  handling, by setting `throw_exception_at_end`, `exit_code_at_end`, or
  `create_oom_error_at_end`.
- **`wordle`** (`POST /wordle`) - `WordleTester` / `handle_wordle()`: a
  self-contained Wordle game simulation played by a built-in AI solver.
- **`echo`** (`POST /echo`) - a small, self-contained **`async def`** tool
  function that echoes back its input text, upper-cased. Unlike `compute`
  and `wordle` (both plain, synchronous `def` functions delegating to
  `ivcap_service.testkit`), `echo` is defined with `async def` and `await`s
  internally - demonstrating that `ivcap-lambda` tool functions can be
  either synchronous or asynchronous, over *both* the REST and the MCP
  (`tools/call`) path, with no special-casing required in tool code. See
  `ivcap_lambda/executor.py`'s use of `asyncio.iscoroutinefunction()` for
  how this is detected and run.

`compute` and `wordle` are backed by `ivcap_service.testkit` (also used by
the `test-tool` and `test-batch` examples), so there is no business logic
duplicated in this example - `mcp-service.py` only wires the shared worker
functions up as separate `@ivcap_lambda` endpoints. `echo` is self-contained
(no `testkit` dependency) since its only purpose is demonstrating the
`async def` tool-function path. All three tools are independently
addressable/callable, which is a closer match to how MCP clients typically
expect tools to be modelled (vs. `test-tool`'s single big "do everything"
request).

## Directory layout

```
test-mcp/
├── mcp-service.py            # the three '@ivcap_lambda' tool definitions
├── pyproject.toml            # poetry project + poetry-plugin-ivcap config
├── Dockerfile                # container build (patches dev deps → PyPI)
├── Makefile                  # run/test/inspector shortcuts
├── resources.json            # k8s cpu/memory limits for deployment
├── mcp-inspector.config.json # MCP Inspector server config
└── tests/
    ├── mcp-call.sh                 # curl-only MCP (streamable-HTTP) test client
    ├── compute.json                # 'req' args for the 'compute' tool
    ├── compute-with-exception.json
    ├── compute-with-oom.json
    ├── wordle.json                 # 'req' args for the 'wordle' tool
    └── echo.json                   # 'req' args for the 'echo' ('async def') tool
```

## Setup

```shell
poetry install
```

During development, `ivcap-lambda` and `ivcap-service` are both referenced
via local `path` dependencies in `pyproject.toml` (see the comments there),
so `poetry install` always picks up in-progress local changes to either
library. `ivcap-service>=0.7.0` (the first release containing
`ivcap_service.testkit`) is now published on PyPI, so the
`[project.dependencies]` version constraint is already set to
`>=0.7.0,<0.8.0`; the `Dockerfile` build (see below) swaps the local `path`
dependencies for the published PyPI constraints, so building/deploying the
container image needs no further action.

## Running

This is an MCP example, so `make run` (the default target) starts the
service **with the MCP endpoint mounted** at `/mcp` (Streamable HTTP
transport), alongside the plain REST endpoints:

```shell
make run
# or directly:
poetry run python mcp-service.py --port 8096 --with-mcp
```

To run the REST endpoints only, without MCP:

```shell
make run-rest-only
```

As a pure stdio MCP server, for stdio-based MCP hosts (Claude Desktop,
Cline, the MCP Inspector's stdio mode, etc.) that launch the tool as a
subprocess instead of connecting over HTTP - this mode does **not** start
the FastAPI/uvicorn HTTP server at all:

```shell
make run-mcp-stdio
# or directly:
poetry run python mcp-service.py --with-mcp-stdio
```

## Testing over MCP

With the server running (`make run`), test the three MCP tools with:

```shell
make test-wordle                 # plays one game of Wordle
make test-compute                # normal run, ~5s, emits progress events
make test-compute-with-exception # raises an exception at the end
make test-compute-with-oom       # causes an OOM error at the end (see warning below)
make test-echo                   # calls the 'async def' echo tool
make test-all                    # wordle + compute + compute-with-exception + echo
```

Each prints every Server-Sent-Event the call produces - the
`notifications/progress` events followed by the final `tools/call` result
(or error).

> `test-compute-with-oom` genuinely exhausts memory and gets the server
> process **OOM-killed by the OS** - the curl call will fail with `transfer
> closed with outstanding read data remaining` once that happens, which is
> expected. Restart the server (`make run`) afterwards. It's intentionally
> excluded from `test-all` for this reason.

### `tests/mcp-call.sh` - a curl-only MCP test client

There's no official `mcp` CLI that speaks the Streamable HTTP transport
directly from the shell, but the protocol itself is just three plain HTTP
`POST` requests, so `tests/mcp-call.sh` implements a minimal client using
nothing but `curl` (and `jq`, if present, purely for pretty-printing):

1. `POST /mcp` `method=initialize` - captures the `Mcp-Session-Id` response
   header, which must be sent on every subsequent request for that session.
2. `POST /mcp` `method=notifications/initialized` - required handshake step.
3. `POST /mcp` `method=tools/call` - the response is a Server-Sent-Events
   stream: zero or more `notifications/progress` events (if the tool reports
   progress), followed by one final event carrying the tool's result.

```shell
./tests/mcp-call.sh <tool-name> <path-to-json-file-with-args>

# e.g.
MCP_URL=http://localhost:8096/mcp ./tests/mcp-call.sh wordle tests/wordle.json
MCP_URL=http://localhost:8096/mcp ./tests/mcp-call.sh compute tests/compute.json
```

`MCP_URL` defaults to `http://localhost:8096/mcp` if unset. The `make
test-*` targets above are thin wrappers around this script.

### Example tool call and response

```shell
$ ./tests/mcp-call.sh wordle tests/wordle.json
{
  "jsonrpc": "2.0",
  "method": "notifications/progress",
  "params": {
    "progressToken": "mcp-call-sh",
    "progress": 1.0,
    "message": "Playing Wordle (max_attempts=2, thinking_time=1)"
  }
}
{
  "jsonrpc": "2.0",
  "method": "notifications/progress",
  "params": { "progressToken": "mcp-call-sh", "progress": 2.0, "message": "play_wordle" }
}
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [{ "text": "{\n  \"secret\": \"PLANK\",\n  \"success\": true,\n  \"attempts\": 2\n}", "type": "text" }],
    "isError": false,
    "structuredContent": { "secret": "PLANK", "success": true, "attempts": 2 }
  }
}
```

### Example request payloads

`tests/compute.json`:

```json
{
  "duration_seconds": 5,
  "target_cpu_percent": 60,
  "progress_interval_seconds": 1
}
```

`tests/echo.json`:

```json
{
  "text": "hello from mcp"
}
```

`tests/wordle.json`:

```json
{
  "max_attempts": 2,
  "thinking_time": 1
}
```

See `ivcap_service/testkit/consume_compute.py` and
`ivcap_service/testkit/wordle.py` (in `ivcap-service2-sdk-python`) for the
full field reference (`ConsumeComputeTester`/`ConsumeComputeResult` and
`WordleTester`/`WordleResult`).

### MCP Inspector (interactive, HTTP)

```shell
make run &
make mcp-inspector
```

This opens the [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
pointed at `http://localhost:8096/mcp` (see `mcp-inspector.config.json`),
where you can browse all three tools' schemas, invoke them, and watch
`compute`'s progress notifications stream in live.

### Programmatically (Python `mcp` SDK, HTTP)

```python
import asyncio
import mcp

async def main():
    async with mcp.Client("http://localhost:8096/mcp") as client:
        tools = await client.list_tools()
        print([t.name for t in tools.tools])  # ['compute', 'wordle', 'echo']

        result = await client.call_tool("wordle", {"req": {"max_attempts": 2}})
        print(result.structured_content)

        async def progress_cb(progress, total, message):
            print("progress:", message)

        result = await client.call_tool(
            "compute",
            {"req": {"duration_seconds": 2, "target_cpu_percent": 30}},
            progress_callback=progress_cb,
        )
        print(result.structured_content)

        # 'echo' is defined with 'async def' (not plain 'def') - calling it
        # over MCP works exactly the same as the two synchronous tools above.
        result = await client.call_tool("echo", {"req": {"text": "hi"}})
        print(result.structured_content)  # {'output': 'HI'}

asyncio.run(main())
```

### Claude Desktop / Cline (stdio)

For stdio-based MCP hosts, point them at `poetry run python mcp-service.py
--with-mcp-stdio` as the launch command, e.g. in Claude Desktop's
`claude_desktop_config.json` or Cline's MCP settings:

```json
{
  "mcpServers": {
    "test-mcp": {
      "command": "poetry",
      "args": ["run", "python", "mcp-service.py", "--with-mcp-stdio"],
      "cwd": "/absolute/path/to/examples/test-mcp"
    }
  }
}
```

## Troubleshooting

- **Port already in use**: change `PORT` in the `Makefile` (default `8096`)
  or pass `--port` directly.
- **`ivcap_service.testkit` import errors**: `ivcap_service.testkit` requires
  `ivcap-service>=0.7.0`. Run `poetry show ivcap-service` to check the
  installed version, and `poetry update ivcap-service` (or `poetry install`
  again, if using the local `path` dependency - see `pyproject.toml`) if it's
  older than that.
- **`--with-mcp-stdio` and `--with-mcp` together**: these are mutually
  exclusive; the server will refuse to start if both are given.
