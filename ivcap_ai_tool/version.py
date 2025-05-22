#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#

__version__ = "???"
try:  # Python > 3.8+
    from importlib_metadata import version
    __version__ = version("ivcap_ai_tool")
except ImportError:
    try:
        import pkg_resources
        __version__ = pkg_resources.get_distribution('ivcap_ai_tool').version
    except Exception:
        pass

def get_version():
    return __version__