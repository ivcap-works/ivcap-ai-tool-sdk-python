#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#

import os
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

try:
    __version__ = _dist_version("ivcap-lambda")
except PackageNotFoundError:
    __version__ = "???"


def resolve_service_version(service_version: str | None) -> str:
    """Return the service version to report.

    Priority: the `VERSION` environment variable, then the version declared on
    the `Service`, then "???". An empty `VERSION` counts as unset.
    """
    return os.environ.get("VERSION") or service_version or "???"


def get_version():
    return __version__
