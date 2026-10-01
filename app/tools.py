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

"""Kubernetes cluster investigation tools for ADK agent."""

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


def _get_k8s_apis() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    """Initialize and return Kubernetes CoreV1Api and AppsV1Api clients.

    Tries in-cluster configuration first (for pods/deployments),
    then falls back to local kubeconfig.
    """
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except config.ConfigException as e:
            raise RuntimeError(f"Unable to load Kubernetes configuration: {e}")
    return client.CoreV1Api(), client.AppsV1Api()


def get_pod_logs(
    pod_name: str,
    namespace: str = "default",
    container: str = "",
    previous: bool = False,
    tail: int = 200,
) -> str:
    """Fetch logs from a specific Kubernetes pod for investigation.

    Args:
        pod_name: Name of the pod to fetch logs from.
        namespace: Kubernetes namespace where the pod is running. Defaults to 'default'.
        container: Specific container name (optional, defaults to primary container).
        previous: If True, retrieve logs for the previous terminated container instance (e.g., after a crash).
        tail: Number of most recent lines of logs to retrieve. Defaults to 200.

    Returns:
        String containing the pod log output, or an error message if retrieval failed.
    """
    try:
        core_v1, _ = _get_k8s_apis()
        kwargs = {
            "name": pod_name,
            "namespace": namespace,
            "previous": previous,
            "tail_lines": tail if tail > 0 else None,
        }
        if container:
            kwargs["container"] = container
        logs = core_v1.read_namespaced_pod_log(**kwargs)
        if not logs or not logs.strip():
            return f"Pod '{pod_name}' in namespace '{namespace}' produced no logs."
        return logs
    except ApiException as e:
        return f"Kubernetes API error fetching logs ({e.status}): {e.reason} - {e.body}"
    except Exception as e:
        return f"Failed to retrieve pod logs: {str(e)}"


def inspect_kubernetes_pods(namespace: str = "all", name_filter: str = "") -> str:
    """Inspect pods across namespaces or in a specific namespace on the active Kubernetes cluster.

    Args:
        namespace: Namespace to check. Use 'all' or empty string to check across all namespaces.
        name_filter: Optional substring filter (e.g. 'keda', 'metrics-server', 'hpa').

    Returns:
        Formatted tabular text listing namespace, pod name, ready status, phase, restarts, and IP.
    """
    try:
        core_v1, _ = _get_k8s_apis()
        if not namespace or namespace.lower() in ("all", "*"):
            pod_list = core_v1.list_pod_for_all_namespaces()
        else:
            pod_list = core_v1.list_namespaced_pod(namespace=namespace)

        lines = [f"{'NAMESPACE':<20} {'NAME':<45} {'READY':<10} {'STATUS':<15} {'RESTARTS':<10} {'IP':<15}"]
        for pod in pod_list.items:
            pod_name = pod.metadata.name or ""
            if name_filter and name_filter.lower() not in pod_name.lower():
                continue

            pod_ns = pod.metadata.namespace or ""
            pod_status = pod.status.phase if pod.status else "Unknown"

            container_statuses = pod.status.container_statuses if pod.status and pod.status.container_statuses else []
            ready_count = sum(1 for cs in container_statuses if cs.ready)
            total_containers = len(pod.spec.containers) if pod.spec and pod.spec.containers else len(container_statuses)
            ready_str = f"{ready_count}/{total_containers}"
            restart_count = sum(cs.restart_count for cs in container_statuses)
            pod_ip = pod.status.pod_ip or "<none>" if pod.status else "<none>"

            lines.append(
                f"{pod_ns:<20} {pod_name:<45} {ready_str:<10} {pod_status:<15} {restart_count:<10} {pod_ip:<15}"
            )

        if len(lines) == 1:
            return f"No pods found matching filter '{name_filter}'." if name_filter else "No pods found in cluster."

        return "\n".join(lines)
    except ApiException as e:
        return f"Kubernetes API error inspecting pods ({e.status}): {e.reason} - {e.body}"
    except Exception as e:
        return f"Failed to inspect pods: {str(e)}"


def check_kubernetes_deployments(namespace: str = "all") -> str:
    """List deployments across namespaces to check for controllers like metrics-server or keda-operator.

    Args:
        namespace: Namespace to check, or 'all' for all namespaces.

    Returns:
        Table of deployments in the cluster.
    """
    try:
        _, apps_v1 = _get_k8s_apis()
        if not namespace or namespace.lower() in ("all", "*"):
            dep_list = apps_v1.list_deployment_for_all_namespaces()
        else:
            dep_list = apps_v1.list_namespaced_deployment(namespace=namespace)

        lines = [f"{'NAMESPACE':<20} {'NAME':<40} {'READY':<10} {'UP-TO-DATE':<12} {'AVAILABLE':<12}"]
        for dep in dep_list.items:
            dep_ns = dep.metadata.namespace or ""
            dep_name = dep.metadata.name or ""
            replicas = dep.spec.replicas if dep.spec and dep.spec.replicas is not None else 0
            ready_replicas = dep.status.ready_replicas if dep.status and dep.status.ready_replicas is not None else 0
            updated_replicas = dep.status.updated_replicas if dep.status and dep.status.updated_replicas is not None else 0
            available_replicas = dep.status.available_replicas if dep.status and dep.status.available_replicas is not None else 0

            ready_str = f"{ready_replicas}/{replicas}"
            lines.append(
                f"{dep_ns:<20} {dep_name:<40} {ready_str:<10} {updated_replicas:<12} {available_replicas:<12}"
            )

        if len(lines) == 1:
            return "No deployments found in cluster."

        return "\n".join(lines)
    except ApiException as e:
        return f"Kubernetes API error querying deployments ({e.status}): {e.reason} - {e.body}"
    except Exception as e:
        return f"Failed to query deployments: {str(e)}"
