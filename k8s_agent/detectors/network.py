"""Detector for Kubernetes network, DNS, and upstream service connectivity failures."""

import re
from typing import List, Optional
from k8s_agent.detectors.base import BaseDetector, DiagnosticFinding
from k8s_agent.models import EvidenceItem, LogEntry, RemediationAction, SeverityLevel


class NetworkDNSDetector(BaseDetector):
    """Detects CoreDNS timeouts, connection refused, upstream resets, and network partition errors."""

    PATTERNS = [
        (re.compile(r"lookup [^\s]+ on [0-9.:]+:\s*(?:no such host|server misbehaving|i/o timeout)", re.IGNORECASE), "DNS resolution failure via cluster DNS (CoreDNS)"),
        (re.compile(r"CoreDNS.*(?:SERVFAIL|NXDOMAIN|timeout)", re.IGNORECASE), "CoreDNS upstream resolution error"),
        (re.compile(r"dial tcp [0-9.:]+:\s*connect:\s*connection refused", re.IGNORECASE), "TCP connection refused on target host/port"),
        (re.compile(r"upstream connect error or disconnect/reset before headers|connection reset by peer", re.IGNORECASE), "Upstream service closed connection abruptly or Envoy proxy reset"),
        (re.compile(r"no route to host|network is unreachable|host is down", re.IGNORECASE), "Network routing failure or CNI plugin partition"),
        (re.compile(r"(?:database|postgres|mysql|redis|mongodb).*connection (?:refused|timed out|pool exhausted)", re.IGNORECASE), "Backend data store connection failure or pool exhaustion"),
        (re.compile(r"502 Bad Gateway|504 Gateway Timeout", re.IGNORECASE), "Ingress/Gateway HTTP proxy error communicating with backend pod"),
    ]

    def detect(self, entries: List[LogEntry]) -> Optional[DiagnosticFinding]:
        evidence: List[EvidenceItem] = []
        is_dns = False
        is_db = False

        for entry in entries:
            text = f"{entry.message} {entry.raw}"
            # Probe failures have their own specialized detector
            if "probe failed" in text.lower():
                continue
            for pattern, desc in self.PATTERNS:
                if pattern.search(text):
                    if "DNS" in desc or "lookup" in text.lower():
                        is_dns = True
                    if "database" in desc or "postgres" in text.lower() or "mysql" in text.lower():
                        is_db = True

                    evidence.append(
                        EvidenceItem(
                            line_number=entry.line_number,
                            timestamp=entry.timestamp,
                            log_snippet=entry.message.strip(),
                            relevance=desc,
                            category="Root Trigger" if "lookup" in text.lower() or "refused" in text.lower() else "Symptom",
                        )
                    )
                    break

        if not evidence:
            return None

        if is_dns:
            title = "DNS Resolution Failure via Kubernetes CoreDNS"
            summary = (
                "The container is unable to resolve service domain names through the cluster DNS "
                "(kube-dns/CoreDNS). Pods cannot discover dependent microservices or external APIs."
            )
            remediation = [
                RemediationAction(
                    phase="immediate",
                    title="Check CoreDNS Pods and Service Status",
                    description="Verify CoreDNS deployment is running and healthy in kube-system namespace.",
                    command="kubectl get pods -n kube-system -l k8s-app=kube-dns && kubectl logs -n kube-system -l k8s-app=kube-dns --tail=50",
                ),
                RemediationAction(
                    phase="diagnostic",
                    title="Test In-Cluster DNS Resolution from a Debug Pod",
                    description="Run an ephemeral debug container with dnsutils to verify internal lookup.",
                    command="kubectl run dns-test --rm -it --image=infoblox/dnstools -- dig <service-name>.<namespace>.svc.cluster.local",
                ),
                RemediationAction(
                    phase="preventative",
                    title="Tune dnsConfig ndots Setting",
                    description="In Kubernetes, default ndots:5 causes multiple iterative search queries for external domains.",
                    yaml_patch="""dnsConfig:
  options:
    - name: ndots
      value: "2" """,
                ),
            ]
        elif is_db:
            title = "Database / Backend Service Connectivity Failure"
            summary = (
                "The container cannot establish or maintain connections to its backend database or cache. "
                "The connection was either refused, timed out, or connection pools were exhausted."
            )
            remediation = [
                RemediationAction(
                    phase="immediate",
                    title="Verify Database Service and Endpoints",
                    description="Check whether database service endpoints exist and pods are ready.",
                    command="kubectl get endpoints <db-service-name>",
                ),
                RemediationAction(
                    phase="diagnostic",
                    title="Inspect Database Pod Logs and Connections",
                    description="Check database server logs for maximum connection pool limits or authentication rejections.",
                    command="kubectl logs -l app=<db-app> --tail=100",
                ),
            ]
        else:
            title = "Network Connectivity or Upstream Connection Refused"
            summary = (
                "The container failed to communicate with an upstream network dependency. "
                "Connections are being rejected or abruptly closed."
            )
            remediation = [
                RemediationAction(
                    phase="immediate",
                    title="Check NetworkPolicies and Target Service Endpoints",
                    description="Ensure NetworkPolicies permit ingress/egress and target pod is listening on the configured port.",
                    command="kubectl get networkpolicy && kubectl get endpoints",
                ),
            ]

        return DiagnosticFinding(
            category="NetworkDNS",
            title=title,
            summary=summary,
            severity=SeverityLevel.HIGH,
            confidence=0.88,
            primary_evidence=evidence,
            contributing_factors=[
                "Target service is either not running, crashing, or bound to localhost instead of 0.0.0.0",
                "Cluster DNS (CoreDNS) rate limiting or packet drop in CNI layer",
                "Kubernetes NetworkPolicy blocking ingress or egress traffic",
            ],
            remediation_actions=remediation,
            affected_components=["CoreDNS", "Cluster CNI / Kube-Proxy", "Upstream Service"],
        )
