import os
from asyncio import sleep as async_sleep
from time import sleep, time

from fastapi import Request as FRequest
from ivcap_service import (
    JobContext,
    Service,
    ServiceContact,
    ServiceLicense,
    getLogger,
    with_schema,
)
from ivcap_service.testkit import (
    ArtifactResult,
    ArtifactTester,
    CallTester,
    ConsumeComputeResult,
    ConsumeComputeTester,
    EventResult,
    EventTester,
    LlmResult,
    LlmTester,
    WordleResult,
    WordleTester,
    completion,
    consume_compute,
    handle_artifact,
    handle_wordle,
    make_request,
    send_events,
)
from pydantic import BaseModel, Field

from ivcap_lambda import ToolOptions, ivcap_lambda, logging_init, start_lambda_server

logging_init()
logger = getLogger("app")


service = Service(
    name="AI Test Tool for IVCAP",
    version=os.environ.get("VERSION", "???"),
    contact=ServiceContact(
        name="Max Ott",
        email="max.ott@data61.csiro.au",
    ),
    license=ServiceLicense(
        name="MIT",
        url="https://opensource.org/license/MIT",
    ),
)


class RequestContext(BaseModel):
    headers: list[tuple[str, str]]
    method: str
    url: str

    @classmethod
    def from_freq(cls, freq: FRequest):
        return cls(
            headers=list(freq.headers.items()), method=freq.method, url=str(freq.url)
        )


# Most of the business logic below is implemented by, and shared with, the
# 'ivcap_service.testkit' worker functions (also used by the 'test-batch'
# batch-service example) - see 'ivcap_service/testkit/' for the
# implementation of 'CallTester'/'make_request', 'LlmTester'/'completion',
# 'WordleTester'/'handle_wordle', 'ConsumeComputeTester'/'consume_compute'
# (which also covers raising exceptions, exiting with a code, or causing an
# OOM error at the end of the run), 'ArtifactTester'/'handle_artifact', and
# 'EventTester'/'send_events'.
@with_schema("urn:sd:schema:ai-tester.request.1")
class Request(BaseModel):
    echo: str | None = Field(None, description="a string to echo in result")
    call: CallTester | None = Field(None, description="Optionally call a service")
    llm: LlmTester | None = Field(
        None, description="Optionally call an LLM's completion service"
    )
    wordle: WordleTester | None = Field(
        None, description="Optionally play a game of Wordle with a built-in AI solver"
    )
    consume_cpu: ConsumeComputeTester | None = Field(
        None,
        description=(
            "Optionally consume a target percentage of CPU for a given duration "
            "- also used to test raising an exception, exiting with a specific "
            "code, or causing an OOM error at the end of the run"
        ),
    )
    artifact: ArtifactTester | None = Field(
        None,
        description="Optionally download an artifact (and optionally re-upload it)",
    )
    events: EventTester | None = Field(
        None, description="Optionally emit a number of progress events"
    )
    sleep: int | None = Field(
        0, description="the number of seconds to sleep before replying"
    )


@with_schema("urn:sd:schema:ai-tester.1")
class Result(BaseModel):
    echo: str | None = Field(None, description="echos string from request")
    call_result: dict | None = Field(
        None, description="result of executing the 'call'"
    )
    llm_result: LlmResult | None = Field(
        None, description="result of executing the 'llm'"
    )
    wordle_result: WordleResult | None = Field(
        None, description="result of executing the 'wordle' game"
    )
    consume_result: ConsumeComputeResult | None = Field(
        None, description="result of executing the 'consume_cpu' CPU load test"
    )
    artifact_result: ArtifactResult | None = Field(
        None,
        description="result of downloading (and optionally re-uploading) an artifact",
    )
    event_result: EventResult | None = Field(
        None, description="result of executing the 'events' test"
    )
    request: RequestContext = Field(description="information on the incoming request")
    run_time: float = Field(description="time in seconds this job took")


@ivcap_lambda("/", opts=ToolOptions(tags=["Test Tool"], service_id="/"))
def tester(req: Request, freq: FRequest, jobCtxt: JobContext) -> Result:
    """
    Run various tests

    This is a simple test harness to execute various functionalities, most of
    which are backed by the shared 'ivcap_service.testkit' worker functions.
    """
    result = Result(run_time=0, request=RequestContext.from_freq(freq))
    start_time = time()  # Start timer

    with jobCtxt.report.step("main", f"Start tool execution for {freq.url}") as step:
        if req.echo is not None:
            result.echo = req.echo

        if req.call is not None:
            result.call_result = make_request(req.call, jobCtxt)

        if req.llm is not None:
            result.llm_result = completion(req.llm)

        if req.wordle is not None:
            result.wordle_result = handle_wordle(req.wordle, jobCtxt)

        if req.consume_cpu is not None:
            result.consume_result = consume_compute(req.consume_cpu, jobCtxt)

        if req.artifact is not None:
            result.artifact_result = handle_artifact(req.artifact, jobCtxt)

        if req.events is not None:
            result.event_result = send_events(req.events, jobCtxt)

        if req.sleep:
            sleep(req.sleep)

        result.run_time = round(time() - start_time, 2)
        step.finished(f"Finished tool execution in {result.run_time} seconds")
    return result


@ivcap_lambda("/async", opts=ToolOptions(tags=["Test Tool"], service_id="/"))
async def async_tester(req: Request, freq: FRequest) -> Result:
    """
    Run various tests in 'async' mode

    Exercises the ivcap-lambda library's support for 'async def' tool
    functions - the only aspect of this tool not already covered by the
    (synchronous) 'ivcap_service.testkit' worker functions.
    """
    result = Result(run_time=0, request=RequestContext.from_freq(freq))
    start_time = time()  # Start timer

    if req.echo is not None:
        result.echo = req.echo

    if req.call is not None:
        raise Exception("not implemented")

    if req.llm is not None:
        result.llm_result = await async_completion(req.llm)

    if req.sleep:
        await async_sleep(req.sleep)

    result.run_time = round(time() - start_time, 2)
    return result


async def async_completion(req: LlmTester) -> LlmResult:
    import openai

    client = create_openai_client(openai.AsyncOpenAI)
    response = await client.chat.completions.create(
        model=req.model, messages=[m.model_dump() for m in req.messages]
    )
    messages = [c.message.model_dump() for c in response.choices]
    usage = response.usage.model_dump()
    return LlmResult(messages=messages, usage=usage)


def create_openai_client(f):
    base_url = os.getenv("LITELLM_PROXY")
    if base_url is None:
        return f()
    else:
        return f(base_url=f"{base_url}/v1", api_key="not-needed")


if __name__ == "__main__":
    import argparse

    def custom_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
        parser.add_argument(
            "--litellm-proxy", type=str, help="Address of the the LiteLlmProxy"
        )
        args = parser.parse_args()
        if args.litellm_proxy is not None:
            os.environ["LITELLM_PROXY"] = args.litellm_proxy
        return args

    start_lambda_server(service, custom_args=custom_args)
