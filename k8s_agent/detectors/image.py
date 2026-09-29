"""Detector for ImagePullBackOff, ErrImagePull, and registry authentication errors."""

import re
from typing import List, Optional
from k8s_agent.detectors.base import BaseDetector, DiagnosticFinding
from k8s_agent.models import EvidenceItem, LogEntry, RemediationAction, SeverityLevel


class ImagePullDetector(BaseDetector):
    """Detects ImagePullBackOff, ErrImagePull, registry auth rejections, and missing tags."""

    PATTERNS = [
        (re.compile(r"ImagePullBackOff|ErrImagePull", re.IGNORECASE), "Container failed to pull specified image"),
        (re.compile(r"manifest for [^\s]+ not found|manifest unknown", re.IGNORECASE), "Image tag or manifest does not exist in registry"),
        (re.compile(r"pull access denied|unauthorized:\s*authentication required|401 Unauthorized|403 Forbidden", re.IGNORECASE), "Registry rejected authentication (missing or invalid credentials)"),
        (re.compile(r"rpc error: code = Unknown desc = failed to pull and unpack image", re.IGNORECASE), "CRI failed to unpack or verify container image layers"),
        (re.compile(r"x509: certificate signed by unknown authority", re.IGNORECASE), "TLS certificate verification failure connecting to image registry"),
    ]

    def detect(self, entries: List[LogEntry]) -> Optional[DiagnosticFinding]:
        evidence: List[EvidenceItem] = []
        is_auth = False
        is_not_found = False

        for entry in entries:
            text = f"{entry.message} {entry.raw}"
            for pattern, desc in self.PATTERNS:
                if pattern.search(text):
                    if "unauthorized" in text.lower() or "401" in text or "access denied" in text.lower():
                        is_auth = True
                    if "not found" in text.lower() or "manifest unknown" in text.lower():
                        is_not_found = True

                    evidence.append(
                        EvidenceItem(
                            line_number=entry.line_number,
                            timestamp=entry.timestamp,
                            log_snippet=entry.message.strip(),
                            relevance=desc,
                            category="Root Trigger" if is_auth or is_not_found else "Fatal Event",
                        )
                    )
                    break

        if not evidence:
            return None

        if is_auth:
            title = "Container Image Pull Denied (Authentication / Authorization Failure)"
            summary = (
                "Kubernetes could not pull the container image because the registry rejected authentication. "
                "The pod is missing a valid imagePullSecret or the registry token has expired."
            )
            remediation = [
                RemediationAction(
                    phase="immediate",
                    title="Create or Update imagePullSecret",
                    description="Generate a docker-registry secret with valid container registry credentials.",
                    command="kubectl create secret docker-registry regcred --docker-server=<registry> --docker-username=<user> --docker-password=<token> --docker-email=<email>",
                ),
                RemediationAction(
                    phase="immediate",
                    title="Attach imagePullSecrets to Pod or ServiceAccount",
                    description="Link the imagePullSecret to the pod spec or the default service account.",
                    yaml_patch="""imagePullSecrets:
  - name: regcred""",
                ),
            ]
        elif is_not_found:
            title = "Container Image or Tag Not Found (ErrImagePull)"
            summary = (
                "The container image tag specified in the pod spec does not exist in the target registry. "
                "Check for typos or verify the CI pipeline pushed the tag."
            )
            remediation = [
                RemediationAction(
                    phase="immediate",
                    title="Verify Image Tag and Existence in Registry",
                    description="Confirm the image tag was built and pushed successfully by CI/CD.",
                    command="docker pull <full-image-name>:<tag>",
                ),
            ]
        else:
            title = "ImagePullBackOff / Container Image Download Failure"
            summary = (
                "The kubelet container runtime failed to download or unpack the container image layers. "
                "The pod is in ImagePullBackOff."
            )
            remediation = [
                RemediationAction(
                    phase="immediate",
                    title="Describe Pod to View Detailed Kubelet Pull Events",
                    description="Fetch detailed event messages from the kubelet runtime.",
                    command="kubectl describe pod <pod-name> | grep -A 10 Events:",
                ),
            ]

        return DiagnosticFinding(
            category="ImagePullBackOff",
            title=title,
            summary=summary,
            severity=SeverityLevel.HIGH,
            confidence=0.96,
            primary_evidence=evidence,
            contributing_factors=[
                "Image tag mismatch between manifest and CI artifact",
                "Missing imagePullSecrets in the Kubernetes namespace",
                "Registry network firewall or rate limit (e.g. Docker Hub rate limits)",
            ],
            remediation_actions=remediation,
            affected_components=["Kubelet Image Manager", "Container Registry", "Pod ImagePullSecret"],
        )
