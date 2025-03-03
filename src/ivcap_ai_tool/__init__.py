#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
""" A client library for accessing IVCAP """

# read version from installed package
try:  # Python < 3.10 (backport)
    from importlib_metadata import version
except ImportError:
    from importlib.metadata import version
try:
    __version__ = version("ivcap_client")
except Exception:
    __version__ = "unknown" # should only happen when running the local examples

from .tool_definition import ToolDefinition, print_tool_definition, create_tool_definition
from .server import start_tool_server

from .builder import add_tool_api_route, ToolOptions
from .executor import ExecutionContext