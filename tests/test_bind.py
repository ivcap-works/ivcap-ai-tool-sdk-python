#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for binding the HTTP port before the service starts."""

import socket
from unittest.mock import Mock

import pytest

from ivcap_lambda import server as server_module


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_bind_returns_listening_socket_on_free_port():
    port = _free_port()
    sock = server_module._bind_listen_socket("127.0.0.1", port, Mock())
    try:
        assert sock.getsockname()[1] == port
    finally:
        sock.close()


def test_bind_conflict_logs_fatal_and_exits_1():
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    logger = Mock()
    try:
        with pytest.raises(SystemExit) as ex:
            server_module._bind_listen_socket("127.0.0.1", port, logger)
    finally:
        holder.close()
    assert ex.value.code == 1
    messages = [c.args[0] for c in logger.error.call_args_list]
    assert any(f"FATAL - Could not bind to port {port}" in m for m in messages)
    assert any(f"lsof -i :{port}" in m for m in messages)
    assert any("Exiting with error code 1" in m for m in messages)
