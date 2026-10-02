"""Unit tests for Kubernetes interaction tools in app/tools.py."""

from unittest.mock import MagicMock, patch
from kubernetes.client.exceptions import ApiException
from app.tools import (
    check_kubernetes_deployments,
    get_deployment_history,
    get_pod_events,
    get_pod_logs,
    inspect_kubernetes_pods,
)


def test_get_pod_logs_success():
    mock_core_v1 = MagicMock()
    mock_core_v1.read_namespaced_pod_log.return_value = "line 1: service starting\nline 2: connected to db"

    with patch("app.tools._get_k8s_apis", return_value=(mock_core_v1, MagicMock())):
        logs = get_pod_logs("auth-service-pod", namespace="prod", container="backend", previous=True, tail=50)

    mock_core_v1.read_namespaced_pod_log.assert_called_once_with(
        name="auth-service-pod",
        namespace="prod",
        previous=True,
        tail_lines=50,
        container="backend",
    )
    assert "service starting" in logs
    assert "connected to db" in logs


def test_get_pod_logs_empty():
    mock_core_v1 = MagicMock()
    mock_core_v1.read_namespaced_pod_log.return_value = "   "

    with patch("app.tools._get_k8s_apis", return_value=(mock_core_v1, MagicMock())):
        logs = get_pod_logs("empty-pod", namespace="default")

    assert "produced no logs" in logs


def test_get_pod_logs_api_exception():
    mock_core_v1 = MagicMock()
    mock_core_v1.read_namespaced_pod_log.side_effect = ApiException(status=404, reason="Not Found")

    with patch("app.tools._get_k8s_apis", return_value=(mock_core_v1, MagicMock())):
        result = get_pod_logs("nonexistent-pod", namespace="default")

    assert "Kubernetes API error fetching logs (404)" in result
    assert "Not Found" in result


def test_inspect_kubernetes_pods_all():
    mock_core_v1 = MagicMock()
    pod = MagicMock()
    pod.metadata.name = "frontend-6d8b9487c8-x5z9k"
    pod.metadata.namespace = "web"
    pod.status.phase = "Running"
    cs = MagicMock()
    cs.ready = True
    cs.restart_count = 2
    pod.status.container_statuses = [cs]
    pod.spec.containers = [MagicMock()]
    pod.status.pod_ip = "10.244.0.15"

    mock_pod_list = MagicMock()
    mock_pod_list.items = [pod]
    mock_core_v1.list_pod_for_all_namespaces.return_value = mock_pod_list

    with patch("app.tools._get_k8s_apis", return_value=(mock_core_v1, MagicMock())):
        output = inspect_kubernetes_pods(namespace="all")

    assert "frontend-6d8b9487c8-x5z9k" in output
    assert "web" in output
    assert "1/1" in output
    assert "Running" in output


def test_inspect_kubernetes_pods_filter():
    mock_core_v1 = MagicMock()
    pod1 = MagicMock()
    pod1.metadata.name = "keda-operator-768568656-ab12"
    pod1.metadata.namespace = "keda"
    pod1.status.phase = "Running"
    pod1.status.container_statuses = []
    pod1.spec.containers = []
    pod1.status.pod_ip = "10.244.0.10"

    pod2 = MagicMock()
    pod2.metadata.name = "nginx-pod"
    pod2.metadata.namespace = "default"
    pod2.status.phase = "Running"
    pod2.status.container_statuses = []
    pod2.spec.containers = []
    pod2.status.pod_ip = "10.244.0.11"

    mock_pod_list = MagicMock()
    mock_pod_list.items = [pod1, pod2]
    mock_core_v1.list_pod_for_all_namespaces.return_value = mock_pod_list

    with patch("app.tools._get_k8s_apis", return_value=(mock_core_v1, MagicMock())):
        output = inspect_kubernetes_pods(namespace="all", name_filter="keda")

    assert "keda-operator" in output
    assert "nginx-pod" not in output


def test_check_kubernetes_deployments():
    mock_apps_v1 = MagicMock()
    dep = MagicMock()
    dep.metadata.name = "metrics-server"
    dep.metadata.namespace = "kube-system"
    dep.spec.replicas = 1
    dep.status.ready_replicas = 1
    dep.status.updated_replicas = 1
    dep.status.available_replicas = 1

    mock_dep_list = MagicMock()
    mock_dep_list.items = [dep]
    mock_apps_v1.list_deployment_for_all_namespaces.return_value = mock_dep_list

    with patch("app.tools._get_k8s_apis", return_value=(MagicMock(), mock_apps_v1)):
        output = check_kubernetes_deployments(namespace="all")

    assert "metrics-server" in output
    assert "kube-system" in output
    assert "1/1" in output


def test_get_pod_events_success():
    mock_core_v1 = MagicMock()
    event1 = MagicMock()
    event1.type = "Normal"
    event1.reason = "Scheduled"
    event1.last_timestamp = "2026-10-02T01:00:00Z"
    event1.event_time = None
    event1.first_timestamp = None
    event1.source.component = "default-scheduler"
    event1.count = 1
    event1.message = "Successfully assigned default/my-pod to node-1"

    event2 = MagicMock()
    event2.type = "Warning"
    event2.reason = "BackOff"
    event2.last_timestamp = "2026-10-02T01:05:00Z"
    event2.event_time = None
    event2.first_timestamp = None
    event2.source.component = "kubelet"
    event2.count = 5
    event2.message = "Back-off restarting failed container"

    mock_event_list = MagicMock()
    mock_event_list.items = [event1, event2]
    mock_core_v1.list_namespaced_event.return_value = mock_event_list

    with patch("app.tools._get_k8s_apis", return_value=(mock_core_v1, MagicMock())):
        output = get_pod_events("my-pod", namespace="default")

    assert "Scheduled" in output
    assert "BackOff" in output
    assert "Successfully assigned" in output
    assert "(x5)" in output
    assert "default-scheduler" in output


def test_get_pod_events_empty():
    mock_core_v1 = MagicMock()
    mock_event_list = MagicMock()
    mock_event_list.items = []
    mock_core_v1.list_namespaced_event.return_value = mock_event_list

    with patch("app.tools._get_k8s_apis", return_value=(mock_core_v1, MagicMock())):
        output = get_pod_events("my-pod", namespace="default")

    assert "No events found for pod 'my-pod'" in output


def test_get_pod_events_api_exception():
    mock_core_v1 = MagicMock()
    mock_core_v1.list_namespaced_event.side_effect = ApiException(status=403, reason="Forbidden")

    with patch("app.tools._get_k8s_apis", return_value=(mock_core_v1, MagicMock())):
        output = get_pod_events("my-pod", namespace="default")

    assert "Kubernetes API error fetching events (403)" in output
    assert "Forbidden" in output


def test_get_deployment_history_success_with_version_change():
    mock_apps_v1 = MagicMock()

    dep = MagicMock()
    dep.metadata.uid = "dep-uid-123"
    dep.metadata.name = "web-app"
    mock_apps_v1.read_namespaced_deployment.return_value = dep

    owner_ref = MagicMock()
    owner_ref.kind = "Deployment"
    owner_ref.uid = "dep-uid-123"
    owner_ref.name = "web-app"

    # Revision 1 (old)
    rs1 = MagicMock()
    rs1.metadata.name = "web-app-rev1"
    rs1.metadata.owner_references = [owner_ref]
    rs1.metadata.annotations = {
        "deployment.kubernetes.io/revision": "1",
        "kubernetes.io/change-cause": "Initial deployment",
    }
    rs1.metadata.creation_timestamp = "2026-10-01T10:00:00Z"
    c1 = MagicMock()
    c1.name = "web"
    c1.image = "my-registry.io/web:v1.0.0"
    rs1.spec.template.spec.containers = [c1]
    rs1.status.replicas = 0
    rs1.status.ready_replicas = 0

    # Revision 2 (current)
    rs2 = MagicMock()
    rs2.metadata.name = "web-app-rev2"
    rs2.metadata.owner_references = [owner_ref]
    rs2.metadata.annotations = {
        "deployment.kubernetes.io/revision": "2",
        "kubernetes.io/change-cause": "Upgrade to v1.1.0",
    }
    rs2.metadata.creation_timestamp = "2026-10-02T12:00:00Z"
    c2 = MagicMock()
    c2.name = "web"
    c2.image = "my-registry.io/web:v1.1.0"
    rs2.spec.template.spec.containers = [c2]
    rs2.status.replicas = 3
    rs2.status.ready_replicas = 3

    mock_rs_list = MagicMock()
    mock_rs_list.items = [rs2, rs1]  # out of order to test sorting
    mock_apps_v1.list_namespaced_replica_set.return_value = mock_rs_list

    with patch("app.tools._get_k8s_apis", return_value=(MagicMock(), mock_apps_v1)):
        output = get_deployment_history("web-app", namespace="prod")

    assert "Rollout History for Deployment 'web-app'" in output
    assert "my-registry.io/web:v1.0.0" in output
    assert "my-registry.io/web:v1.1.0" in output
    assert "YES" in output  # Revision 2 is active
    assert "Pod Version Change Analysis" in output
    assert "Updated from 'my-registry.io/web:v1.0.0' (Revision 1) to 'my-registry.io/web:v1.1.0' (Revision 2)" in output


def test_get_deployment_history_single_revision():
    mock_apps_v1 = MagicMock()

    dep = MagicMock()
    dep.metadata.uid = "dep-uid-456"
    dep.metadata.name = "single-dep"
    mock_apps_v1.read_namespaced_deployment.return_value = dep

    owner_ref = MagicMock()
    owner_ref.kind = "Deployment"
    owner_ref.uid = "dep-uid-456"
    owner_ref.name = "single-dep"

    rs = MagicMock()
    rs.metadata.name = "single-dep-rev1"
    rs.metadata.owner_references = [owner_ref]
    rs.metadata.annotations = {"deployment.kubernetes.io/revision": "1"}
    rs.metadata.creation_timestamp = "2026-10-02T10:00:00Z"
    c = MagicMock()
    c.name = "api"
    c.image = "my-registry.io/api:v1.0.0"
    rs.spec.template.spec.containers = [c]
    rs.status.replicas = 2
    rs.status.ready_replicas = 2

    mock_rs_list = MagicMock()
    mock_rs_list.items = [rs]
    mock_apps_v1.list_namespaced_replica_set.return_value = mock_rs_list

    with patch("app.tools._get_k8s_apis", return_value=(MagicMock(), mock_apps_v1)):
        output = get_deployment_history("single-dep", namespace="default")

    assert "Single revision deployed (Revision 1)" in output
    assert "my-registry.io/api:v1.0.0" in output


def test_get_deployment_history_not_found():
    mock_apps_v1 = MagicMock()
    mock_apps_v1.read_namespaced_deployment.side_effect = ApiException(status=404, reason="Not Found")

    with patch("app.tools._get_k8s_apis", return_value=(MagicMock(), mock_apps_v1)):
        output = get_deployment_history("missing-dep", namespace="default")

    assert "Kubernetes API error fetching deployment 'missing-dep' (404)" in output
    assert "Not Found" in output


def test_get_deployment_history_no_replicasets():
    mock_apps_v1 = MagicMock()
    dep = MagicMock()
    dep.metadata.uid = "dep-uid-789"
    dep.metadata.name = "empty-dep"
    mock_apps_v1.read_namespaced_deployment.return_value = dep

    mock_rs_list = MagicMock()
    mock_rs_list.items = []
    mock_apps_v1.list_namespaced_replica_set.return_value = mock_rs_list

    with patch("app.tools._get_k8s_apis", return_value=(MagicMock(), mock_apps_v1)):
        output = get_deployment_history("empty-dep", namespace="default")

    assert "No rollout history (ReplicaSets) found" in output


