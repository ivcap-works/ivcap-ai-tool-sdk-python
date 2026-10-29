#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for the `/_healtz` readiness endpoint in ivcap_lambda.health_handler.

These tests cover:
 - the endpoint returning 200 when no readiness handlers are registered
 - 200 when all registered readiness handlers report ready
 - 503 when any sync or async readiness handler reports not-ready
 - `add_health_route` not overriding an existing `/_healtz` route
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ivcap_lambda import health_handler as health_module
from ivcap_lambda.health_handler import NotReadyYet, add_health_route, add_ready_handler


@pytest.fixture(autouse=True)
def _clean_ready_handlers():
    """`_ready_handlers` is a module-level list; isolate tests."""
    saved = list(health_module._ready_handlers)
    health_module._ready_handlers.clear()
    yield
    health_module._ready_handlers.clear()
    health_module._ready_handlers.extend(saved)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VERSION", "1.2.3")
    app = FastAPI()
    add_health_route(app)
    return TestClient(app)


def test_healtz_ok_without_handlers(client):
    resp = client.get("/_healtz")
    assert resp.status_code == 200
    assert resp.json() == {"version": "1.2.3"}


def test_healtz_ok_when_all_handlers_ready(client):
    add_ready_handler(lambda: True)
    add_ready_handler(lambda: True)
    assert client.get("/_healtz").status_code == 200


def test_healtz_503_when_sync_handler_not_ready(client):
    add_ready_handler(lambda: False)
    assert client.get("/_healtz").status_code == 503


def test_healtz_503_when_async_handler_not_ready(client):
    async def not_ready() -> bool:
        return False

    add_ready_handler(not_ready)
    assert client.get("/_healtz").status_code == 503


def test_healtz_503_if_any_handler_not_ready(client):
    add_ready_handler(lambda: True)
    add_ready_handler(lambda: False)
    assert client.get("/_healtz").status_code == 503


def test_add_none_handler_is_ignored(client):
    add_ready_handler(None)
    assert health_module._ready_handlers == []
    assert client.get("/_healtz").status_code == 200


def test_add_health_route_keeps_existing_route():
    app = FastAPI()

    @app.get("/_healtz")
    def custom():
        return {"custom": True}

    add_ready_handler(lambda: False)
    add_health_route(app)
    assert TestClient(app).get("/_healtz").json() == {"custom": True}


def test_dict_result_is_merged_into_reply(client):
    add_ready_handler(lambda: {"model": "resnet-50", "config": "v2"})
    resp = client.get("/_healtz")
    assert resp.status_code == 200
    assert resp.json() == {"model": "resnet-50", "config": "v2", "version": "1.2.3"}


def test_empty_dict_is_ready(client):
    add_ready_handler(lambda: {})
    resp = client.get("/_healtz")
    assert resp.status_code == 200
    assert resp.json() == {"version": "1.2.3"}


def test_dict_info_merges_across_handlers(client):
    add_ready_handler(lambda: {"model": "m1"})
    add_ready_handler(lambda: {"dataset": "d1"})
    assert client.get("/_healtz").json() == {
        "model": "m1",
        "dataset": "d1",
        "version": "1.2.3",
    }


def test_version_key_in_dict_does_not_override_version(client):
    add_ready_handler(lambda: {"version": "spoofed", "model": "m1"})
    assert client.get("/_healtz").json() == {"version": "1.2.3", "model": "m1"}


def test_async_dict_result_is_merged(client):
    async def info() -> dict:
        return {"model": "async-model"}

    add_ready_handler(info)
    assert client.get("/_healtz").json() == {
        "model": "async-model",
        "version": "1.2.3",
    }


def test_not_ready_yet_returns_503_without_retry_header(client):
    def not_yet() -> bool:
        raise NotReadyYet()

    add_ready_handler(not_yet)
    resp = client.get("/_healtz")
    assert resp.status_code == 503
    assert "Retry-After" not in resp.headers


def test_not_ready_yet_sets_retry_after_rounded_up(client):
    def loading() -> bool:
        raise NotReadyYet(retry_after=2.2)

    add_ready_handler(loading)
    resp = client.get("/_healtz")
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "3"


def test_async_not_ready_yet_sets_retry_after(client):
    async def loading() -> bool:
        raise NotReadyYet(retry_after=10)

    add_ready_handler(loading)
    resp = client.get("/_healtz")
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "10"


def test_largest_retry_after_wins_across_handlers(client):
    def short() -> bool:
        raise NotReadyYet(retry_after=5)

    def long() -> bool:
        raise NotReadyYet(retry_after=30)

    add_ready_handler(short)
    add_ready_handler(long)
    assert client.get("/_healtz").headers["Retry-After"] == "30"


def test_other_handlers_still_contribute_info_when_not_ready(client):
    def loading() -> bool:
        raise NotReadyYet(retry_after=1)

    add_ready_handler(lambda: {"model": "m1"})
    add_ready_handler(loading)
    resp = client.get("/_healtz")
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "1"


def test_not_ready_yet_takes_precedence_over_ready_dict(client):
    add_ready_handler(lambda: {"model": "m1"})
    add_ready_handler(lambda: False)
    assert client.get("/_healtz").status_code == 503
