#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for ivcap_lambda.executor, focusing on error paths and the
less commonly exercised branches: unexpected parameter types, sync and
async worker-function exceptions, request/context param injection, a
dedicated thread pool (max_workers), job_cache lookups, and the
module-level accessor helpers.
"""

import asyncio
import time

import pytest
from fastapi import Request
from ivcap_service import ExecutionError, with_schema
from pydantic import BaseModel, Field

from ivcap_lambda.executor import (
    ExecutionContext,
    Executor,
    ExecutorOpts,
    get_event_reporter,
    get_job_context,
    get_job_id,
)


@with_schema("urn:sd:schema:executor-test.request.1")
class _Data(BaseModel):
    value: int = Field(..., description="input value")


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


async def _run_and_get(executor: Executor, param, job_id="job-1", req=None):
    req = req or _FakeRequest()
    queue = await executor.execute(param, job_id, req, report_result=False)
    return await asyncio.wait_for(queue.get(), timeout=5)


def test_constructor_rejects_unexpected_parameter_type():
    def bad_fn(data: _Data, something_unexpected: int) -> _Data:
        return data

    with pytest.raises(Exception, match="unexpected function parameter"):
        Executor(bad_fn, opts=None)


def test_execute_sync_function_success():
    def fn(data: _Data) -> _Data:
        return _Data(value=data.value * 2)

    executor = Executor(fn, opts=None)

    result = asyncio.run(_run_and_get(executor, _Data(value=21)))
    assert not isinstance(result, ExecutionError)
    assert result.raw.value == 42


def test_execute_sync_function_raises_value_error_returns_execution_error():
    def fn(data: _Data) -> _Data:
        raise ValueError("bad data")

    executor = Executor(fn, opts=None)

    result = asyncio.run(_run_and_get(executor, _Data(value=1)))
    assert isinstance(result, ExecutionError)
    assert result.type == "ValueError"
    assert "bad data" in result.error
    assert result.traceback is not None


def test_execute_async_function_success():
    async def fn(data: _Data) -> _Data:
        await asyncio.sleep(0)
        return _Data(value=data.value + 1)

    executor = Executor(fn, opts=None)

    result = asyncio.run(_run_and_get(executor, _Data(value=1)))
    assert not isinstance(result, ExecutionError)
    assert result.raw.value == 2


def test_execute_async_function_raises_returns_execution_error():
    async def fn(data: _Data) -> _Data:
        await asyncio.sleep(0)
        raise RuntimeError("async boom")

    executor = Executor(fn, opts=None)

    result = asyncio.run(_run_and_get(executor, _Data(value=1)))
    assert isinstance(result, ExecutionError)
    assert result.type == "RuntimeError"
    assert "async boom" in result.error


def test_execute_injects_request_param():
    captured = {}

    def fn(data: _Data, req: Request) -> _Data:
        captured["headers"] = dict(req.headers)
        return data

    executor = Executor(fn, opts=None)
    req = _FakeRequest(headers={"authorization": "Bearer xyz"})

    asyncio.run(_run_and_get(executor, _Data(value=1), req=req))
    assert captured["headers"]["authorization"] == "Bearer xyz"


def test_execute_injects_context_param():
    class MyContext(ExecutionContext):
        pass

    ctxt = MyContext()
    captured = {}

    def fn(data: _Data, ctx: MyContext) -> _Data:
        captured["ctx"] = ctx
        return data

    executor = Executor(fn, opts=None, context=ctxt)
    asyncio.run(_run_and_get(executor, _Data(value=1)))
    assert captured["ctx"] is ctxt


def test_execute_with_dedicated_thread_pool():
    def fn(data: _Data) -> _Data:
        return data

    executor = Executor(fn, opts=ExecutorOpts(max_workers=2))
    assert executor.thread_pool is not None

    result = asyncio.run(_run_and_get(executor, _Data(value=7)))
    assert not isinstance(result, ExecutionError)


def test_lookup_job_in_progress_returns_none():
    def fn(data: _Data) -> _Data:
        time.sleep(0.2)
        return data

    executor = Executor(fn, opts=None)

    async def start():
        return await executor.execute(
            _Data(value=1), "job-x", _FakeRequest(), report_result=False
        )

    asyncio.run(start())
    # Immediately after scheduling, the job cache entry is set to None
    assert executor.lookup_job("job-x") is None


def test_lookup_job_unknown_raises_keyerror():
    def fn(data: _Data) -> _Data:
        return data

    executor = Executor(fn, opts=None)
    with pytest.raises(KeyError):
        executor.lookup_job("never-existed")


def test_wait_for_exit_ready_returns_immediately_when_no_active_jobs():
    # Ensure clean state then call; should return without blocking since
    # there shouldn't be any lingering active jobs from a clean test run.
    Executor._active_jobs.clear()
    Executor.wait_for_exit_ready()  # should not hang


def test_active_jobs_lists_running_job_ids():
    Executor._active_jobs.clear()

    def fn(data: _Data) -> _Data:
        time.sleep(0.2)
        return data

    executor = Executor(fn, opts=None)

    async def start():
        return await executor.execute(
            _Data(value=1), "job-active", _FakeRequest(), report_result=False
        )

    asyncio.run(start())
    # Give the background thread a moment to register itself as active.
    time.sleep(0.05)
    assert "job-active" in Executor.active_jobs()
    # Wait for it to finish so we don't leak state into other tests.
    for _ in range(50):
        if "job-active" not in Executor.active_jobs():
            break
        time.sleep(0.05)


def test_get_job_context_event_reporter_and_job_id_default_to_none():
    # Outside of any job execution context (e.g. the main test thread),
    # there should be no job context set.
    assert get_job_context() is None
    assert get_event_reporter() is None
    assert get_job_id() is None
