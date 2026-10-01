"""Unit tests for Kubernetes interaction tools in app/tools.py."""

from unittest.mock import MagicMock, patch
from kubernetes.client.exceptions import ApiException
from app.tools import get_pod_logs, inspect_kubernetes_pods, check_kubernetes_deployments


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
