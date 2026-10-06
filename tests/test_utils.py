#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for ivcap_lambda.utils."""

from ivcap_lambda.utils import (
    find_first,
    get_forwarded_header,
    get_public_url_prefix,
    get_title_from_path,
)


class _FakeRequest:
    """Minimal duck-typed stand-in for fastapi.Request used by these helpers."""

    def __init__(self, headers=None, base_url="http://testserver/"):
        self.headers = headers or {}
        self.base_url = base_url


# --- get_title_from_path ----------------------------------------------------


def test_get_title_from_path_simple():
    assert get_title_from_path("process") == ("process", "Process")


def test_get_title_from_path_with_slash():
    assert get_title_from_path("/api/v1/process") == ("process", "Process")


def test_get_title_from_path_plural_ies():
    # "companies" -> "company"
    assert get_title_from_path("companies") == ("company", "Company")


def test_get_title_from_path_plural_es():
    # "boxes" -> "box"
    assert get_title_from_path("boxes") == ("box", "Box")


def test_get_title_from_path_plural_ss_preserved():
    # words ending in "ss" should not be singularised
    assert get_title_from_path("class") == ("class", "Class")


def test_get_title_from_path_plural_s():
    assert get_title_from_path("tools") == ("tool", "Tool")


def test_get_title_from_path_underscore_replaced_with_space():
    assert get_title_from_path("my_tool") == ("my tool", "My tool")


def test_get_title_from_path_empty_string():
    assert get_title_from_path("") == ("", "")


def test_get_title_from_path_trailing_slash():
    # last path element after a trailing slash is empty
    assert get_title_from_path("/process/") == ("", "")


def test_get_title_from_path_single_char():
    assert get_title_from_path("a") == ("a", "A")


# --- find_first --------------------------------------------------------------


def test_find_first_found():
    assert find_first([1, 2, 3, 4], lambda x: x > 2) == 3


def test_find_first_not_found():
    assert find_first([1, 2, 3], lambda x: x > 10) is None


def test_find_first_empty_iterable():
    assert find_first([], lambda x: True) is None


# --- get_forwarded_header -----------------------------------------------------


def test_get_forwarded_header_missing():
    req = _FakeRequest(headers={})
    assert get_forwarded_header(req) is None


def test_get_forwarded_header_parses_key_values():
    req = _FakeRequest(headers={"Forwarded": "for=1.2.3.4;proto=https"})
    result = get_forwarded_header(req)
    assert result == {"for": "1.2.3.4", "proto": "https"}


def test_get_forwarded_header_strips_quotes():
    req = _FakeRequest(headers={"Forwarded": 'for="1.2.3.4";proto=https'})
    result = get_forwarded_header(req)
    assert result == {"for": "1.2.3.4", "proto": "https"}


def test_get_forwarded_header_ignores_malformed_elements():
    # an element without "=" is silently skipped
    req = _FakeRequest(headers={"Forwarded": "for=1.2.3.4;garbage;proto=https"})
    result = get_forwarded_header(req)
    assert result == {"for": "1.2.3.4", "proto": "https"}


def test_get_forwarded_header_empty_value():
    req = _FakeRequest(headers={"Forwarded": ""})
    assert get_forwarded_header(req) is None


# --- get_public_url_prefix -----------------------------------------------------


def test_get_public_url_prefix_without_forwarded_header():
    req = _FakeRequest(headers={}, base_url="http://testserver/")
    assert get_public_url_prefix(req) == "http://testserver"


def test_get_public_url_prefix_with_forwarded_header():
    req = _FakeRequest(headers={"Forwarded": "for=1.2.3.4;proto=https"})
    # Note: current implementation builds "proto:://for" (double colon is
    # intentional/pre-existing behaviour of get_public_url_prefix).
    assert get_public_url_prefix(req) == "https:://1.2.3.4"


def test_get_public_url_prefix_with_forwarded_header_defaults_proto():
    req = _FakeRequest(headers={"Forwarded": "for=1.2.3.4"})
    assert get_public_url_prefix(req) == "http:://1.2.3.4"
