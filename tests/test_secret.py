#
# Copyright (c) 2025 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import warnings

def test_local_secret_client_deprecation():
    """Importing and instantiating the local SecretMgrClient should succeed
    but emit a DeprecationWarning. We don't call get_secret to avoid any
    network access; the warning is triggered in __init__.
    """
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", DeprecationWarning)
        from ivcap_ai_tool.secret import SecretMgrClient

        # Instantiate with a harmless URL to avoid accidental calls later
        client = SecretMgrClient(secret_url="http://example.com")
        assert client is not None
        assert any(
            issubclass(wi.category, DeprecationWarning)
            and "deprecated" in str(wi.message).lower()
            for wi in w
        ), "Expected a DeprecationWarning when using local SecretMgrClient"
