import os
import sys
import math
from pydantic import BaseModel, Field
from fastapi import FastAPI
from signal import signal, SIGTERM

this_dir = os.path.dirname(__file__)
src_dir = os.path.abspath(os.path.join(this_dir, "../../src"))
sys.path.insert(0, src_dir)

from ivcap_fastapi import getLogger, logging_init
from ivcap_ai_tool import start_tool_server, add_tool_api_route, ToolOptions

logging_init()
logger = getLogger("app")

# shutdown pod cracefully
signal(SIGTERM, lambda _1, _2: sys.exit(0))

title="AI tool to check for prime numbers"
description = """
AI tool to help determining if a number is a prime number.
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
    root_path=os.environ.get("IVCAP_ROOT_PATH", "")
)

class Request(BaseModel):
    jschema: str = Field("urn:sd:schema:is-prime.request.1", alias="$schema")
    number: int = Field(description="the number to check if prime")

class Result(BaseModel):
    jschema: str = Field("urn:sd:schema:is-prime.1", alias="$schema")
    flag: bool = Field(description="true if number is prime, false otherwise")

def is_prime(req: Request) -> Result:
    """
    Checks if a number is prime.
    """
    number = req.number
    if number <= 1:
        return Result(flag=False)
    if number <= 3:
        return Result(flag=True)
    if number % 2 == 0 or number % 3 == 0:
        return Result(flag=False)

    for i in range(5, int(math.sqrt(number)) + 1, 6):
        if number % i == 0 or number % (i + 2) == 0:
            return Result(flag=False)

    return Result(flag=True)

add_tool_api_route(app, "/", is_prime, opts=ToolOptions(tags=["Prime Checker"]))

if __name__ == "__main__":
    start_tool_server(app, is_prime)
