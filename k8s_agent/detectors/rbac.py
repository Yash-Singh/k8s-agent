"""Detector for Kubernetes RBAC, ServiceAccount permission, and admission webhook errors."""

import re
from typing import List, Optional
from k8s_agent.detectors.base import BaseDetector, DiagnosticFinding
from k8s_agent.models import EvidenceItem, LogEntry, RemediationAction, SeverityLevel


class RBACDetector(BaseDetector):
    """Detects RBAC 403 Forbidden errors, missing ServiceAccount tokens, and admission webhook rejections."""

    PATTERNS = [
        (re.compile(r"is forbidden:\s*User [^\s]+ cannot (?:get|list|watch|create|update|patch|delete) resource \"?([a-z0-9_-]+)\"?", re.IGNORECASE), "Kubernetes API RBAC authorization failure (403 Forbidden)"),
        (re.compile(r"system:serviceaccount:[^\s]+ cannot [^\s]+ resource", re.IGNORECASE), "ServiceAccount lacks required Role or ClusterRole permission"),
        (re.compile(r"failed calling webhook \"[^\"]+\": Post \"[^\"]+\": dial tcp.*connect: connection refused", re.IGNORECASE), "Admission webhook unreachable (ValidatingWebhookConfiguration or MutatingWebhookConfiguration failure)"),
        (re.compile(r"admission webhook \"[^\"]+\" denied the request", re.IGNORECASE), "Admission webhook policy explicitly denied the request"),
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
                            category="Root Trigger",
                        )
                    )
                    break

        if not evidence:
            return None

        remediation = [
            RemediationAction(
                phase="immediate",
                title="Create Role / ClusterRole with Required Permissions",
                description="Grant the appropriate API verb access to the Pod's ServiceAccount.",
                yaml_patch="""apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: pod-reader
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: read-pods-global
subjects:
- kind: ServiceAccount
  name: <service-account-name>
  namespace: <namespace>
roleRef:
  kind: ClusterRole
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io""",
            ),
            RemediationAction(
                phase="diagnostic",
                title="Verify ServiceAccount Authorization with kubectl auth can-i",
                description="Check what permissions the service account currently has.",
                command="kubectl auth can-i list pods --as=system:serviceaccount:<namespace>:<serviceaccount>",
            ),
        ]

        return DiagnosticFinding(
            category="RBAC",
            title="Kubernetes RBAC Authorization / Admission Webhook Denial",
            summary=(
                "The application attempted to perform an API operation against the Kubernetes API server, "
                "but was rejected with HTTP 403 Forbidden due to insufficient RBAC permissions or a webhook denial."
            ),
            severity=SeverityLevel.HIGH,
            confidence=0.95,
            primary_evidence=evidence,
            contributing_factors=[
                "Pod runs with default ServiceAccount which has no cluster permissions by default",
                "Missing RoleBinding or ClusterRoleBinding for target API resource",
            ],
            remediation_actions=remediation,
            affected_components=["Kubernetes API Server", "RBAC Authorizer", "ServiceAccount"],
        )
