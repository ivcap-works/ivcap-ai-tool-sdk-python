#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""A library supporting the development of tools for agents to be deployed on  IVCAP"""

from .version import __version__

from .server import start_lambda_server
from .server import start_tool_server  # backward-compat alias (deprecated)
from .builder import add_tool_api_route, ToolOptions
from .executor import ExecutionContext, get_event_reporter, get_job_id
from .utils import get_public_url_prefix
from .secret import SecretMgrClient
from .decorators import ivcap_lambda
from .logger import logging_init


def ivcap_ai_tool(*args, **kwargs):
    """Deprecated alias for :func:`ivcap_lambda`.

    .. deprecated::
        Use :func:`ivcap_lambda` instead.
    """
    import warnings

    warnings.warn(
        "ivcap_ai_tool() is deprecated; use ivcap_lambda() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return ivcap_lambda(*args, **kwargs)
