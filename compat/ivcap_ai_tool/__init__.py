#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""
DEPRECATED compatibility shim: ivcap_ai_tool → ivcap_lambda

This package re-exports the entire public API of ivcap_lambda under the old
ivcap_ai_tool namespace so that existing code continues to work. Please migrate
to ivcap_lambda as this shim will be removed in a future release.
"""

import warnings

warnings.warn(
    "The 'ivcap_ai_tool' package has been renamed to 'ivcap_lambda'. "
    "Please update your dependency and imports: "
    "'pip install ivcap-lambda' and 'from ivcap_lambda import ...'",
    DeprecationWarning,
    stacklevel=2,
)

from ivcap_lambda import (  # noqa: F401, E402
    ExecutionContext,
    SecretMgrClient,
    ToolOptions,
    __version__,
    add_tool_api_route,
    get_event_reporter,
    get_job_id,
    get_public_url_prefix,
    logging_init,
    start_lambda_server,
)

# Expose start_tool_server as a backward-compat alias without triggering a
# second DeprecationWarning from the ivcap_lambda.start_tool_server wrapper.
start_tool_server = start_lambda_server  # noqa: F401

# The decorator was called ivcap_ai_tool in the old package.
# Import ivcap_lambda directly and alias it — the compat package's own
# DeprecationWarning (above) already covers users of this shim; we don't
# want a second warning from ivcap_lambda.ivcap_ai_tool().
from ivcap_lambda import ivcap_lambda  # noqa: F401, E402

ivcap_ai_tool = ivcap_lambda  # noqa: F401
