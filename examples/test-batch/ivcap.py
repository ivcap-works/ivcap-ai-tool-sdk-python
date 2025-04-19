from dataclasses import Field, dataclass
import os
from typing import Any, Callable, Generic, List, Optional, TypeVar, Union, BinaryIO

from time import sleep
from urllib.parse import urlparse, urlunparse
import httpx
from pydantic import BaseModel, HttpUrl
from ivcap_fastapi import getLogger

logger = getLogger("ivcap")

# Number of attempt to deliver job result before giving up
MAX_DELIVER_RESULT_ATTEMPTS = 4

@dataclass
class BinaryResult():
    """If the result of the tool is a non json serialisable object, return an
    instance of this class indicating the content-type and the actual
    result either as a byte array or a file handle to a binary content (`open(..., "rb")`)"""
    content_type: str = Field(description="Content type of result serialised")
    content: Union[bytes, str, io.BufferedReader] = Field(description="Content to send, either as byte array or file handle")

@dataclass
class IvcapResult(BinaryResult):
    isError: bool = False
    raw: Any = None

class ExecutionError(BaseModel):
    """
    Pydantic model for execution errors.
    """
    jschema: str = Field("urn:ivcap:schema.ai-tool.error.1", alias="$schema")
    error: str = Field(description="Error message")
    type: str = Field(description="Error type")
    traceback: Optional[str] = Field(None, description="traceback")

def push_result(result: Union[IvcapResult, ExecutionError], job_id: str, auth_token: Optional[str]=None):
    """Actively push result to sidecar, fail quietly."""
    ivcap_url = get_ivcap_url()
    if ivcap_url is None:
        logger.warning(f"{job_id}: no ivcap url found - cannot push result")
        return
    url = urlunparse(ivcap_url._replace(path=f"/results/{job_id}"))

    content_type="text/plain"
    content="SOMETHING WENT WRONG _ PLEASE REPORT THIS ERROR"
    is_error = False
    if not (isinstance(result, ExecutionError) or isinstance(result, IvcapResult)):
        msg = f"{job_id}: expected 'IvcapResult' or 'ExecutionError' but got {type(result)}"
        logger.warning(msg)
        result = ExecutionError(
            error=msg,
            type='InternalError',
        )

    if isinstance(result, IvcapResult):
        content = result.content
        content_type = result.content_type
    else:
        is_error = True
        if not isinstance(result, ExecutionError):
            # this should never happen
            logger.error(f"{job_id}: expected 'ExecutionError' but got {type(result)}")
            result = ExecutionError(
                error="please report unexpected internal error - expected 'ExecutionError' but got {type(result)}",
                type="internal_error",
            )
        content = result.model_dump_json(by_alias=True)
        content_type = "application/json"


    wait_time = 1
    attempt = 0
    headers = {
        "Content-Type": content_type,
        "Is-Error": str(is_error),
    }
    if auth_token:
        headers["Authorization"] = auth_token

    while attempt < MAX_DELIVER_RESULT_ATTEMPTS:
        try:
            response = httpx.post(
                url=url,
                headers=headers,
                data=content,
            )
            response.raise_for_status()
            return
        except Exception as e:
            attempt += 1
            logger.info(f"{job_id}: attempt #{attempt} failed to push result - will try again in {wait_time} sec - {type(e)}: {e}")
            sleep(wait_time)
            wait_time *= 2

    logger.warning(f"{job_id}: giving up pushing result after {attempt} attempts")


def get_ivcap_url() -> HttpUrl:
    """
    Returns the sidecar URL from the request headers.
    """
    base = os.getenv("IVCAP_BASE_URL")
    if base == "":
        return None
    return urlparse(base)
