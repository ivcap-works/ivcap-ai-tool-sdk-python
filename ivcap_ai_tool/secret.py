#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#


"""
This is a file for the IVCAP Secret Manager Client

Handles sync Operations for:
- Read Secret


Requires:
* `env ["NAMESPACE", "CLOUD_PROVIDER", "M2M_AUTH_TOKEN_URL", "M2M_AUTH_AUDIENCE"],
* `env ["AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET"] for minikube/docker-desktop`
* `env ["GCP_PROJECT_ID"]` for gcp project`
* `pip install jwt, logging`
"""

import os, requests
import jwt, logging
from datetime import datetime, timezone

class SecretMgrClient:
    # the class vars for auth0 client_id, secret and token
    auth0_client_id = ""
    auth0_client_secret = ""
    auth0_token = ""
    logger = logging.getLogger("secret")

    def __init__(self):
        self.namespace = os.getenv("NAMESPACE", "ivcap-minikube").strip()
        self.cloud_provider = os.getenv("CLOUD_PROVIDER", "minikube").strip()

    def populate_auth0_client(self):
        # skip if already exists
        if SecretMgrClient.auth0_client_id and SecretMgrClient.auth0_client_secret:
            return

        if(self.cloud_provider != "gke"): # TODO, add support for workbench
            SecretMgrClient.auth0_client_id = os.getenv("AUTH0_CLIENT_ID")
            SecretMgrClient.auth0_client_secret = os.getenv("AUTH0_CLIENT_SECRET")
            if not SecretMgrClient.auth0_client_id or not SecretMgrClient.auth0_client_secret:
                raise ValueError("env AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET required!")
        else:
            SecretMgrClient.auth0_client_id = os.getenv("AUTH0_CLIENT_ID")
            if not SecretMgrClient.auth0_client_id:
                raise ValueError("env AUTH0_CLIENT_ID required!")
            SecretMgrClient.auth0_client_secret = self.get_global_gcp_secret("AUTH0-M2M-CLIENT-SECRET")



    def get_global_gcp_secret(self, secret_id):
        """
            The method to get auth0 client id and auth0 client secret, which are global secrets.
            The auth0 client id and secret are used to generate m2m token to access other secrets
        """

        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        gcp_project_id = os.getenv("GCP_PROJECT_ID")
        if not gcp_project_id:
            raise ValueError("env GCP_PROJECT_ID required!")

        name = f"projects/{gcp_project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(name=name)
        return response.payload.data.decode("UTF-8")


    def get_secret(self, key: str) -> str:
        try:
            # generate client token
            self.renew_auth0_token()

            if not SecretMgrClient.auth0_token:
                SecretMgrClient.logger.error(f"invalid auth0 token {SecretMgrClient.auth0_token}")
                raise ValueError(f"invalid auth0 token !")

            # secretmgr url can be passed in
            secretmgr_url = os.getenv("SECRETMGR_URL")
            if secretmgr_url:
                url = f"{secretmgr_url}/1/internal/secret"
            else:
                url = f"https://secretmgr.{self.namespace}.svc.cluster.local/1/internal/secret"

            # https schema or http
            if url.startswith("https://"):
                is_https = True
                ca_crt = "/etc/tls/client/ca.crt"
                client_crt = "/etc/tls/client/tls.crt"
                client_key = "/etc/tls/client/tls.key"
                if not os.path.exists(ca_crt) or not os.path.exists(client_crt) or not os.path.exists(client_key):
                    raise ValueError("tls certificates needed for secretmgr!")
            else:
                is_https = False

            secret_name = key.strip()
            if not secret_name:
                raise ValueError("empty secret name")

            params = {
                "secret-name": secret_name,
                "secret-type": "raw",
            }
            headers = {
                "Authorization": f"Bearer {SecretMgrClient.auth0_token}",
                "Content-Type": "application/json",
            }

            if not is_https:
                response = requests.get(url, headers=headers, params=params, timeout=30)
            else:
                response = requests.get(url, headers=headers, params=params, timeout=30,
                                        cert=(client_crt, client_key),
                                        verify=(ca_crt)
                                        )
            if response.status_code == 404:
                SecretMgrClient.logger.info(f"secret name {secret_name} not found ")
                return None
            else:
                response.raise_for_status()

            if not response.content:
                raise Exception("Failed to read secret: empty response received.")

            data = response.json()
            return data["secret-value"]

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to read secret: {e}")

    def set_secret(self, key: str, value: str):
        raise Exception("method not allowed")

    def delete_secret(self, key: str):
        raise Exception("method not allowed")

    def renew_auth0_token(self):
        # skip if token still valid
        if self.check_token_expiry():
            return

        self.populate_auth0_client()

        auth_url = os.getenv("M2M_AUTH_TOKEN_URL")
        auth_audience = os.getenv("M2M_AUTH_AUDIENCE")
        if not auth_url or not auth_audience:
            raise ValueError("env M2M_AUTH_TOKEN_URL and M2M_AUTH_AUDIENCE required! ")

        headers = {"Content-Type": "application/json"}
        payload = {
            "grant_type": "client_credentials",
            "client_id": SecretMgrClient.auth0_client_id,
            "client_secret": SecretMgrClient.auth0_client_secret,
            "audience": auth_audience,
        }
        response = requests.post(auth_url, json=payload, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Error fetching token: {response.status_code}, {response.text}")

        SecretMgrClient.auth0_token = response.json().get("access_token")

    def check_token_expiry(self) -> bool:
        if not SecretMgrClient.auth0_token:
            return False

        try:
            decoded = jwt.decode(SecretMgrClient.auth0_token, options={"verify_signature": False})
            exp_timestamp = decoded.get("exp")
            if not exp_timestamp:
                raise ValueError("Token does not have an 'exp' claim.")

            exp_time = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            remaining_time = exp_time - now

            # give 1 mins buffer
            return remaining_time.total_seconds() > 1*60

        except jwt.DecodeError:
            raise ValueError("Invalid JWT token.")