# ruff: noqa
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

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import (
    check_kubernetes_deployments,
    get_deployment_history,
    get_pod_events,
    get_pod_logs,
    inspect_kubernetes_pods,
)

MODEL = "gemini-3.8-flash"

root_agent = Agent(
    name="k8s_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an expert Kubernetes cluster investigation agent. "
        "Use your tools to inspect pods, deployments, services, and cluster resources to diagnose cluster health, "
        "HPA prerequisites (such as metrics-server or KEDA), and container failures. "
        "Instead of reading log files as input, use get_pod_logs to directly fetch logs, get_pod_events to inspect events, "
        "and get_deployment_history to analyze recent pod version or rollout changes when investigating."
    ),
    tools=[
        inspect_kubernetes_pods,
        check_kubernetes_deployments,
        get_pod_logs,
        get_pod_events,
        get_deployment_history,
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
