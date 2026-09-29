"""Unit tests for Kubernetes anomaly detectors."""

from k8s_agent.parser import LogParser
from k8s_agent.detectors.oom import OOMDetector
from k8s_agent.detectors.crashloop import CrashLoopDetector
from k8s_agent.detectors.probes import ProbeDetector
from k8s_agent.detectors.network import NetworkDNSDetector
from k8s_agent.detectors.image import ImagePullDetector
from k8s_agent.detectors.storage import StorageDetector
from k8s_agent.detectors.rbac import RBACDetector
from k8s_agent.models import SeverityLevel


def test_oom_detector():
    raw = """
2026-09-28T14:10:00Z stdout F Starting worker
2026-09-28T14:11:00Z stderr F java.lang.OutOfMemoryError: Java heap space
2026-09-28T14:11:01Z system F Warning OOMKilled pod/worker-1 Memory cgroup out of memory: Container worker was terminated with exit code 137
"""
    entries = LogParser().parse(raw)
    detector = OOMDetector()
    finding = detector.detect(entries)

    assert finding is not None
    assert finding.category == "OOMKilled"
    assert finding.severity == SeverityLevel.CRITICAL
    assert finding.confidence >= 0.95
    assert len(finding.primary_evidence) >= 2


def test_crashloop_detector():
    raw = """
2026-09-28T10:00:00Z stderr F panic: runtime error: invalid memory address or nil pointer dereference
2026-09-28T10:00:01Z system F command terminated with exit code 2
2026-09-28T10:00:02Z system F Warning BackOff pod/app-1 Back-off restarting failed container
"""
    entries = LogParser().parse(raw)
    detector = CrashLoopDetector()
    finding = detector.detect(entries)

    assert finding is not None
    assert finding.category == "CrashLoopBackOff"
    assert finding.severity == SeverityLevel.CRITICAL
    assert "panic" in finding.summary.lower()


def test_probe_detector():
    raw = """
2026-09-28T16:00:00Z system F Warning Unhealthy pod/api-1 Liveness probe failed: HTTP probe failed with statuscode: 500
2026-09-28T16:00:05Z system F Normal Killing pod/api-1 Container api failed liveness probe, will be restarted
"""
    entries = LogParser().parse(raw)
    detector = ProbeDetector()
    finding = detector.detect(entries)

    assert finding is not None
    assert finding.category == "ProbeFailure"
    assert "Liveness" in finding.title
    assert finding.severity == SeverityLevel.CRITICAL


def test_network_dns_detector():
    raw = """
2026-09-28T12:00:00Z stderr F [ERROR] dial tcp: lookup payment-service.default.svc.cluster.local on 10.96.0.10:53: no such host
2026-09-28T12:00:01Z stderr F [ERROR] CoreDNS server failure (SERVFAIL)
"""
    entries = LogParser().parse(raw)
    detector = NetworkDNSDetector()
    finding = detector.detect(entries)

    assert finding is not None
    assert finding.category == "NetworkDNS"
    assert "DNS" in finding.title
    assert any("CoreDNS" in ev.relevance or "DNS" in ev.relevance for ev in finding.primary_evidence)


def test_image_pull_detector():
    raw = """
2026-09-28T08:00:00Z system F Warning Failed pod/vault-1 Failed to pull image: 401 Unauthorized
2026-09-28T08:00:01Z system F Warning Failed pod/vault-1 Error: ImagePullBackOff
"""
    entries = LogParser().parse(raw)
    detector = ImagePullDetector()
    finding = detector.detect(entries)

    assert finding is not None
    assert finding.category == "ImagePullBackOff"
    assert "Denied" in finding.title or "Authentication" in finding.title


def test_storage_detector():
    raw = """
2026-09-28T18:00:00Z stderr F [ERROR] Failed to write block: No space left on device
2026-09-28T18:00:01Z system F Warning NodeHasDiskPressure node/worker-1 Node worker-1 status is now: NodeHasDiskPressure
"""
    entries = LogParser().parse(raw)
    detector = StorageDetector()
    finding = detector.detect(entries)

    assert finding is not None
    assert finding.category == "DiskPressure"
    assert finding.severity == SeverityLevel.HIGH


def test_rbac_detector():
    raw = """
2026-09-28T19:00:00Z stderr F [ERROR] User "system:serviceaccount:default:my-app" cannot list resource "secrets" in API group "" in the namespace "default"
"""
    entries = LogParser().parse(raw)
    detector = RBACDetector()
    finding = detector.detect(entries)

    assert finding is not None
    assert finding.category == "RBAC"
    assert finding.severity == SeverityLevel.HIGH
