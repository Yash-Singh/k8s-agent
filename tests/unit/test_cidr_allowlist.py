# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import ipaddress
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.fast_api_app import _get_allowed_networks, app


def test_get_allowed_networks_empty():
    with patch.dict(os.environ, {"ALLOWED_CIDRS": ""}):
        assert _get_allowed_networks() == []


def test_get_allowed_networks_valid():
    with patch.dict(os.environ, {"ALLOWED_CIDRS": "10.10.1.0/24, 192.168.1.0/24"}):
        networks = _get_allowed_networks()
        assert len(networks) == 2
        assert ipaddress.ip_network("10.10.1.0/24") in networks
        assert ipaddress.ip_network("192.168.1.0/24") in networks


def test_cidr_allowlist_unrestricted_when_env_unset():
    client = TestClient(app)
    with patch.dict(os.environ, {"ALLOWED_CIDRS": ""}):
        # Any IP is permitted when ALLOWED_CIDRS is unset
        response = client.get("/docs", headers={"X-Forwarded-For": "203.0.113.1"})
        assert response.status_code == 200


def test_cidr_allowlist_allowed_ip():
    client = TestClient(app)
    with patch.dict(os.environ, {"ALLOWED_CIDRS": "10.10.1.0/24,192.168.0.0/16"}):
        response = client.get("/docs", headers={"X-Forwarded-For": "10.10.1.50"})
        assert response.status_code == 200

        # Multi-hop X-Forwarded-For (client is first IP)
        response_multi = client.get(
            "/docs", headers={"X-Forwarded-For": "10.10.1.99, 10.0.0.1"}
        )
        assert response_multi.status_code == 200


def test_cidr_allowlist_blocked_ip():
    client = TestClient(app)
    with patch.dict(os.environ, {"ALLOWED_CIDRS": "10.10.1.0/24"}):
        response = client.get("/docs", headers={"X-Forwarded-For": "192.168.1.1"})
        assert response.status_code == 403
        assert "not in allowed CIDRs" in response.json()["detail"]


def test_cidr_allowlist_invalid_ip():
    client = TestClient(app)
    with patch.dict(os.environ, {"ALLOWED_CIDRS": "10.10.1.0/24"}):
        response = client.get("/docs", headers={"X-Forwarded-For": "invalid-ip"})
        assert response.status_code == 403
        assert "Invalid client IP" in response.json()["detail"]
