import os
import sys
from time import sleep, time
from typing import List, Optional, Tuple
import httpx
from pydantic import BaseModel, Field
from fastapi import Request as FRequest
import requests
from asyncio import sleep as async_sleep

from ivcap_ai_tool.executor import JobContext

this_dir = os.path.dirname(__file__)
src_dir = os.path.abspath(os.path.join(this_dir, "../../src"))
sys.path.insert(0, src_dir)

from ivcap_service import getLogger, Service
from ivcap_ai_tool import start_tool_server, ivcap_ai_tool, ToolOptions, logging_init

logging_init()
logger = getLogger("app")


service = Service(
    name="AI Test Tool for IVCAP",
    description= """
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

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl

class CallTester(BaseModel):
    method: str = Field(..., description="The HTTP method to use (GET, POST, PUT, DELETE, etc.).",
        pattern="^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$"  # Only allow valid methods
    )
    url: HttpUrl = Field(..., description="The full URL of the API endpoint.")
    params: Optional[Dict[str, Any]] = Field(None, description="Optional dictionary of query parameters to be appended to the URL.")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional JSON payload to be sent in the request body (for POST/PUT).")
    headers: Optional[Dict[str, str]] = Field(None, description="Optional dictionary of headers to include in the request.")
    timeout: int = Field(5, description="The timeout duration for the request in seconds.",
        ge=1  # Minimum value of 1 second to prevent infinite waiting
    )

class ChatMessage(BaseModel):
    content: str = Field(..., description="The content of this message.")
    role: str = Field(..., description="The role of the messages author.")
    name: Optional[str] = Field(None, description="An optional name for the participant.")

class LlmTester(BaseModel):
    messages: List[ChatMessage] = Field(..., description="A list of messages to be passed to the LLM.")
    model: Optional[str] = Field("gpt-3.5-turbo", description="The LLM model to use [gpt-3.5-turbo].")

class Request(BaseModel):
    jschema: str = Field("urn:sd:schema:ai-tester.request.1", alias="$schema")
    echo: Optional[str] = Field(None, description="a string to echo in result")
    call: Optional[CallTester] = Field(None, description="Optionally call a service")
    llm: Optional[LlmTester] = Field(None, description="Optionally callan LLM's completion service")
    sleep: Optional[int] = Field(0, description="the number of seconds to sleep before replying")
    raise_error: Optional[str] = Field(None, description="raise an error with this message")

class RequestContext(BaseModel):
    headers: List[Tuple[str, str]]
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
    echo: Optional[str] = Field(None, description="echos string from request")
    call_result: Optional[Dict] = Field(None, description="result of executing the 'call'")
    llm_result: Optional[Dict] = Field(None, description="result of executing the 'llm'")
    request: RequestContext = Field(description="information on the incoming request")
    run_time: float = Field(description="time in seconds this job took")


# class ExecCtxt(ExecutionContext, BaseModel):
#     msg: str

@ivcap_ai_tool("/", opts=ToolOptions(tags=["Test Tool"], service_id="/"))
def tester(req: Request, freq: FRequest, jobCtxt: JobContext) -> Result:
    """
    Run various tests
    """
    result = Result(run_time=0, request=RequestContext.from_freq(freq))
    start_time = time()  # Start timer

    jobCtxt.report.step_started("main", f"Start tool execution for {freq.url}")
    if req.echo != None:
        result.echo = req.echo

    if req.call != None:
        result.call_result = make_request(req.call)

    if req.llm != None:
        result.llm_result = completion(req.llm)

    if req.sleep > 0:
        sleep(req.sleep)

    if req.raise_error:
        raise BaseException(req.raise_error)

    result.run_time = round(time() - start_time, 2)
    jobCtxt.report.step_finished("main", f"Finished tool execution in {result.run_time} seconds")
    return result

@ivcap_ai_tool("/async", opts=ToolOptions(tags=["Test Tool"], service_id="/"))
async def async_tester(req: Request, freq: FRequest) -> Result:
    """
    Run various tests in 'async' mode
    """
    result = Result(run_time=0, request=RequestContext.from_freq(freq))
    start_time = time()  # Start timer

    if req.echo != None:
        result.echo = req.echo

    if req.call != None:
        raise Exception("not implemented")

    if req.llm != None:
        result.llm_result = await async_completion(req.llm)

    if req.sleep > 0:
        await async_sleep(req.sleep)

    result.run_time = round(time() - start_time, 2)
    return result

def completion(req: LlmTester):
    import openai

    try:
        client =  create_openai_client(openai.OpenAI)
        response = client.chat.completions.create(model=req.model, messages=req.messages)
        return format_llm_response(response)
    except Exception as ex:
        logger.warning(f"llm execution failed - {ex}")
        raise ex

async def async_completion(req: LlmTester):
    import openai

    client =  create_openai_client(openai.AsyncOpenAI)
    response = await client.chat.completions.create(model=req.model, messages=req.messages)
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
            timeout=req.timeout
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx, 5xx)
        return response.json()

    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

# add_tool_api_route(app, "/", tester, opts=ToolOptions(tags=["Test Tool"], service_id="/"), context=ExecCtxt(msg="Boo!"))
# add_tool_api_route(app, "/async", async_tester, opts=ToolOptions(tags=["Test Tool"]))

if __name__ == "__main__":
    import argparse
    def custom_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
        parser.add_argument('--litellm-proxy', type=str, help='Address of the the LiteLlmProxy')
        args = parser.parse_args()
        if args.litellm_proxy != None:
            os.setenv("LITELLM_PROXY", args.litellm_proxy)
        return args

    start_tool_server(service, custom_args=custom_args)
