import os
import sys
import math
from time import sleep, time
from typing import List, Optional, Tuple
from httpcore import URL
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request as FRequest
import requests
from signal import signal, SIGTERM
from asyncio import sleep as async_sleep

this_dir = os.path.dirname(__file__)
src_dir = os.path.abspath(os.path.join(this_dir, "../../src"))
sys.path.insert(0, src_dir)

from ivcap_fastapi import getLogger, logging_init
from ivcap_ai_tool import start_tool_server, add_tool_api_route, ToolOptions

logging_init()
logger = getLogger("app")

# shutdown pod cracefully
signal(SIGTERM, lambda _1, _2: sys.exit(0))

title="AI Test Tool for IVCAP"
description = """
Test tool to exercise various aspects of the IVCAP platform.
"""

app = FastAPI(
    title=title,
    description=description,
    version=os.environ.get("VERSION", "???"),
    contact={
        "name": "Max Ott",
        "email": "max.ott@data61.csiro.au",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/license/MIT",
    },
    docs_url="/api",
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

class Request(BaseModel):
    jschema: str = Field("urn:sd:schema:ai-tester.request.1", alias="$schema")
    echo: Optional[str] = Field(None, description="a string to echo in result")
    call: Optional[CallTester] = Field(None, description="Optionally call a service")
    sleep: Optional[int] = Field(0, description="the number of seconds to sleep before replying")

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
    request: RequestContext = Field(description="information on the incoming request")
    run_time: float = Field(description="time in seconds this job took")


def tester(req: Request, freq: FRequest) -> Result:
    """
    Run various tests
    """
    result = Result(run_time=0, request=RequestContext.from_freq(freq))
    start_time = time()  # Start timer

    if req.echo != None:
        result.echo = req.echo

    if req.call != None:
        result.call_result = make_request(req.call)

    if req.sleep > 0:
        sleep(req.sleep)

    result.run_time = round(time() - start_time, 2)
    return result

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

    if req.sleep > 0:
        await async_sleep(req.sleep)

    result.run_time = round(time() - start_time, 2)
    return result


def make_request(req: CallTester) -> Any:
    """
    Makes a generic HTTP request.

    :param request_data: CallTester object containing request details.
    :return: JSON response or error message.
    """
    try:
        url = str(req.url)
        params = req.params
        response = requests.request(
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

add_tool_api_route(app, "/", tester, opts=ToolOptions(tags=["Test Tool"]))
add_tool_api_route(app, "/async", async_tester, opts=ToolOptions(tags=["Test Tool"]))

if __name__ == "__main__":
    start_tool_server(app, tester)
