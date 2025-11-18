#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import asyncio
import contextvars
import concurrent.futures
import threading
from time import sleep
import traceback
import contextlib
from typing import Any, Callable, Generic, List, Optional, TypeVar, Union
from cachetools import TTLCache
from fastapi import Request
from pydantic import BaseModel, Field
from ivcap_service import getLogger
from opentelemetry import trace, context
from opentelemetry.context.context import Context

from ivcap_service import get_input_type, push_result, verify_result, EventReporter
from ivcap_service import ExecutionError, create_event_reporter, JobContext
from ivcap_client import IVCAP

# Number of attempt to deliver job result before giving up
MAX_DELIVER_RESULT_ATTEMPTS = 4

logger = getLogger("executor")
tracer = trace.get_tracer("executor")

class ExecutionContext:
    pass

class ThreadLocal(threading.local):
    pass

T = TypeVar('T')

class ExecutorOpts(BaseModel):
    job_cache_size: Optional[int] = Field(10000, description="size of job cache")
    job_cache_ttl: Optional[int] = Field(3600, description="TTL of job entries in the job cache")
    max_workers: Optional[int] = Field(None, description="size of thread pool to use. If None, a new thread pool will be created for each execution")

job_context = contextvars.ContextVar('ivcap', default=JobContext())

def get_job_context() -> JobContext:
    return job_context.get()

def get_event_reporter() -> Optional[EventReporter]:
    """Get the current event reporter from the job context."""
    return job_context.get().report

def get_job_id() -> Optional[EventReporter]:
    """Get the current job ID from the job context."""
    return job_context.get().job_id

class Executor(Generic[T]):
    """
    A generic class that executes a function in a thread pool and returns the result via an asyncio Queue.
    The generic type T represents the return type of the function.
    """

    # _job_ctxt = JobContext()
    _active_jobs = set() # keep track of active jobs to block shutdown until they are done

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
        context: Optional[JobContext] = None
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
        self.job_ctxt_param = None
        _, extras = get_input_type(func)
        for k, v in extras.items():
            if isinstance(context, v):
                self.context_param = k
            elif v == Request:
                self.request_param  = k
            elif v == JobContext:
                self.job_ctxt_param  = k
            else:
                raise Exception(f"unexpected function parameter '{k}'")

    async def execute(self, param: Any, job_id: str, req: Request, report_result=True) -> asyncio.Queue[Union[T, ExecutionError]]:
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
        event_loop = asyncio.get_running_loop()
        self.job_cache[job_id] = None

        def _process_result(result):
            """Verify the result, add it to the queue, and report it to IVCAP."""
            try:
                result = verify_result(result, job_id, logger)
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
                if report_result:
                    push_result(result, job_id)
                self.__class__._active_jobs.discard(job_id)

        def _run(param: Any, ctxt: Context):
            context.attach(ctxt) # OTEL
            authorization = req.headers.get("authorization")
            jctxt = JobContext(
                job_id=job_id,
                job_authorization = authorization,
                report = create_event_reporter(job_id=job_id, job_authorization=authorization),
            )
            job_context.set(jctxt)
            kwargs = {}
            if self.context_param is not None:
                kwargs[self.context_param] = self.context
            if self.request_param is not None:
                kwargs[self.request_param] = req
            if self.job_ctxt_param is not None:
                kwargs[self.job_ctxt_param] = jctxt # self._job_ctxt

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
                        try:
                            res = loop.run_until_complete(self.func(param, **kwargs))
                        except (asyncio.CancelledError, GeneratorExit):
                            # Propagate cancellation and generator shutdown properly
                            raise
                        finally:
                            # Gracefully shutdown remaining tasks and async generators to avoid
                            # 'Task exception was never retrieved' and similar warnings
                            try:
                                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                                for t in pending:
                                    t.cancel()
                                if pending:
                                    with contextlib.suppress(Exception):
                                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                                with contextlib.suppress(Exception):
                                    loop.run_until_complete(loop.shutdown_asyncgens())
                            finally:
                                loop.close()
                    else:
                        res = self.func(param, **kwargs)
                except (asyncio.CancelledError, GeneratorExit):
                    # Allow cooperative shutdown/cancellation to propagate cleanly
                    span.record_exception(Exception("cancelled"))
                    raise
                except Exception as ex:
                    span.record_exception(ex)
                    logger.error(f"while executing {job_id} - {type(ex).__name__}: {ex}")
                    res = ExecutionError(
                        error=str(ex),
                        type=type(ex).__name__,
                        traceback=traceback.format_exc()
                    )
                finally:
                    self.__class__._active_jobs.discard(job_id)

                try:
                    _process_result(res)
                except Exception as ex:
                    logger.error(f"while delivering result fo {job_id} - {ex}")

                job_context.set(JobContext())



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
