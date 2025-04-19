
from dataclasses import dataclass
import io
import json
import time
import traceback
from typing import BinaryIO, Callable, Union
import argparse
from logging import Logger
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse, urlunparse
from fastapi import FastAPI, Request, Response
import httpx
import uvicorn
import os
import sys
import signal
from pydantic import BaseModel, Field
import requests  # Import the requests library

from ivcap_fastapi import service_log_config, getLogger
# Number of attempt to request a new job before giving up
MAX_REQUEST_JOB_ATTEMPTS = 4

def wait_for_work(worker_fn: Callable, input_model: type[BaseModel], output_model: type[BaseModel], logger: Logger):
    ivcap_url = get_ivcap_url()
    if ivcap_url is None:
        logger.warning(f"no ivcap url found - cannot request work")
        return
    url = urlunparse(ivcap_url._replace(path=f"/next_job"))
    logger.info(f"... checking for work at '{url}'")
    try:
        response = fetch_job(url, logger)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        while True:
            try:
                job = response.json()
                schema = job.get("$schema", "")
                if schema.startswith("urn:ivcap:schema.service.batch.done"):
                    logger.info("no more jobs - we are done")
                    sys.exit(0)

                job_id = job.get("id", "unknown_job_id")  # Provide a default value if "id" is missing
                result = do_job(job, worker_fn, input_model, output_model, logger)
                result = verify_result(result, job_id)
            except Exception as e:
                result = ExecutionError(
                    error=str(e),
                    type=type(e).__name__,
                    traceback=traceback.format_exc()
                )
                logger.warning(f"job {job_id} failed - {result.error}")
            finally:
                logger.info(f"job {job_id} finished, sending result message")
                push_result(result, job_id)

    except requests.exceptions.RequestException as e:
        logger.warning(f"Error during request: {e}")
    except Exception as e:
        logger.warning(f"Error processing job: {e}")

def fetch_job(url: str, logger: Logger) -> Any:
    wait_time = 1
    attempt = 0
    while attempt < MAX_REQUEST_JOB_ATTEMPTS:
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response
        except Exception as e:
            attempt += 1
            logger.info(f"attempt #{attempt} failed to fetch new job - will try again in {wait_time} sec - {type(e)}: {e}")
            time.sleep(wait_time)
            wait_time *= 2
    logger.info("cannot contact sidecar - bailing out")
    sys.exit(255)

def do_job(
    job: Any,
    worker_fn: Callable,
    input_model: type[BaseModel],
    output_model: type[BaseModel],
    logger: Logger
):
    job_id = job.get("id", "unknown_job_id")  # Provide a default value if "id" is missing
    ct = job["in-content-type"]
    if ct != "application/json":
        raise Exception(f"cannot handle content-type '{ct}'")
    jc = job["in-content"]
    mreq = input_model(**jc)
    logger.info(f"{job_id}: calling worker with - {mreq}")
    try:
        resp = worker_fn(mreq)
        logger.info(f"{job_id}: worker finished with - {resp}")
        if type(resp) != output_model:
            logger.warning(f"{job_id}: result is of type '{type(resp)}' but expected '{output_model}'")

    except BaseException as ex:
        logger.warning(f"{job_id}: failed - '{ex}'")
        resp = ExecutionError(
                        error=str(ex),
                        type=type(ex).__name__,
                        traceback=traceback.format_exc()
                    )
    return resp

def start_service(
    title: str,
    worker_fn: Callable,
    *,
    custom_args: Optional[Callable[[argparse.ArgumentParser], argparse.Namespace]] = None,
    run_opts: Optional[Dict[str, Any]] = None,
    with_telemetry: Optional[bool] = None,
):
    """A helper function to start a batch service

    Args:
        title (str): the tile
        tool_fn (Callable[..., Any]): _description_
        logger (Logger): _description_
        custom_args (Optional[Callable[[argparse.ArgumentParser], argparse.Namespace]], optional): _description_. Defaults to None.
        run_opts (Optional[Dict[str, Any]], optional): _description_. Defaults to None.
        with_telemetry: (Optional[bool]): Instantiate or block use of OpenTelemetry tracing
    """
    logger = getLogger("server")

    parser = argparse.ArgumentParser(description=title)
    parser.add_argument('--with-telemetry', action="store_true", help='Initialise OpenTelemetry')
    parser.add_argument('--test-file', type=str, help='path to job file for testing service')

    if custom_args is not None:
        args = custom_args(parser)
    else:
        args = parser.parse_args()

    logger.info(f"{title} - {os.getenv('VERSION')} - v{get_version()}")

    input_model, _ = _get_input_type(worker_fn)
    output_model = _get_function_return_type(worker_fn)
    summary, description = (worker_fn.__doc__.lstrip() + "\n").split("\n", 1)

    if args.test_file is not None:
        from testing import file_to_http_response
        import httpx
        resp = file_to_http_response(args.test_file, headers={"Content-Type": "application/json"})
        do_job(resp, worker_fn, input_model, output_model, logger)
    else:
        wait_for_work(worker_fn, input_model, output_model, logger)

##### COMMON TO executor

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


def verify_result(result: any, job_id: str, logger) -> any:
    if isinstance(result, ExecutionError):
        return result
    if isinstance(result, BaseModel):
        try:
            return IvcapResult(
                content=result.model_dump_json(by_alias=True),
                content_type="application/json",
                raw=result,
            )
        except Exception as ex:
            msg = f"{job_id}: cannot json serialise pydantic isntance - {str(ex)}"
            logger.warning(msg)
            return ExecutionError(
                error=msg,
                type=type(ex).__name__,
                traceback=traceback.format_exc()
            )
    if isinstance(result, BinaryResult):
        return IvcapResult(content=result.content, content_type=result.content_type)
    if isinstance(result, str):
        return IvcapResult(content=result, content_type="text/plain", raw=result)
    if isinstance(result, bytes):
        # If it's a byte array, return it as is
        return IvcapResult(
            content=result,
            content_type="application/octet-stream",
            raw=result,
        )
    if isinstance(result, BinaryIO):
        # If it's a file handler, return it as is
        return IvcapResult(
            content=result,
            content_type="application/octet-stream",
            raw=result
        )
    # normal model which should be serialisable
    try:
        result = IvcapResult(
            content=json.dumps(result),
            content_type="application/json"
        )
    except Exception as ex:
        msg = f"{job_id}: cannot json serialise result - {str(ex)}"
        logger.warning(msg)
        result = ExecutionError(
            error=msg,
            type=type(ex).__name__,
        )

def push_result(result: any, job_id: str, authorization: str, logger):
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
        msg = f"{job_id}: expected 'BinaryResult' or 'ExecutionError' but got {type(result)}"
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
    if authorization is not None or authorization != "":
        headers["Authorization"] = authorization

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
            time.sleep(wait_time)
            wait_time *= 2

    logger.warning(f"{job_id}: giving up pushing result after {attempt} attempts")


##### COMMON TO ai-tool

import inspect
import os
import re
from typing import Optional, Type, Callable, TypeVar, Any, get_type_hints, Union, Dict, Tuple

from pydantic import BaseModel, HttpUrl

def get_version():
    return "???"

def _get_input_type(func: Callable) -> Tuple[Optional[Type[BaseModel]], Dict[str, Any]]:
    """Gets the input type of a function.

    Args:
        func: The function to get the input type for.

    Returns:
        A tuple containing:
        - The first function parameter which is a derived class of a pydantic BaseModel, or None if no such parameter exists.
        - A dictionary of all additional parameters, where the key is the parameter name and the value is the type.
    """
    signature = inspect.signature(func)
    type_hints = get_type_hints(func)

    # Get the Pydantic model class
    pydantic_model_class = None
    pydantic_param_name = None
    for param_name, param in signature.parameters.items():
        if hasattr(param.annotation, '__mro__') and BaseModel in param.annotation.__mro__:
            pydantic_model_class = param.annotation
            pydantic_param_name = param_name
            break

    # Get all additional parameters
    additional_params = {}
    for param_name, param in signature.parameters.items():
        if param_name != pydantic_param_name:
            param_type = type_hints.get(param_name, Any)
            additional_params[param_name] = param_type

    return pydantic_model_class, additional_params

def _get_function_return_type(func):
    """Extracts the return type from a function."""
    type_hints = get_type_hints(func)
    # param_types = {k: v for k, v in type_hints.items() if k != 'return'}
    return_type = type_hints.get('return')
    # return param_types, return_type
    return return_type

def get_ivcap_url() -> HttpUrl:
    """
    Returns the sidecar URL from the request headers.
    """
    base = os.getenv("IVCAP_BASE_URL")
    if base == "":
        return None
    return urlparse(base)
