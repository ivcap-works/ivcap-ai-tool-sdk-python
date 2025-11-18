#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#

"""
DEPRECATED: ivcap_ai_tool.secret.SecretMgrClient

The SecretMgrClient has moved to ivcap_service.secret.SecretMgrClient.
This module keeps a backwards-compatible shim so existing imports like

    from ivcap_ai_tool.secret import SecretMgrClient

continue to work. Please migrate to:

    from ivcap_service.secret import SecretMgrClient

This shim will be removed in a future release.
"""

from __future__ import annotations

import warnings

__all__ = ["SecretMgrClient"]

from ivcap_service.secret import SecretMgrClient as _SecretMgrClient  # type: ignore

class SecretMgrClient(_SecretMgrClient):
    """Backward-compatibility shim for SecretMgrClient.

    Deprecated: Use ivcap_service.secret.SecretMgrClient instead.
    """

    def __init__(self, *args, **kwargs):
        warnings.warn(
            "ivcap_ai_tool.secret.SecretMgrClient is deprecated; use "
            "ivcap_service.secret.SecretMgrClient",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)
