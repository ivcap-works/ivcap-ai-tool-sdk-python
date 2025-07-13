#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import json
import os
import logging
from ivcap_service import set_service_log_config

class SuppressPathsFilter(logging.Filter):
    def __init__(self, targets=None):
        super().__init__()
        if targets is None:
            self.targets = []
        else:
            self.targets = targets

    def filter(self, record):
        # Suppress logs for any request matching a target substring or path
        # For uvicorn.access, HTTP info is in record.args: (client_addr, method, path, http_version, status)
        path = ""
        if hasattr(record, "args") and isinstance(record.args, tuple) and len(record.args) >= 3:
            path = record.args[2]
        for target in self.targets:
            if target == path:
                return False
        return True

def logging_init(cfg_path: str=None):
    if not cfg_path:
        script_dir = os.path.dirname(__file__)
        cfg_path = os.path.join(script_dir, "logging.json")

    with open(cfg_path, 'r') as file:
        config = json.load(file)
        set_service_log_config(config)
