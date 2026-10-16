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

import contextlib
import ipaddress
import os
from collections.abc import AsyncIterator

from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes

load_dotenv()
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)
otel_to_cloud = True

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=otel_to_cloud,
    lifespan=lifespan,
)
app.title = "k8s-agent"
app.description = "API for interacting with the Agent k8s-agent"


def _get_allowed_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse comma-separated CIDRs from ALLOWED_CIDRS environment variable."""
    cidrs_env = os.getenv("ALLOWED_CIDRS", "").strip()
    if not cidrs_env:
        return []
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in cidrs_env.split(","):
        cidr_str = cidr.strip()
        if cidr_str:
            try:
                networks.append(ipaddress.ip_network(cidr_str, strict=False))
            except ValueError:
                pass
    return networks


@app.middleware("http")
async def cidr_allowlist_middleware(request: Request, call_next):
    """Enforce CIDR-based ingress allowlisting if ALLOWED_CIDRS is configured."""
    allowed_networks = _get_allowed_networks()
    if allowed_networks:
        client_ip_str: str | None = None
        if x_forwarded_for := request.headers.get("x-forwarded-for"):
            client_ip_str = x_forwarded_for.split(",")[0].strip()
        elif request.client:
            client_ip_str = request.client.host

        if not client_ip_str:
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: Unable to determine client IP"},
            )

        try:
            client_ip = ipaddress.ip_address(client_ip_str)
        except ValueError:
            return JSONResponse(
                status_code=403,
                content={"detail": f"Forbidden: Invalid client IP '{client_ip_str}'"},
            )

        if not any(client_ip in net for net in allowed_networks):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Forbidden: Client IP {client_ip_str} not in allowed CIDRs"
                },
            )

    return await call_next(request)


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
