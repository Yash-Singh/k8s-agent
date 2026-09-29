"""Detector for Out Of Memory (OOM) failures in Kubernetes."""

import re
from typing import List, Optional
from k8s_agent.detectors.base import BaseDetector, DiagnosticFinding
from k8s_agent.models import EvidenceItem, LogEntry, RemediationAction, SeverityLevel


class OOMDetector(BaseDetector):
    """Detects container cgroup OOM kills, kernel OOM invocations, and runtime heap exhaustion."""

    OOM_PATTERNS = [
        (re.compile(r"oom[-_]?killed\s*[:=]?\s*true", re.IGNORECASE), "OOMKilled flag reported by runtime"),
        (re.compile(r"command terminated with exit code 137|exit code:?\s*137|terminated with (?:status|exit code) 137", re.IGNORECASE), "Process terminated with Exit Code 137 (SIGKILL by Linux OOM-killer)"),
        (re.compile(r"invoked oom-killer|kernel:\s*Out of memory:\s*Kill process|oom_reaper:\s*reaped process", re.IGNORECASE), "Linux kernel Out of Memory (OOM) killer invoked"),
        (re.compile(r"memory cgroup out of memory|cgroup\.memory:\s*usage exceeds limit|exceeded memory limit", re.IGNORECASE), "Container memory usage exceeded Kubernetes cgroup limit"),
        (re.compile(r"java\.lang\.OutOfMemoryError:\s*(?:Java heap space|GC overhead limit exceeded|Metaspace)", re.IGNORECASE), "JVM OutOfMemoryError detected"),
        (re.compile(r"fatal error:\s*runtime:\s*out of memory", re.IGNORECASE), "Go runtime memory allocation failure"),
        (re.compile(r"JavaScript heap out of memory", re.IGNORECASE), "Node.js V8 heap out of memory"),
    ]

    def detect(self, entries: List[LogEntry]) -> Optional[DiagnosticFinding]:
        evidence: List[EvidenceItem] = []
        matched_indicators = []

        for entry in entries:
            text = f"{entry.message} {entry.raw}"
            for pattern, desc in self.OOM_PATTERNS:
                if pattern.search(text):
                    category = "Fatal Event" if "137" in desc or "cgroup" in desc or "OutOfMemory" in desc else "Trigger"
                    evidence.append(
                        EvidenceItem(
                            line_number=entry.line_number,
                            timestamp=entry.timestamp,
                            log_snippet=entry.message.strip(),
                            relevance=desc,
                            category=category,
                        )
                    )
                    matched_indicators.append(desc)
                    break

        if not evidence:
            return None

        # Determine confidence based on specific indicators
        is_hard_oom = any("137" in ind or "cgroup" in ind or "kernel" in ind or "OOMKilled" in ind for ind in matched_indicators)
        confidence = 0.98 if is_hard_oom else 0.85

        contributing = [
            "Container memory limit (resources.limits.memory) is insufficient for current workload",
            "Potential memory leak or unbounded cache allocation in application process",
            "Node memory pressure leading to cgroup eviction",
        ]

        remediation = [
            RemediationAction(
                phase="immediate",
                title="Increase Container Memory Limits",
                description="Patch the container memory limit to allow headroom while investigating leaks.",
                command="kubectl patch deployment <deployment-name> -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"<container>\",\"resources\":{\"limits\":{\"memory\":\"2Gi\"},\"requests\":{\"memory\":\"1Gi\"}}}]}}}}'",
                yaml_patch="""resources:
  requests:
    memory: "1Gi"
  limits:
    memory: "2Gi" """,
            ),
            RemediationAction(
                phase="immediate",
                title="Inspect Historical Pod Resource Consumption",
                description="Check recent resource metrics and previous container termination state.",
                command="kubectl top pod <pod-name> --containers && kubectl describe pod <pod-name> | grep -A 5 -B 5 -i oom",
            ),
            RemediationAction(
                phase="preventative",
                title="Profile Application Heap & Tune GC/Concurrency",
                description="Capture heap profiles or limit concurrency pool sizes to prevent unbounded memory spikes under load.",
            ),
        ]

        return DiagnosticFinding(
            category="OOMKilled",
            title="Container Terminated Due to Out Of Memory (OOMKilled)",
            summary=(
                "The container was forcibly killed by the operating system kernel or Kubernetes runtime "
                "because its memory consumption exceeded the allocated cgroup limit (Exit Code 137)."
            ),
            severity=SeverityLevel.CRITICAL,
            confidence=confidence,
            primary_evidence=evidence,
            contributing_factors=contributing,
            remediation_actions=remediation,
            affected_components=["Container Cgroup", "Kernel OOM Killer", "Kubernetes Pod Memory Limit"],
        )
