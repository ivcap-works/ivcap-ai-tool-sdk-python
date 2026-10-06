"""Standalone MCP test service.

Exposes two of the shared 'ivcap_service.testkit' worker functions as
separate IVCAP lambda tools (and therefore, once `--with-mcp`/`--with-mcp-stdio`
is enabled, as separate MCP tools):

- 'compute': runs 'consume_compute()' - a CPU load test that also emits
  periodic progress events, useful for exercising MCP's
  'notifications/progress' bridging.
- 'wordle': runs 'handle_wordle()' - a self-contained Wordle game simulation.
- 'echo': a small, self-contained 'async def' tool - exercises
  ivcap-lambda's support for async tool functions. The REST and MCP paths
  reuse the same 'Executor', so 'async def' tools work identically over
  both transports (see 'examples/test-tool/tool-service.py's
  'async_tester' for the equivalent REST-focused example).

This mirrors (a subset of) 'examples/test-tool/tool-service.py' but keeps
each test as its own tool/endpoint (rather than bundled into one big
request), which is a closer match to how MCP clients typically expect tools
to be modelled.
"""

import asyncio

from pydantic import BaseModel, Field

from ivcap_service import (
    JobContext,
    Service,
    ServiceContact,
    ServiceLicense,
    with_schema,
)
from ivcap_service.testkit import (
    ConsumeComputeResult,
    ConsumeComputeTester,
    WordleResult,
    WordleTester,
    consume_compute,
    handle_wordle,
)

from ivcap_lambda import ToolOptions, ivcap_lambda, logging_init, start_lambda_server

logging_init()

service = Service(
    name="MCP Test Service for IVCAP",
    contact=ServiceContact(
        name="Max Ott",
        email="max.ott@data61.csiro.au",
    ),
    license=ServiceLicense(
        name="MIT",
        url="https://opensource.org/license/MIT",
    ),
)


@ivcap_lambda("/compute", opts=ToolOptions(tags=["Test Tool"], service_id="/compute"))
def compute(req: ConsumeComputeTester, jobCtxt: JobContext) -> ConsumeComputeResult:
    """Consume CPU for a while

    Burns CPU for 'duration_seconds' at roughly 'target_cpu_percent' load,
    emitting a progress event every 'progress_interval_seconds' - useful for
    exercising event/progress reporting (surfaced as MCP
    'notifications/progress' when called over MCP). Can optionally raise an
    exception, exit with a given code, or cause an OOM error at the end of
    the run, to test error handling.
    """
    return consume_compute(req, jobCtxt)


@ivcap_lambda("/wordle", opts=ToolOptions(tags=["Test Tool"], service_id="/wordle"))
def wordle(req: WordleTester, jobCtxt: JobContext) -> WordleResult:
    """Play a game of Wordle

    Plays a random game of Wordle, solved by a built-in AI solver, and
    reports whether it succeeded within the allowed number of attempts.
    """
    return handle_wordle(req, jobCtxt)


@with_schema("urn:sd:schema:mcp-test.echo.request.1")
class EchoRequest(BaseModel):
    text: str = Field(..., description="Text to echo back, upper-cased.")


@with_schema("urn:sd:schema:mcp-test.echo.1")
class EchoResult(BaseModel):
    output: str = Field(..., description="The upper-cased input text.")


@ivcap_lambda("/echo", opts=ToolOptions(tags=["Test Tool"], service_id="/echo"))
async def echo(req: EchoRequest, jobCtxt: JobContext) -> EchoResult:
    """Echo a message back, upper-cased, via an 'async def' tool function

    Demonstrates that tool functions can be defined with 'async def' -
    ivcap-lambda detects this automatically (via
    'asyncio.iscoroutinefunction') and awaits the coroutine on a dedicated
    event loop inside the executor's thread pool, so this works identically
    whether the tool is called over plain REST or over MCP ('tools/call').
    """
    with jobCtxt.report.step("work", "echoing") as step:
        await asyncio.sleep(0)  # yield once, to exercise the async path
        step.finished("done")
    return EchoResult(output=req.text.upper())


if __name__ == "__main__":
    start_lambda_server(service)
