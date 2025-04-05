#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import asyncio
import httpx
from dataclasses import dataclass
import io
import concurrent.futures
import json
import threading
from time import sleep
import traceback
from typing import Any, Callable, Generic, List, Optional, TypeVar, Union, BinaryIO
from urllib.parse import urlunparse
from cachetools import TTLCache
from fastapi import Request
from pydantic import BaseModel, Field
from ivcap_fastapi import getLogger
from opentelemetry import trace, context
from opentelemetry.context.context import Context

from .utils import _get_input_type, get_ivcap_url

# Number of attempt to deliver job result before giving up
MAX_DELIVER_RESULT_ATTEMPTS = 4

logger = getLogger("executor")
tracer = trace.get_tracer("executor")

class ExecutionContext(threading.local):
    job_id: Optional[str] = None
    authorization: Optional[str] = None

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

T = TypeVar('T')

class ExecutorOpts(BaseModel):
    job_cache_size: Optional[int] = Field(1000, description="size of job cache")
    job_cache_ttl: Optional[int] = Field(600, description="TTL of job entries in the job cache")
    max_workers: Optional[int] = Field(None, description="size of thread pool to use. If None, a new thread pool will be created for each execution")

class ExecutionError(BaseModel):
    """
    Pydantic model for execution errors.
    """
    jschema: str = Field("urn:ivcap:schema.ai-tool.error.1", alias="$schema")
    error: str = Field(description="Error message")
    type: str = Field(description="Error type")
    traceback: Optional[str]

class Executor(Generic[T]):
    """
    A generic class that executes a function in a thread pool and returns the result via an asyncio Queue.
    The generic type T represents the return type of the function.
    """

    _exex_ctxt = ExecutionContext()
    _active_jobs = set() # keep track of active jobs to block shutdown until they are done

    @classmethod
    def job_id(cls) -> str:
        return cls._exex_ctxt.job_id

    @classmethod
    def job_authorization(cls) -> str:
        return cls._exex_ctxt.authorization

    @classmethod
    def active_jobs(cls) -> List[str]:
        """Returns a list of IDs of the currently active jobs"""
        return list(cls._active_jobs)

    @classmethod
    def wait_for_exit_ready(cls):
        """The server is calling this method when a shutdown request arrived. It will
        proceed with the shutdown when this method returns.

        We may implement functionality to only return when all active jobs have finsihed, as well as not
        accepting any new incoming requests.
        """
        while len(cls._active_jobs) > 0:
            logger.info(f"blocking shutdown as {len(cls._active_jobs)} job(s) are still running")
            sleep(5)
        return

    def __init__(
        self,
        func: Callable[..., T],
        *,
        opts: Optional[ExecutorOpts],
        context: Optional[ExecutionContext] = None
    ):
        """
        Initialize the Executor with a function and an optional thread pool.

        Args:
            func: The function to execute, returning type T
            opts:
             - job_cache_size: Optional size of job cache. Defaults to 1000
             - job_cache_ttl: Optional TTL of job entries in the job cache. Defaults to 600 sec
             - max_workers: Optional size of thread pool to use. If None, a new thread pool will be created for each execution.
        """
        self.func = func
        if opts is None:
            opts = ExecutorOpts()
        self.job_cache = TTLCache(maxsize=opts.job_cache_size, ttl=opts.job_cache_ttl)
        self.thread_pool = None
        if opts.max_workers:
            self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=opts.max_workers)

        self.context = context
        self.context_param = None
        self.request_param = None
        _, extras = _get_input_type(func)
        for k, v in extras.items():
            if isinstance(context, v):
                self.context_param = k
            if v == Request:
                self.request_param  = k

    async def execute(self, param: Any, job_id: str, req: Request) -> asyncio.Queue[Union[T, ExecutionError]]:
        """
        Execute the function with the given parameter in a thread and return a queue with the result.

        Args:
            param: Any The parameter to pass to the function
            job_id: str ID of this job
            req: Request FastAPI's request object

        Returns:
            An asyncio Queue that will contain either the result of type T or an ExecutionError
        """
        result_queue: asyncio.Queue[Union[T, ExecutionError]] = asyncio.Queue()
        event_loop = asyncio.get_event_loop()
        self.job_cache[job_id] = None

        def _process_result(result):
            """Verify the result, add it to the queue, and report it to IVCAP."""
            try:
                result = self._verify_result(result, job_id)
            except Exception as e:
                result = ExecutionError(
                    error=str(e),
                    type=type(e).__name__,
                    traceback=traceback.format_exc()
                )
                logger.warning(f"job {job_id} failed - {result.error}")
            finally:
                self.job_cache[job_id] = result
                logger.info(f"job {job_id} finished, sending result message")
                asyncio.run_coroutine_threadsafe(
                    result_queue.put(result),
                    event_loop,
                )
                self._push_result(result, job_id)
                self.__class__._active_jobs.discard(job_id)

        def _run(param: Any, ctxt: Context):
            context.attach(ctxt) # OTEL

            kwargs = {}
            if self.context_param is not None:
                kwargs[self.context_param] = self.context
            if self.request_param is not None:
                kwargs[self.request_param] = req

            self._exex_ctxt.job_id = job_id
            self._exex_ctxt.authorization = req.headers.get("authorization")
            fname = self.func.__name__
            with tracer.start_as_current_span(f"RUN {fname}") as span:
                span.set_attribute("job.id", job_id)
                span.set_attribute("job.name", fname)
                loop = None
                try:
                    self.__class__._active_jobs.add(job_id)
                    if asyncio.iscoroutinefunction(self.func):
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        res = loop.run_until_complete(self.func(param, **kwargs))
                        loop.close()  # Clean up event loop
                    else:
                        res = self.func(param, **kwargs)
                    _process_result(res)
                except Exception as ex:
                    span.record_exception(ex)
                    raise ex
                finally:
                    self.__class__._active_jobs.discard(job_id)
                    self._exex_ctxt.job_id = None
                    self._exex_ctxt.authorizaton = None
                    if loop != None:
                        loop.close


        # Use the provided thread pool or create a new one
        use_pool = self.thread_pool or concurrent.futures.ThreadPoolExecutor(max_workers=1)
        # Submit the function to the thread pool
        future = use_pool.submit(_run, param, context.get_current())

        # If we created a new pool, we should clean it up when done
        if self.thread_pool is None:
            future.add_done_callback(lambda _: use_pool.shutdown(wait=False))
        return result_queue

    def lookup_job(self, job_id: str) -> Union[T, ExecutionError, None]:
        """Return the result of a job

        Args:
            job_id (str): The id of the job requested

        Returns:
            Union[T, ExecutionError, None]: Returns the result fo a job, 'None' is still in progress

        Raises:
            KeyError: Unknown job - may have already expired
        """
        return self.job_cache[job_id]

    def _verify_result(self, result: any, job_id: str) -> any:
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
                    isErroe=True,
                    raw=result
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

    def _push_result(self, result: any, job_id: str):
        """Actively push result to sidecar, fail quietly."""
        content_type="text/plain"
        content="SOMETHING WENT WRONG _ PLEASE REPORT THIS ERROR"

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
            if isinstance(result, ExecutionError):
                content = result.model_dump_json(by_alias=True)
                content_type = "application/json"
            else:
                # this should never happen
                logger.error(f"{job_id}: expected 'ExecutionError' but got {type(result)}")
                content = json.dumps({"error": "please report unexpected internal error - expected 'ExecutionError' but got {type(result)}"})
                content_type = "application/json"

        wait_time = 1
        attempt = 0
        while attempt < MAX_DELIVER_RESULT_ATTEMPTS:
            try:
                url = get_ivcap_url()._replace(path=f"/results/{job_id}")
                with httpx.Client() as client:
                    client.post(
                        url=urlunparse(url),
                        headers={"Content-Type": content_type},
                        data=content,
                    )
                break
            except httpx.RequestError as e:
                attempt += 1
                logger.warning(f"{job_id}: attempt #{attempt} failed to push result - will try again in {wait_time} sec - {e}")
                sleep(wait_time)
                wait_time *= 2

        logger.warning(f"{job_id}: giving up pushing result after {attempt} attempts")
