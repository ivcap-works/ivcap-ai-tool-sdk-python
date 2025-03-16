#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import asyncio
import concurrent.futures
import threading
import traceback
from typing import Any, Callable, Generic, Optional, TypeVar, Union
from cachetools import TTLCache
from fastapi import Request
from pydantic import BaseModel, Field
from ivcap_fastapi import getLogger
from opentelemetry import trace, context
from opentelemetry.context.context import Context


from .utils import _get_input_type

logger = getLogger("executor")
tracer = trace.get_tracer("executor")

class ExecutionContext(BaseModel):
    pass

T = TypeVar('T')

class ExecutorOpts(BaseModel):
    job_cache_size: Optional[int] = Field(1000, description="size of job cache")
    job_cache_ttl: Optional[int] = Field(600, description="TTL of job entries in the job cache")
    max_workers: Optional[int] = Field(None, description="size of thread pool to use. If None, a new thread pool will be created for each execution")

class ExecutionError(BaseModel):
    """
    Pydantic model for execution errors.
    """
    error: str
    type: type # type of error
    traceback: str

class ExecutionContext(threading.local):
    job_id: Optional[str] = None
    authorization: Optional[str] = None

class Executor(Generic[T]):
    """
    A generic class that executes a function in a thread pool and returns the result via an asyncio Queue.
    The generic type T represents the return type of the function.
    """

    _exex_ctxt = ExecutionContext()

    @classmethod
    def job_id(cls) -> str:
        return cls._exex_ctxt.job_id

    @classmethod
    def job_authorization(cls) -> str:
        return cls._exex_ctxt.authorization

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
        def _callback(future):
            """Callback to handle the future result and put it in the queue."""
            try:
                result = future.result()
            except Exception as e:
                result = ExecutionError(
                    error=str(e),
                    type=type(e),
                    traceback=traceback.format_exc()
                )
                logger.warning(f"job {job_id} failed - {result.error}")
            finally:
                self.job_cache[job_id] = result
                asyncio.run_coroutine_threadsafe(
                    result_queue.put(result),
                    event_loop,
                )

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
                    if asyncio.iscoroutinefunction(self.func):
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        res = loop.run_until_complete(self.func(param, **kwargs))
                        loop.close()  # Clean up event loop
                        return res
                    else:
                        return self.func(param, **kwargs)
                except Exception as ex:
                    span.record_exception(ex)
                    raise ex
                finally:
                    self._exex_ctxt.job_id = None
                    self._exex_ctxt.authorizaton = None
                    if loop != None:
                        loop.close


        # Use the provided thread pool or create a new one
        use_pool = self.thread_pool or concurrent.futures.ThreadPoolExecutor(max_workers=1)

        # Submit the function to the thread pool
        future = use_pool.submit(_run, param, context.get_current())
        future.add_done_callback(_callback)

        # If we created a new pool, we should clean it up when done
        if self.thread_pool is None:
            future.add_done_callback(lambda _: use_pool.shutdown(wait=False))

        return result_queue

    def lookup_job(self, job_id: str) -> Union[T, ExecutionError, None]:
        """Return the result of a

        Args:
            job_id (str): The id of the job requested

        Returns:
            Union[T, ExecutionError, None]: Returns the result fo a job, 'None' is still in progress

        Raises:
            KeyError: Unknown job - may have already expired
        """
        return self.job_cache[job_id]
