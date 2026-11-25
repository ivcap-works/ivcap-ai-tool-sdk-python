#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for the `on_startup` hook of start_lambda_server.

These cover: the hook gating `/_healtz` while it runs, success, sync and async
failures being captured and reported in the 503 body, and the server staying up.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ivcap_service import Service, ServiceContact

from ivcap_lambda import health_handler as health_module
from ivcap_lambda import server as server_module


@pytest.fixture
def harness(monkeypatch):
    saved_tools = list(server_module.tools)
    server_module.tools[:] = [SimpleNamespace(name="t")]
    saved_gates = list(health_module._ready_handlers)
    health_module._ready_handlers.clear()
    health_module._health_info.clear()
    monkeypatch.setattr(server_module, "get_fast_app", FastAPI)
    for name in (
        "otel_instrument",
        "init_openobserve_from_env",
        "set_event_reporter_factory",
        "set_context",
    ):
        monkeypatch.setattr(server_module, name, Mock())
    config = Mock()
    monkeypatch.setattr(server_module.uvicorn, "Config", config)
    monkeypatch.setattr(server_module, "_bind_listen_socket", Mock())
    monkeypatch.setattr(server_module.uvicorn.Server, "run", Mock())
    yield config
    server_module.tools[:] = saved_tools
    health_module._ready_handlers.clear()
    health_module._ready_handlers.extend(saved_gates)


def _start(hook):
    svc = Service(
        name="S", version="1.0.0", contact=ServiceContact(name="T", email="t@e.com")
    )
    server_module.start_lambda_server(
        svc, custom_args=lambda p: p.parse_args([]), on_startup=hook
    )


def _wait_for(client, status_code, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.get("/_healtz").status_code == status_code:
            return True
        time.sleep(0.01)
    return False


def _wait_for_failed(client, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get("/_healtz").json()
        if body.get("startup", {}).get("status") == "failed":
            return True
        time.sleep(0.01)
    return False


def test_successful_sync_hook_makes_service_ready(harness):
    ran = []

    def hook():
        ran.append(1)

    _start(hook)
    app = harness.call_args[0][0]
    with TestClient(app) as c:
        assert _wait_for(c, 200)
    assert ran == [1]


def test_healtz_503_while_sync_hook_runs(harness):
    gate = threading.Event()

    def hook():
        gate.wait(5)

    _start(hook)
    app = harness.call_args[0][0]
    with TestClient(app) as c:
        body = c.get("/_healtz")
        assert body.status_code == 503
        assert body.json()["startup"] == {"status": "loading"}
        gate.set()
        assert _wait_for(c, 200)


def test_sync_hook_exception_is_reported_in_healtz(harness):
    def hook():
        raise RuntimeError("model file missing")

    _start(hook)
    app = harness.call_args[0][0]
    with TestClient(app) as c:
        assert _wait_for_failed(c)
        resp = c.get("/_healtz")
        assert resp.status_code == 503
        startup = resp.json()["startup"]
        assert startup["status"] == "failed"
        assert startup["error"] == "RuntimeError: model file missing"


def test_async_hook_exception_is_reported_in_healtz(harness):
    async def hook():
        raise ValueError("bad weights")

    _start(hook)
    app = harness.call_args[0][0]
    with TestClient(app) as c:
        time.sleep(0.2)
        resp = c.get("/_healtz")
        assert resp.status_code == 503
        assert resp.json()["startup"] == {
            "status": "failed",
            "error": "ValueError: bad weights",
        }


def test_failed_hook_is_logged_with_traceback(harness, caplog):
    def hook():
        raise KeyError("missing")

    _start(hook)
    app = harness.call_args[0][0]
    with TestClient(app) as c:
        time.sleep(0.2)
        c.get("/_healtz")
    assert any(r.exc_info and r.exc_info[0] is KeyError for r in caplog.records), (
        "expected the full traceback to be logged"
    )


def test_failed_hook_does_not_stop_server_responding(harness):
    def hook():
        raise RuntimeError("boom")

    _start(hook)
    app = harness.call_args[0][0]
    with TestClient(app) as c:
        time.sleep(0.2)
        # still answering HTTP (not a crash): a 503 with the failure, not a connection error
        assert c.get("/_healtz").status_code == 503


def test_no_hook_means_ready_without_startup_status(harness):
    _start(None)
    app = harness.call_args[0][0]
    with TestClient(app) as c:
        resp = c.get("/_healtz")
        assert resp.status_code == 200
        assert "startup" not in resp.json()
