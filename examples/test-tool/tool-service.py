from ivcap_service.events import GenericEvent
import os
import sys
from time import sleep, time
from typing import List, Optional, Tuple
import httpx
from pydantic import BaseModel, Field
from fastapi import Request as FRequest
import requests
from asyncio import sleep as async_sleep
from typing import Dict, Any
from pydantic import HttpUrl


from ivcap_service import getLogger, Service, with_schema
from ivcap_lambda import start_tool_server, ivcap_lambda, ToolOptions, logging_init

from wordle import WordleProps, WordleResult, play_random_wordle

from ivcap_lambda.executor import JobContext

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


class ArtifactDownloader(BaseModel):
    artifact_id: str = Field(
        ...,
        description="The URN of the artifact to download.",
    )
    block_size: int = Field(
        8192,
        description="Number of bytes to read per chunk when streaming the artifact.",
        ge=1,
    )
    max_size: Optional[int] = Field(
        None,
        description="Optional maximum total bytes to download before stopping early.",
        ge=1,
    )


class CallTester(BaseModel):
    method: str = Field(
        ...,
        description="The HTTP method to use (GET, POST, PUT, DELETE, etc.).",
        pattern="^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$",  # Only allow valid methods
    )
    url: HttpUrl = Field(..., description="The full URL of the API endpoint.")
    params: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional dictionary of query parameters to be appended to the URL.",
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional JSON payload to be sent in the request body (for POST/PUT).",
    )
    headers: Optional[Dict[str, str]] = Field(
        None, description="Optional dictionary of headers to include in the request."
    )
    timeout: int = Field(
        5,
        description="The timeout duration for the request in seconds.",
        ge=1,  # Minimum value of 1 second to prevent infinite waiting
    )


class ChatMessage(BaseModel):
    content: str = Field(..., description="The content of this message.")
    role: str = Field(..., description="The role of the messages author.")
    name: Optional[str] = Field(
        None, description="An optional name for the participant."
    )


class LlmTester(BaseModel):
    messages: List[ChatMessage] = Field(
        ..., description="A list of messages to be passed to the LLM."
    )
    model: Optional[str] = Field(
        "gpt-3.5-turbo", description="The LLM model to use [gpt-3.5-turbo]."
    )


class EventTester(BaseModel):
    count: int = Field(default=5, description="Number of events to send")
    sleep: int = Field(
        default=1, description="the number of seconds to sleep until next event"
    )


@with_schema("urn:sd:schema:ai-tester.request.1")
class Request(BaseModel):
    echo: Optional[str] = Field(None, description="a string to echo in result")
    call: Optional[CallTester] = Field(None, description="Optionally call a service")
    llm: Optional[LlmTester] = Field(
        None, description="Optionally callan LLM's completion service"
    )
    wordle: Optional[WordleProps] = Field(
        None, description="Optionally play a wordle game"
    )
    create_oom_error: Optional[bool] = Field(
        False, description="Optionally cause an OOM error"
    )
    sleep: Optional[int] = Field(
        0, description="the number of seconds to sleep before replying"
    )
    raise_error: Optional[str] = Field(
        None, description="raise an error with this message"
    )
    events: Optional[EventTester] = Field(
        None, description="Optionally create lots of events"
    )
    download_artifact: Optional[ArtifactDownloader] = Field(
        None, description="Optionally download an artifact by its URN"
    )


class RequestContext(BaseModel):
    headers: List[Tuple[str, str]]
    method: str
    url: str

    @classmethod
    def from_freq(cls, freq: FRequest):
        return cls(headers=freq.headers.items(), method=freq.method, url=str(freq.url))


@with_schema("urn:sd:schema:ai-tester.1")
class Result(BaseModel):
    echo: Optional[str] = Field(None, description="echos string from request")
    call_result: Optional[Dict] = Field(
        None, description="result of executing the 'call'"
    )
    llm_result: Optional[Dict] = Field(
        None, description="result of executing the 'llm'"
    )
    wordle_result: Optional[WordleResult] = Field(
        None, description="result of executing the 'wordle' game"
    )
    artifact_result: Optional[Dict] = Field(
        None, description="result of downloading an artifact"
    )
    request: RequestContext = Field(description="information on the incoming request")
    run_time: float = Field(description="time in seconds this job took")


# class ExecCtxt(ExecutionContext, BaseModel):
#     msg: str


@ivcap_lambda("/", opts=ToolOptions(tags=["Test Tool"], service_id="/"))
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

        if req.download_artifact is not None:
            result.artifact_result = download_artifact_content(
                req.download_artifact, jobCtxt
            )

        if req.create_oom_error:
            # This will eventually raise a MemoryError or be killed by the OS
            data = []
            while True:
                data.append(" " * 100_000_000)

        if req.sleep > 0:
            sleep(req.sleep)

        if req.raise_error:
            raise BaseException(req.raise_error)

        result.run_time = round(time() - start_time, 2)
        step.finished(f"Finished tool execution in {result.run_time} seconds")
    return result


@ivcap_lambda("/async", opts=ToolOptions(tags=["Test Tool"], service_id="/"))
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
            data.append(" " * 100_000_000)

    if req.sleep > 0:
        await async_sleep(req.sleep)

    result.run_time = round(time() - start_time, 2)
    return result


def completion(req: LlmTester):
    import openai

    try:
        client = create_openai_client(openai.OpenAI)
        response = client.chat.completions.create(
            model=req.model, messages=req.messages
        )
        return format_llm_response(response)
    except Exception as ex:
        logger.warning(f"llm execution failed - {ex}")
        raise ex


async def async_completion(req: LlmTester):
    import openai

    client = create_openai_client(openai.AsyncOpenAI)
    response = await client.chat.completions.create(
        model=req.model, messages=req.messages
    )
    return format_llm_response(response)


def format_llm_response(response):
    messages = [c.message.model_dump() for c in response.choices]
    usage = response.usage.model_dump()
    return {"messages": messages, "usage": usage}


def create_openai_client(f):
    base_url = os.getenv("LITELLM_PROXY")
    if base_url == None:
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
            timeout=req.timeout,
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx, 5xx)
        return response.json()

    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def send_events(req: EventTester, jobCtxt: JobContext):
    for i in range(req.count):
        with jobCtxt.report.step("work", message=f"step#{i}"):
            sleep(req.sleep)
    jobCtxt.report.emit(GenericEvent(name=f"finished"))


def download_artifact_content(req: ArtifactDownloader, jobCtxt: JobContext) -> Dict:
    """Stream an artifact by URN using the ivcap_client SDK and return a
    summary dict containing metadata and download statistics.

    Iterates over artifact.as_stream() chunks, emitting a job event for every
    block via step.info() with a running byte total.  All downloaded data is
    discarded.  Stops early when max_size bytes have been received (if set).
    Errors during download are captured and reported in the result dict rather
    than propagating to the caller.
    """
    logger.info(
        f"downloading artifact '{req.artifact_id}' "
        f"(block_size={req.block_size}, max_size={req.max_size})"
    )

    chunks_received = 0
    bytes_received = 0
    error = None
    artifact_id = req.artifact_id
    artifact_name = None
    artifact_size = None
    artifact_mime_type = None

    with jobCtxt.report.step(
        "download-artifact", f"Downloading artifact {req.artifact_id}"
    ) as step:
        try:
            artifact = jobCtxt.ivcap.get_artifact(req.artifact_id)
            artifact_id = artifact.id
            artifact_name = getattr(artifact, "name", None)
            artifact_size = getattr(artifact, "size", None)
            artifact_mime_type = getattr(artifact, "mime_type", None)

            for chunk in artifact.as_stream(chunk_size=req.block_size):
                chunks_received += 1
                bytes_received += len(chunk)
                step.info(
                    GenericEvent(
                        name="artifact-chunk",
                        options={
                            "chunk": chunks_received,
                            "bytes_this_chunk": len(chunk),
                            "bytes_total": bytes_received,
                        },
                    )
                )
                if req.max_size is not None and bytes_received >= req.max_size:
                    logger.info(
                        f"stopping early: reached max_size={req.max_size} "
                        f"after {chunks_received} chunks ({bytes_received} bytes)"
                    )
                    break

        except Exception as ex:
            logger.warning(
                f"artifact download failed after {chunks_received} chunks "
                f"({bytes_received} bytes) - {ex}"
            )
            error = str(ex)

        size_info = f" of {artifact_size}" if artifact_size is not None else ""
        step.finished(
            f"downloaded {chunks_received} chunks / {bytes_received} bytes{size_info}"
            + (" [error]" if error else "")
        )

    return {
        "artifact_id": artifact_id,
        "name": artifact_name,
        "artifact_size": artifact_size,
        "mime_type": artifact_mime_type,
        "chunks_received": chunks_received,
        "bytes_received": bytes_received,
        "stopped_early": req.max_size is not None and bytes_received >= req.max_size,
        "error": error,
    }


# add_tool_api_route(app, "/", tester, opts=ToolOptions(tags=["Test Tool"], service_id="/"), context=ExecCtxt(msg="Boo!"))
# add_tool_api_route(app, "/async", async_tester, opts=ToolOptions(tags=["Test Tool"]))

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

    start_tool_server(service, custom_args=custom_args)
