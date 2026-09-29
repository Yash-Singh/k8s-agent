"""Detector for Kubernetes health probe failures (Liveness, Readiness, Startup)."""

import re
from typing import List, Optional
from k8s_agent.detectors.base import BaseDetector, DiagnosticFinding
from k8s_agent.models import EvidenceItem, LogEntry, RemediationAction, SeverityLevel


class ProbeDetector(BaseDetector):
    """Detects Liveness, Readiness, and Startup probe failures and timeouts."""

    PROBE_PATTERNS = [
        (re.compile(r"Liveness probe failed:\s*(.*)", re.IGNORECASE), "Liveness probe failure (triggers container kill & restart)"),
        (re.compile(r"Readiness probe failed:\s*(.*)", re.IGNORECASE), "Readiness probe failure (triggers removal from Service endpoints)"),
        (re.compile(r"Startup probe failed:\s*(.*)", re.IGNORECASE), "Startup probe failure (triggers kill during container initialization)"),
        (re.compile(r"Container [^\s]+ failed liveness probe, will be restarted", re.IGNORECASE), "Kubelet restarting container due to failed health check"),
        (re.compile(r"probe failed with statuscode:\s*(5\d\d)", re.IGNORECASE), "Health endpoint returned server HTTP 5xx error"),
        (re.compile(r"probe.*(?:timeout|deadline exceeded|timed out)", re.IGNORECASE), "Health probe timed out waiting for application response"),
        (re.compile(r"probe.*(?:connection refused|connect: connection refused)", re.IGNORECASE), "Health probe port connection refused (app not listening or locked)"),
    ]

    def detect(self, entries: List[LogEntry]) -> Optional[DiagnosticFinding]:
        evidence: List[EvidenceItem] = []
        is_liveness = False
        is_readiness = False
        is_startup = False

        for entry in entries:
            text = f"{entry.message} {entry.raw}"
            for pattern, desc in self.PROBE_PATTERNS:
                m = pattern.search(text)
                if m:
                    if "Liveness" in desc or "liveness" in text.lower():
                        is_liveness = True
                    if "Readiness" in desc or "readiness" in text.lower():
                        is_readiness = True
                    if "Startup" in desc or "startup" in text.lower():
                        is_startup = True

                    evidence.append(
                        EvidenceItem(
                            line_number=entry.line_number,
                            timestamp=entry.timestamp,
                            log_snippet=entry.message.strip(),
                            relevance=desc,
                            category="Fatal Event" if "restarted" in desc or "Liveness" in desc else "Symptom",
                        )
                    )
                    break

        if not evidence:
            return None

        probe_type = "Liveness" if is_liveness else ("Readiness" if is_readiness else ("Startup" if is_startup else "Health"))
        severity = SeverityLevel.CRITICAL if (is_liveness or is_startup) else SeverityLevel.HIGH

        if is_liveness:
            summary = (
                "The container's Liveness probe is failing or timing out. As designed, Kubernetes "
                "assumes the process is deadlocked or unresponsive and issues a SIGKILL to restart it."
            )
            consequence = "Repeated restarts disrupt ongoing requests and cause service instability."
        elif is_readiness:
            summary = (
                "The container's Readiness probe is failing. Kubernetes has removed this pod from the "
                "Service endpoints, preventing client traffic from routing to this instance."
            )
            consequence = "No traffic routed to pod; clients may experience HTTP 502/503 from Ingress."
        else:
            summary = (
                "The container's Startup probe failed, indicating the application did not finish initializing "
                "within the allocated startup grace period."
            )
            consequence = "Pod killed before reaching operational state."

        remediation = [
            RemediationAction(
                phase="immediate",
                title="Increase Probe initialDelaySeconds and timeoutSeconds",
                description="Give the application sufficient time to initialize or process background work before probe checks.",
                yaml_patch="""livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 30  # Increased from default
  periodSeconds: 10
  timeoutSeconds: 5        # Increased timeout for slow responses
  failureThreshold: 3""",
            ),
            RemediationAction(
                phase="diagnostic",
                title="Profile Health Check Endpoint Latency",
                description="Verify if /healthz endpoint performs heavy synchronous DB/network calls instead of simple shallow status checks.",
                command="kubectl exec -it <pod-name> -- curl -v http://localhost:8080/healthz",
            ),
            RemediationAction(
                phase="preventative",
                title="Decouple Deep Dependency Checks from Liveness Probes",
                description="Liveness probes should only verify process liveness. External dependency checks (DB, Redis) belong in Readiness probes.",
            ),
        ]

        return DiagnosticFinding(
            category="ProbeFailure",
            title=f"Kubernetes {probe_type} Probe Failure Detected",
            summary=f"{summary} {consequence}",
            severity=severity,
            confidence=0.92,
            primary_evidence=evidence,
            contributing_factors=[
                f"{probe_type} probe threshold or timeout too aggressive for current workload",
                "Health endpoint blocked by high CPU utilization or synchronous downstream dependency failure",
            ],
            remediation_actions=remediation,
            affected_components=[f"{probe_type} Probe", "Kubelet Prober", "Endpoint Controller"],
        )
