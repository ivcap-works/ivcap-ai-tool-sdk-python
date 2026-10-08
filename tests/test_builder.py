#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for the request/response building logic in ivcap_lambda.builder.

These tests exercise `add_tool_api_route` end-to-end via FastAPI's
TestClient, covering:
 - tool-definition (GET {path}) endpoint
 - successful job execution (POST {path})
 - try-later / async semantics (204 + Location/Retry-Later headers)
 - job polling (GET {path}/jobs/{job_id}) including success, in-progress,
   error, and unknown-job paths
 - ValueError vs. generic Exception error-model mapping
"""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ivcap_service import JobContext, with_schema
from pydantic import BaseModel, Field

from ivcap_lambda import builder as builder_module
from ivcap_lambda.builder import ToolOptions, add_tool_api_route


@with_schema("urn:sd:schema:builder-test.request.1")
class _Req(BaseModel):
    text: str = Field(..., description="text to process")


@with_schema("urn:sd:schema:builder-test.1")
class _Res(BaseModel):
    output: str = Field(..., description="the result")


@pytest.fixture(autouse=True)
def _clean_tool_registry():
    """`ivcap_lambda.builder.tools` is a module-level list; isolate tests."""
    saved = list(builder_module.tools)
    builder_module.tools.clear()
    yield
    builder_module.tools.clear()
    builder_module.tools.extend(saved)


def _new_app():
    return FastAPI()


def test_get_tool_definition_route():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Process text

        Uppercases the input text.
        """
        return _Res(output=req.text.upper())

    add_tool_api_route(app, "/process", process, opts=ToolOptions(service_id="svc-1"))

    client = TestClient(app)
    resp = client.get("/process")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "process"
    # ToolDefinition serialises this field under the "service-id" alias
    assert data["service-id"] == "svc-1"
    assert "fn_schema" in data


def test_post_job_returns_result_synchronously():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Process text"""
        return _Res(output=req.text.upper())

    add_tool_api_route(app, "/process", process, opts=ToolOptions())

    client = TestClient(app)
    resp = client.post("/process", json={"text": "hi"})
    assert resp.status_code == 200
    assert resp.json()["output"] == "HI"
    assert "job-id" in resp.headers


def test_post_job_with_job_context_param():
    app = _new_app()

    def process(req: _Req, jobCtxt: JobContext) -> _Res:
        """Process text with context"""
        assert jobCtxt.job_id is not None
        return _Res(output=req.text.upper())

    add_tool_api_route(app, "/process", process, opts=ToolOptions())

    client = TestClient(app)
    resp = client.post("/process", json={"text": "hi"})
    assert resp.status_code == 200
    assert resp.json()["output"] == "HI"


def test_post_job_honours_incoming_job_id_header():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Process text"""
        return _Res(output=req.text.upper())

    add_tool_api_route(app, "/process", process, opts=ToolOptions())

    client = TestClient(app)
    resp = client.post(
        "/process", json={"text": "hi"}, headers={"job-id": "urn:ivcap:job:abc123"}
    )
    assert resp.status_code == 200
    assert resp.headers["job-id"] == "urn:ivcap:job:abc123"


def test_post_job_value_error_returns_400():
    """`_return_job_result` maps a `ValueError` raised in a tool function to
    a 400 Bad Request with an `ErrorModel` body (no traceback leaked), by
    comparing `el.type` - the string class name (e.g. "ValueError")
    produced by `Executor` - against `ValueError.__name__`.
    """
    app = _new_app()

    def fail(req: _Req) -> _Res:
        """Always fails"""
        raise ValueError(f"bad input: {req.text}")

    add_tool_api_route(app, "/fail", fail, opts=ToolOptions())

    client = TestClient(app)
    resp = client.post("/fail", json={"text": "hi"})
    assert resp.status_code == 400
    body = resp.json()
    assert "bad input: hi" in body["message"]
    assert "traceback" not in body


def test_post_job_generic_exception_returns_500():
    app = _new_app()

    def fail(req: _Req) -> _Res:
        """Always fails"""
        raise RuntimeError("boom")

    add_tool_api_route(app, "/fail", fail, opts=ToolOptions())

    client = TestClient(app)
    resp = client.post("/fail", json={"text": "hi"})
    assert resp.status_code == 500
    body = resp.json()
    assert "boom" in body["message"]
    assert "traceback" in body


def test_post_job_respond_async_defers_and_get_job_polls_result():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Process text"""
        return _Res(output=req.text.upper())

    add_tool_api_route(app, "/process", process, opts=ToolOptions())

    client = TestClient(app)
    resp = client.post(
        "/process", json={"text": "hi"}, headers={"Prefer": "respond-async"}
    )
    assert resp.status_code == 204
    location = resp.headers["location"]
    assert location.startswith("/process/jobs/")
    assert "retry-later" in resp.headers

    job_id = location.rsplit("/", 1)[-1]

    # Poll until the background thread has produced a result.
    for _ in range(50):
        poll = client.get(f"/process/jobs/{job_id}")
        if poll.status_code != 204:
            break
        time.sleep(0.05)
    assert poll.status_code == 200
    assert poll.json()["output"] == "HI"


def test_get_job_unknown_job_returns_404():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Process text"""
        return _Res(output=req.text.upper())

    add_tool_api_route(app, "/process", process, opts=ToolOptions())

    client = TestClient(app)
    resp = client.get("/process/jobs/does-not-exist")
    assert resp.status_code == 404


def test_get_job_strips_job_urn_prefix():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Process text"""
        return _Res(output=req.text.upper())

    add_tool_api_route(app, "/process", process, opts=ToolOptions())

    client = TestClient(app)
    resp = client.get("/process/jobs/urn:ivcap:job:does-not-exist")
    assert resp.status_code == 404


def test_post_job_timeout_triggers_try_later():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Slow process"""
        time.sleep(0.3)
        return _Res(output=req.text.upper())

    add_tool_api_route(app, "/process", process, opts=ToolOptions(max_wait_time=0.01))

    client = TestClient(app)
    resp = client.post("/process", json={"text": "hi"})
    assert resp.status_code == 204
    assert "location" in resp.headers
    assert "retry-later" in resp.headers


def test_default_tags_and_name_derived_from_path_prefix():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Process text"""
        return _Res(output=req.text.upper())

    opts = ToolOptions()
    add_tool_api_route(app, "/process", process, opts=opts)

    assert opts.tags == ["Process"]
    assert opts.name == "process"


def test_default_tags_fallback_when_path_prefix_is_root():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Process text"""
        return _Res(output=req.text.upper())

    opts = ToolOptions()
    add_tool_api_route(app, "/", process, opts=opts)

    assert opts.tags == ["Tool"]
    assert opts.name == "Execute the tool"


def test_add_tool_api_route_with_none_opts_uses_defaults():
    app = _new_app()

    def process(req: _Req) -> _Res:
        """Process text"""
        return _Res(output=req.text.upper())

    add_tool_api_route(app, "/process", process, opts=None)

    client = TestClient(app)
    resp = client.post("/process", json={"text": "hi"})
    assert resp.status_code == 200
    assert resp.json()["output"] == "HI"
