"""Detector for Kubernetes storage, persistent volume (PV/PVC), and disk pressure failures."""

import re
from typing import List, Optional
from k8s_agent.detectors.base import BaseDetector, DiagnosticFinding
from k8s_agent.models import EvidenceItem, LogEntry, RemediationAction, SeverityLevel


class StorageDetector(BaseDetector):
    """Detects PVC mount failures, read-only file systems, disk space exhaustion, and node disk pressure."""

    PATTERNS = [
        (re.compile(r"Read-only file system", re.IGNORECASE), "File system mounted as Read-Only or corrupted into read-only mode"),
        (re.compile(r"No space left on device|ENOSPC", re.IGNORECASE), "Disk or volume capacity exhausted (ENOSPC)"),
        (re.compile(r"NodeHasDiskPressure|eviction manager: node [^\s]+ has disk pressure", re.IGNORECASE), "Kubernetes node reported DiskPressure condition"),
        (re.compile(r"FailedMount|Unable to attach or mount volumes", re.IGNORECASE), "Kubelet VolumeManager failed to attach or mount persistent volume"),
        (re.compile(r"VolumeSubpathInitializationFailed|subpath.*does not exist", re.IGNORECASE), "Kubernetes volume mount subPath initialization failure"),
    ]

    def detect(self, entries: List[LogEntry]) -> Optional[DiagnosticFinding]:
        evidence: List[EvidenceItem] = []

        for entry in entries:
            text = f"{entry.message} {entry.raw}"
            for pattern, desc in self.PATTERNS:
                if pattern.search(text):
                    evidence.append(
                        EvidenceItem(
                            line_number=entry.line_number,
                            timestamp=entry.timestamp,
                            log_snippet=entry.message.strip(),
                            relevance=desc,
                            category="Fatal Event" if "No space" in desc or "Read-only" in desc else "Trigger",
                        )
                    )
                    break

        if not evidence:
            return None

        remediation = [
            RemediationAction(
                phase="immediate",
                title="Inspect PVC and PV Bound Status and Capacity",
                description="Check storage capacity and volume claim status.",
                command="kubectl get pvc,pv -A && kubectl describe pvc <pvc-name>",
            ),
            RemediationAction(
                phase="immediate",
                title="Expand PersistentVolumeClaim Size",
                description="If the storageClass supports volume expansion, increase PVC storage request.",
                yaml_patch="""spec:
  resources:
    requests:
      storage: 50Gi  # Increased storage request""",
            ),
            RemediationAction(
                phase="diagnostic",
                title="Check Disk Utilization Inside Pod or Node",
                description="Identify which log directory or temporary path consumed the available inodes or blocks.",
                command="kubectl exec <pod-name> -- df -h",
            ),
        ]

        return DiagnosticFinding(
            category="DiskPressure",
            title="Storage / Volume Exhaustion or Mount Failure",
            summary=(
                "The container or node encountered storage failure: either volume space is exhausted (ENOSPC), "
                "the volume is mounted as read-only, or the CSI storage driver failed to attach the volume."
            ),
            severity=SeverityLevel.HIGH,
            confidence=0.90,
            primary_evidence=evidence,
            contributing_factors=[
                "Unbounded application log or temporary file generation in ephemeral storage",
                "Persistent volume claim (PVC) filled to 100% capacity",
                "CSI plugin failed to detach volume from previous node",
            ],
            remediation_actions=remediation,
            affected_components=["PersistentVolumeClaim", "CSI Driver", "Kubelet VolumeManager"],
        )
