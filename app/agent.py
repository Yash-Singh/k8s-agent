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

import subprocess
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

MODEL = "gemini-3.8-flash"


def inspect_kubernetes_pods(namespace: str = "all", name_filter: str = "") -> str:
    """Inspect pods across namespaces or in a specific namespace on the active Kubernetes cluster.

    Args:
        namespace: Namespace to check. Use 'all' or empty string to check across all namespaces (-A).
        name_filter: Optional substring filter (e.g. 'keda', 'metrics-server', 'hpa').

    Returns:
        Formatted tabular text listing namespace, pod name, status, restarts, and age.
    """
    cmd = ["kubectl", "get", "pods", "-o", "wide"]
    if not namespace or namespace.lower() in ("all", "*"):
        cmd.append("-A")
    else:
        cmd.extend(["-n", namespace])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            return f"Error executing kubectl: {res.stderr}"

        output_lines = res.stdout.splitlines()
        if not output_lines:
            return "No pods found in cluster."

        if name_filter:
            header = output_lines[0]
            matching = [line for line in output_lines[1:] if name_filter.lower() in line.lower()]
            if not matching:
                return f"No pods matching '{name_filter}' found across namespaces."
            return "\n".join([header] + matching)

        return res.stdout
    except Exception as e:
        return f"Failed to run kubectl: {str(e)}"


def check_kubernetes_deployments(namespace: str = "all") -> str:
    """List deployments across namespaces to check for controllers like metrics-server or keda-operator.

    Args:
        namespace: Namespace to check, or 'all' for all namespaces.

    Returns:
        Table of deployments in the cluster.
    """
    cmd = ["kubectl", "get", "deployments", "-o", "wide"]
    if not namespace or namespace.lower() in ("all", "*"):
        cmd.append("-A")
    else:
        cmd.extend(["-n", namespace])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return res.stdout if res.returncode == 0 else f"Error: {res.stderr}"
    except Exception as e:
        return f"Failed to query deployments: {str(e)}"


root_agent = Agent(
    name="k8s_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are an expert Kubernetes cluster investigation agent. "
        "Use your tools to inspect pods, deployments, services, and cluster resources to diagnose cluster health, "
        "HPA prerequisites (such as metrics-server or KEDA), and container failures."
    ),
    tools=[inspect_kubernetes_pods, check_kubernetes_deployments],
)

app = App(
    root_agent=root_agent,
    name="app",
)
