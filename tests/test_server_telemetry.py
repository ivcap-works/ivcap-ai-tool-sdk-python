#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for OpenTelemetry initialization during lambda server startup."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from ivcap_service import Service, ServiceContact

from ivcap_lambda import server as server_module


@pytest.fixture
def telemetry_startup(monkeypatch):
    saved_tools = list(server_module.tools)
    server_module.tools[:] = [SimpleNamespace(name="test_tool")]

    init_openobserve = Mock()
    instrument = Mock()
    monkeypatch.setattr(server_module, "init_openobserve_from_env", init_openobserve)
    monkeypatch.setattr(server_module, "otel_instrument", instrument)
    monkeypatch.setattr(server_module, "get_fast_app", FastAPI)
    monkeypatch.setattr(server_module, "set_event_reporter_factory", Mock())
    monkeypatch.setattr(server_module, "set_context", Mock())
    monkeypatch.setattr(server_module.uvicorn, "Config", Mock())
    monkeypatch.setattr(server_module.uvicorn.Server, "run", Mock())

    yield init_openobserve, instrument

    server_module.tools[:] = saved_tools


def _start(argv, *, with_telemetry=None, logger=None):
    service = Service(
        name="Telemetry Test",
        version="1.2.3",
        contact=ServiceContact(name="Test", email="test@example.com"),
    )
    server_module.start_lambda_server(
        service,
        logger=logger or logging.getLogger("test.server.telemetry"),
        custom_args=lambda parser: parser.parse_args(argv),
        with_telemetry=with_telemetry,
    )


@pytest.mark.parametrize(
    ("argv", "configured", "expected"),
    [
        ([], None, None),
        (["--with-telemetry"], False, True),
        (["--without-telemetry"], True, False),
    ],
)
def test_initializes_exporters_and_resolves_cli_precedence(
    telemetry_startup, argv, configured, expected
):
    init_openobserve, instrument = telemetry_startup

    _start(argv, with_telemetry=configured)

    init_openobserve.assert_called_once()
    assert init_openobserve.call_args.kwargs["service_name"] == "Telemetry Test"
    assert init_openobserve.call_args.kwargs["service_version"] == "1.2.3"
    assert instrument.call_args.args[0] is expected


def test_exporter_initialization_failure_does_not_stop_server(telemetry_startup):
    init_openobserve, instrument = telemetry_startup
    init_openobserve.side_effect = RuntimeError("invalid telemetry config")
    logger = Mock()

    _start([], logger=logger)

    logger.warning.assert_called_once_with(
        "OpenTelemetry initialization failed: %s", init_openobserve.side_effect
    )
    instrument.assert_called_once()


@pytest.mark.parametrize(
    "thread_name",
    [
        "OtelBatchLogRecordProcessor",
        "OtelBatchSpanRecordProcessor",
        "OtelPeriodicExportingMetricReader",
    ],
)
def test_missing_job_context_does_not_warn_for_otel_threads(
    telemetry_startup, monkeypatch, thread_name
):
    logger = Mock()
    monkeypatch.setattr(
        server_module, "current_thread", lambda: SimpleNamespace(name=thread_name)
    )
    _start([], logger=logger)

    context_provider = server_module.set_context.call_args.args[0]
    assert context_provider() is None
    logger.warning.assert_not_called()


def test_missing_job_context_still_warns_for_other_threads(
    telemetry_startup, monkeypatch
):
    logger = Mock()
    monkeypatch.setattr(
        server_module, "current_thread", lambda: SimpleNamespace(name="worker-1")
    )
    _start([], logger=logger)

    context_provider = server_module.set_context.call_args.args[0]
    assert context_provider() is None
    logger.warning.assert_called_once_with("missing job context in thread")
