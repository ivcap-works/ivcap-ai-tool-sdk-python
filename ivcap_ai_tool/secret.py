#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#


"""
This is a file for the IVCAP Secret Manager Client

It suppose to read secret through http via:
- Service side car
"""

import requests

class SecretMgrClient:
    def __init__(self,
        secret_url: str = "http://secretmgr.local"
    ) -> None:
        self.secret_url = secret_url

    def get_secret(self, secret_name: str, is_shared_secret: bool = False, secret_type: str = "", timeout: int = 10) -> str:
        try:
            url = f"{self.secret_url}/1/secret"

            secret_name = secret_name.strip()
            if not secret_name:
                raise ValueError("empty secret name")

            secret_type = secret_type.strip()
            if not secret_type:
                secret_type = "raw"

            token_type = "USER"
            if is_shared_secret:
                token_type = "M2M"

            params = {
                "secret-name": secret_name,
                "secret-type": secret_type,
                "token-type":  token_type,
            }

            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()

            if not response.content:
                raise Exception("Failed to read secret: empty response received.")

            data = response.json()
            return data["secret-value"]
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to read secret: {e}")