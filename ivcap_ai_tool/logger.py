#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import json
import os
from ivcap_service import set_service_log_config

def logging_init(cfg_path: str=None):
    if not cfg_path:
        script_dir = os.path.dirname(__file__)
        cfg_path = os.path.join(script_dir, "logging.json")

    with open(cfg_path, 'r') as file:
        config = json.load(file)
        set_service_log_config(config)