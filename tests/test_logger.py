#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for ivcap_lambda.logger."""

import json
import logging

from ivcap_lambda.logger import SuppressPathsFilter, logging_init

# --- SuppressPathsFilter -------------------------------------------------


def _make_record(args=None):
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/1.1" %s',
        args=args,
        exc_info=None,
    )
    return record


def test_suppress_paths_filter_defaults_to_empty_targets():
    f = SuppressPathsFilter()
    assert f.targets == []
    # With no targets, everything passes through
    record = _make_record(args=("127.0.0.1", "GET", "/_healtz", "200"))
    assert f.filter(record) is True


def test_suppress_paths_filter_suppresses_matching_path():
    f = SuppressPathsFilter(targets=["/_healtz"])
    record = _make_record(args=("127.0.0.1", "GET", "/_healtz", "200"))
    assert f.filter(record) is False


def test_suppress_paths_filter_allows_non_matching_path():
    f = SuppressPathsFilter(targets=["/_healtz"])
    record = _make_record(args=("127.0.0.1", "GET", "/other", "200"))
    assert f.filter(record) is True


def test_suppress_paths_filter_no_args():
    f = SuppressPathsFilter(targets=["/_healtz"])
    record = _make_record(args=None)
    # record.args is None -> "hasattr(record, 'args') and isinstance(...)" is False
    assert f.filter(record) is True


def test_suppress_paths_filter_short_args_tuple():
    f = SuppressPathsFilter(targets=["/_healtz"])
    record = _make_record(args=("only-one",))
    assert f.filter(record) is True


# --- logging_init ---------------------------------------------------------


def test_logging_init_with_default_config_path():
    # Uses ivcap_lambda/logging.json bundled with the package; should not raise
    logging_init()
    logger = logging.getLogger("app")
    assert logger.level == logging.DEBUG


def test_logging_init_with_custom_config_path(tmp_path):
    cfg = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": {"format": "%(message)s"}},
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": "DEBUG",
            }
        },
        "root": {"level": "WARNING", "handlers": ["default"]},
    }
    cfg_path = tmp_path / "custom_logging.json"
    cfg_path.write_text(json.dumps(cfg))

    logging_init(str(cfg_path))

    assert logging.getLogger().level == logging.WARNING
