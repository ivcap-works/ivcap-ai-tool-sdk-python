import os
import sys
from asyncio import sleep as async_sleep
from time import sleep, time
from typing import Any

import httpx
import requests
from fastapi import Request as FRequest
from ivcap_service import Service, getLogger
from ivcap_service.events import GenericEvent
from pydantic import BaseModel, Field, HttpUrl
from wordle import WordleProps, WordleResult, play_random_wordle

from ivcap_ai_tool import ToolOptions, ivcap_ai_tool, logging_init, start_tool_server
from ivcap_ai_tool.executor import JobContext

this_dir = os.path.dirname(__file__)
src_dir = os.path.abspath(os.path.join(this_dir, "../../src"))
sys.path.insert(0, src_dir)


logging_init()
logger = getLogger("app")


service = Service(
    name="AI Test Tool for IVCAP",
    description="""
Test tool to exercise various aspects of the IVCAP platform.
""",
    contact={
        "name": "Max Ott",
        "email": "max.ott@data61.csiro.au",
    },
    license={
        "name": "MIT",
        "url": "https://opensource.org/license/MIT",
    },
)


class CallTester(BaseModel):
    method: str = Field(..., description="The HTTP method to use (GET, POST, PUT, DELETE, etc.).",
                        # Only allow valid methods
                        pattern="^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$"
                        )
    url: HttpUrl = Field(..., description="The full URL of the API endpoint.")
    params: dict[str, Any] | None = Field(
        None, description="Optional dictionary of query parameters to be appended to the URL.")
    data: dict[str, Any] | None = Field(
        None, description="Optional JSON payload to be sent in the request body (for POST/PUT).")
    headers: dict[str, str] | None = Field(
        None, description="Optional dictionary of headers to include in the request.")
    timeout: int = Field(5, description="The timeout duration for the request in seconds.",
                         ge=1  # Minimum value of 1 second to prevent infinite waiting
                         )


class ChatMessage(BaseModel):
    content: str = Field(..., description="The content of this message.")
    role: str = Field(..., description="The role of the messages author.")
    name: str | None = Field(
        None, description="An optional name for the participant.")


class LlmTester(BaseModel):
    messages: list[ChatMessage] = Field(
        ..., description="A list of messages to be passed to the LLM.")
    model: str | None = Field(
        "gpt-3.5-turbo", description="The LLM model to use [gpt-3.5-turbo].")


class EventTester(BaseModel):
    count: int = Field(default=5, description="Number of events to send")
    sleep: int = Field(
        default=1, description="the number of seconds to sleep until next event")


class Request(BaseModel):
    jschema: str = Field("urn:sd:schema:ai-tester.request.1", alias="$schema")
    echo: str | None = Field(None, description="a string to echo in result")
    call: CallTester | None = Field(
        None, description="Optionally call a service")
    llm: LlmTester | None = Field(
        None, description="Optionally callan LLM's completion service")
    wordle: WordleProps | None = Field(
        None, description="Optionally play a wordle game")
    create_oom_error: bool | None = Field(
        False, description="Optionally cause an OOM error")
    sleep: int | None = Field(
        0, description="the number of seconds to sleep before replying")
    raise_error: str | None = Field(
        None, description="raise an error with this message")
    events: EventTester | None = Field(
        None, description="Optionally create lots of events")


class RequestContext(BaseModel):
    headers: list[tuple[str, str]]
    method: str
    url: str

    @classmethod
    def from_freq(cls, freq: FRequest):
        return cls(
            headers=freq.headers.items(),
            method=freq.method,
            url=str(freq.url)
        )


class Result(BaseModel):
    jschema: str = Field("urn:sd:schema:ai-tester.1", alias="$schema")
    echo: str | None = Field(None, description="echos string from request")
    call_result: dict | None = Field(
        None, description="result of executing the 'call'")
    llm_result: dict | None = Field(
        None, description="result of executing the 'llm'")
    wordle_result: WordleResult | None = Field(
        None, description="result of executing the 'wordle' game")
    request: RequestContext = Field(
        description="information on the incoming request")
    run_time: float = Field(description="time in seconds this job took")

# class ExecCtxt(ExecutionContext, BaseModel):
#     msg: str


@ivcap_ai_tool("/", opts=ToolOptions(tags=["Test Tool"], service_id="/"))
def tester(req: Request, freq: FRequest, jobCtxt: JobContext) -> Result:
    """
    Run various tests

    This is a simple test harness to execute various functionalities
    """
    result = Result(run_time=0, request=RequestContext.from_freq(freq))
    start_time = time()  # Start timer

    with jobCtxt.report.step("main", f"Start tool execution for {freq.url}") as step:
        if req.echo is not None:
            result.echo = req.echo

        if req.call is not None:
            result.call_result = make_request(req.call)

        if req.llm is not None:
            result.llm_result = completion(req.llm)

        if req.wordle is not None:
            result.wordle_result = play_random_wordle(req.wordle)

        if req.events is not None:
            send_events(req.events, jobCtxt)

        if req.create_oom_error:
            # This will eventually raise a MemoryError or be killed by the OS
            data = []
            while True:
                data.append(' ' * 100_000_000)

        if req.sleep > 0:
            sleep(req.sleep)

        if req.raise_error:
            raise BaseException(req.raise_error)

        result.run_time = round(time() - start_time, 2)
        step.finished(f"Finished tool execution in {result.run_time} seconds")
    return result


@ivcap_ai_tool("/async", opts=ToolOptions(tags=["Test Tool"], service_id="/"))
async def async_tester(req: Request, freq: FRequest) -> Result:
    """
    Run various tests in 'async' mode
    """
    result = Result(run_time=0, request=RequestContext.from_freq(freq))
    start_time = time()  # Start timer

    if req.echo is not None:
        result.echo = req.echo

    if req.call is not None:
        raise Exception("not implemented")

    if req.llm is not None:
        result.llm_result = await async_completion(req.llm)

    if req.wordle is not None:
        result.wordle_result = play_random_wordle(req.wordle)

    if req.create_oom_error:
        # This will eventually raise a MemoryError or be killed by the OS
        data = []
        while True:
            data.append(' ' * 100_000_000)

    if req.sleep > 0:
        await async_sleep(req.sleep)

    result.run_time = round(time() - start_time, 2)
    return result


def completion(req: LlmTester):
    import openai

    try:
        client = create_openai_client(openai.OpenAI)
        response = client.chat.completions.create(
            model=req.model, messages=req.messages)
        return format_llm_response(response)
    except Exception as ex:
        logger.warning(f"llm execution failed - {ex}")
        raise ex


async def async_completion(req: LlmTester):
    import openai

    client = create_openai_client(openai.AsyncOpenAI)
    response = await client.chat.completions.create(model=req.model, messages=req.messages)
    return format_llm_response(response)


def format_llm_response(response):
    messages = [c.message.model_dump() for c in response.choices]
    usage = response.usage.model_dump()
    return {"messages": messages, "usage": usage}


def create_openai_client(f):
    base_url = os.getenv("LITELLM_PROXY")
    if base_url is None:
        return f()
    else:
        return f(base_url=f"{base_url}/v1", api_key="not-needed")


def make_request(req: CallTester) -> Any:
    """
    Makes a generic HTTP request.

    :param request_data: CallTester object containing request details.
    :return: JSON response or error message.
    """
    try:
        url = str(req.url)
        params = req.params
        response = httpx.request(
            method=req.method.upper(),
            url=url,
            params=params,
            json=req.data,
            headers=req.headers,
            timeout=req.timeout
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx, 5xx)
        return response.json()

    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def send_events(req: EventTester, jobCtxt: JobContext):
    for i in range(req.count):
        with jobCtxt.report.step("work", message=f"step#{i}"):
            sleep(req.sleep)
    jobCtxt.report.emit(GenericEvent(name="finished"))


# add_tool_api_route(app, "/", tester, opts=ToolOptions(tags=["Test Tool"], service_id="/"), context=ExecCtxt(msg="Boo!"))
# add_tool_api_route(app, "/async", async_tester, opts=ToolOptions(tags=["Test Tool"]))

if __name__ == "__main__":
    import argparse

    def custom_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
        parser.add_argument('--litellm-proxy', type=str,
                            help='Address of the the LiteLlmProxy')
        args = parser.parse_args()
        if args.litellm_proxy is not None:
            os.environ["LITELLM_PROXY"] = args.litellm_proxy
        return args

    start_tool_server(service, custom_args=custom_args)
