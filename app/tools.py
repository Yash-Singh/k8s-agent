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


def get_pod_events(pod_name: str, namespace: str = "default") -> str:
    """Fetch Kubernetes events related to a specific pod for troubleshooting.

    Args:
        pod_name: Name of the pod to fetch events for.
        namespace: Kubernetes namespace where the pod is running. Defaults to 'default'.

    Returns:
        Formatted string listing events (Type, Reason, Age/Timestamp, Component, Message)
        for the given pod, or an informational/error message.
    """
    try:
        core_v1, _ = _get_k8s_apis()
        field_selector = f"involvedObject.name={pod_name},involvedObject.kind=Pod"
        events = core_v1.list_namespaced_event(namespace=namespace, field_selector=field_selector)

        if not events.items:
            events = core_v1.list_namespaced_event(
                namespace=namespace, field_selector=f"involvedObject.name={pod_name}"
            )

        if not events.items:
            return f"No events found for pod '{pod_name}' in namespace '{namespace}'."

        sorted_events = sorted(
            events.items,
            key=lambda e: str(e.last_timestamp or e.event_time or e.first_timestamp or ""),
        )

        lines = [f"{'TYPE':<10} {'REASON':<20} {'AGE/TIME':<25} {'FROM':<20} {'MESSAGE'}"]
        for event in sorted_events:
            event_type = event.type or "Normal"
            reason = event.reason or "Unknown"
            timestamp = str(event.last_timestamp or event.event_time or event.first_timestamp or "<unknown>")
            source = (
                event.source.component
                if event.source and event.source.component
                else (event.reporting_component or "<unknown>")
            )
            count_str = f" (x{event.count})" if event.count and event.count > 1 else ""
            message = f"{event.message or ''}{count_str}"
            lines.append(f"{event_type:<10} {reason:<20} {timestamp:<25} {source:<20} {message}")

        return "\n".join(lines)
    except ApiException as e:
        return f"Kubernetes API error fetching events ({e.status}): {e.reason} - {e.body}"
    except Exception as e:
        return f"Failed to retrieve pod events: {str(e)}"


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


def get_deployment_history(deployment_name: str, namespace: str = "default") -> str:
    """Fetch and analyze the rollout revision history of a deployment to detect recent changes in pod versions/images.

    Args:
        deployment_name: Name of the Kubernetes deployment.
        namespace: Kubernetes namespace where the deployment lives. Defaults to 'default'.

    Returns:
        Formatted summary showing rollout revisions, timestamps, container images (pod versions),
        and detected differences across recent revisions.
    """
    try:
        _, apps_v1 = _get_k8s_apis()
        try:
            dep = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        except ApiException as e:
            return f"Kubernetes API error fetching deployment '{deployment_name}' ({e.status}): {e.reason} - {e.body}"

        # Fetch all replica sets in the namespace
        rs_list = apps_v1.list_namespaced_replica_set(namespace=namespace)

        # Filter ReplicaSets owned by this deployment
        dep_uid = dep.metadata.uid if dep.metadata else None
        matching_rs = []
        for rs in rs_list.items:
            is_owned = False
            if rs.metadata and rs.metadata.owner_references:
                for owner in rs.metadata.owner_references:
                    if owner.kind == "Deployment" and (
                        (dep_uid and owner.uid == dep_uid) or owner.name == deployment_name
                    ):
                        is_owned = True
                        break
            if is_owned:
                matching_rs.append(rs)

        if not matching_rs:
            return f"No rollout history (ReplicaSets) found for deployment '{deployment_name}' in namespace '{namespace}'."

        revisions_data = []
        for rs in matching_rs:
            annotations = rs.metadata.annotations or {} if rs.metadata else {}
            rev_str = annotations.get("deployment.kubernetes.io/revision", "0")
            try:
                rev_num = int(rev_str)
            except ValueError:
                rev_num = 0

            change_cause = annotations.get("kubernetes.io/change-cause", "<none>")
            creation_time = str(rs.metadata.creation_timestamp or "<unknown>") if rs.metadata else "<unknown>"

            # Extract container images
            container_images = {}
            if (
                rs.spec
                and rs.spec.template
                and rs.spec.template.spec
                and rs.spec.template.spec.containers
            ):
                for c in rs.spec.template.spec.containers:
                    container_images[c.name] = c.image

            replicas = rs.status.replicas if rs.status and rs.status.replicas is not None else 0
            ready_replicas = rs.status.ready_replicas if rs.status and rs.status.ready_replicas is not None else 0
            is_active = (replicas > 0)

            revisions_data.append({
                "rev_num": rev_num,
                "rev_str": rev_str,
                "rs_name": rs.metadata.name if rs.metadata else "",
                "creation_time": creation_time,
                "change_cause": change_cause,
                "images": container_images,
                "replicas": replicas,
                "ready_replicas": ready_replicas,
                "is_active": is_active,
            })

        # Sort chronologically by revision number
        revisions_data.sort(key=lambda r: r["rev_num"])

        # Format output
        output_lines = [
            f"=== Rollout History for Deployment '{deployment_name}' (Namespace: '{namespace}') ===",
            "",
            f"{'REVISION':<10} {'ACTIVE':<8} {'CREATED':<25} {'CONTAINER(S) & IMAGE':<50} {'CHANGE CAUSE'}",
        ]

        for rev in revisions_data:
            active_marker = "YES" if rev["is_active"] else "no"
            images_str = ", ".join(f"{c}: {img}" for c, img in rev["images"].items())
            output_lines.append(
                f"{rev['rev_str']:<10} {active_marker:<8} {rev['creation_time']:<25} {images_str:<50} {rev['change_cause']}"
            )

        # Version change analysis
        output_lines.append("")
        output_lines.append("=== Pod Version Change Analysis ===")
        if len(revisions_data) > 1:
            latest = revisions_data[-1]
            prev = revisions_data[-2]
            changes_detected = False

            # Check for container image updates
            all_containers = set(latest["images"].keys()).union(set(prev["images"].keys()))
            for c_name in sorted(all_containers):
                prev_img = prev["images"].get(c_name, "<not present>")
                latest_img = latest["images"].get(c_name, "<not present>")
                if prev_img != latest_img:
                    output_lines.append(
                        f"• Container '{c_name}': Updated from '{prev_img}' (Revision {prev['rev_str']}) to '{latest_img}' (Revision {latest['rev_str']})"
                    )
                    changes_detected = True

            if not changes_detected:
                output_lines.append(
                    f"• No container image change detected between Revision {prev['rev_str']} and Revision {latest['rev_str']} (configmap/secret/replica change)."
                )
        else:
            current_rev = revisions_data[0]
            current_images = ", ".join(f"{c}: {img}" for c, img in current_rev["images"].items())
            output_lines.append(
                f"• Single revision deployed (Revision {current_rev['rev_str']}). Current pod image: {current_images}."
            )

        return "\n".join(output_lines)
    except ApiException as e:
        return f"Kubernetes API error querying deployment history ({e.status}): {e.reason} - {e.body}"
    except Exception as e:
        return f"Failed to retrieve deployment history: {str(e)}"
