"""Detectors package exposing all specialized Kubernetes diagnostic detectors."""

from typing import List
from k8s_agent.detectors.base import BaseDetector, DiagnosticFinding
from k8s_agent.detectors.oom import OOMDetector
from k8s_agent.detectors.crashloop import CrashLoopDetector
from k8s_agent.detectors.probes import ProbeDetector
from k8s_agent.detectors.network import NetworkDNSDetector
from k8s_agent.detectors.image import ImagePullDetector
from k8s_agent.detectors.storage import StorageDetector
from k8s_agent.detectors.rbac import RBACDetector


def get_default_detectors() -> List[BaseDetector]:
    """Return default suite of detectors ordered by priority."""
    return [
        OOMDetector(),
        CrashLoopDetector(),
        ProbeDetector(),
        NetworkDNSDetector(),
        ImagePullDetector(),
        StorageDetector(),
        RBACDetector(),
    ]


__all__ = [
    "BaseDetector",
    "DiagnosticFinding",
    "OOMDetector",
    "CrashLoopDetector",
    "ProbeDetector",
    "NetworkDNSDetector",
    "ImagePullDetector",
    "StorageDetector",
    "RBACDetector",
    "get_default_detectors",
]
