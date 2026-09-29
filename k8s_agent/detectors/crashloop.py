"""Detector for CrashLoopBackOff and application crash failures in Kubernetes."""

import re
from typing import List, Optional
from k8s_agent.detectors.base import BaseDetector, DiagnosticFinding
from k8s_agent.models import EvidenceItem, LogEntry, RemediationAction, SeverityLevel


class CrashLoopDetector(BaseDetector):
    """Detects CrashLoopBackOff, unhandled application exceptions, fatal exit codes, and panics."""

    CRASH_SIGNATURES = [
        (re.compile(r"CrashLoopBackOff|Back-off restarting failed container", re.IGNORECASE), "Kubernetes Pod entered CrashLoopBackOff state"),
        (re.compile(r"command terminated with exit code (?:1|2|134|139)|exit code:?\s*(?:1|2|134|139)|terminated with exit code (?:1|2|134|139)", re.IGNORECASE), "Container process crashed with fatal exit code (1=Error, 134=SIGABRT, 139=SIGSEGV)"),
        (re.compile(r"panic:\s*runtime error:.*", re.IGNORECASE), "Fatal Go runtime panic"),
        (re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE), "Unhandled Python exception traceback"),
        (re.compile(r"uncaughtException|UnhandledPromiseRejection|FATAL ERROR:.*Allocation failed", re.IGNORECASE), "Uncaught Node.js process exception"),
        (re.compile(r"Exception in thread [^\n]+|FATAL:.*Application startup failed", re.IGNORECASE), "Fatal application startup failure"),
    ]

    ROOT_CAUSE_EXTRACTORS = [
        re.compile(r"(?:[A-Za-z0-9_]+Error|[A-Za-z0-9_]+Exception):\s*(.*)"),
        re.compile(r"panic:\s*(.*)"),
        re.compile(r"FATAL:\s*(.*)"),
    ]

    def detect(self, entries: List[LogEntry]) -> Optional[DiagnosticFinding]:
        evidence: List[EvidenceItem] = []
        isolated_root_cause = None

        for entry in entries:
            text = f"{entry.message}\n{entry.raw}"
            matched = False
            for pattern, desc in self.CRASH_SIGNATURES:
                if pattern.search(text):
                    evidence.append(
                        EvidenceItem(
                            line_number=entry.line_number,
                            timestamp=entry.timestamp,
                            log_snippet=entry.message.strip(),
                            relevance=desc,
                            category="Root Trigger" if "Traceback" in desc or "panic" in desc else "Fatal Event",
                        )
                    )
                    matched = True
                    break

            if matched and not isolated_root_cause:
                for extractor in self.ROOT_CAUSE_EXTRACTORS:
                    m = extractor.search(text)
                    if m:
                        isolated_root_cause = m.group(0).strip()
                        break

        if not evidence:
            return None

        # Build informative summary with isolated exception if found
        summary = (
            "The container is repeatedly crashing on startup or execution, causing Kubernetes "
            "to place it in CrashLoopBackOff state with exponential restart delay."
        )
        if isolated_root_cause:
            summary += f" Specific root failure identified: '{isolated_root_cause}'."

        remediation = [
            RemediationAction(
                phase="immediate",
                title="Inspect Previous Container Termination Logs",
                description="Fetch the crash logs from the previous instance of the container before it was restarted.",
                command="kubectl logs <pod-name> --previous -c <container-name>",
            ),
            RemediationAction(
                phase="immediate",
                title="Verify Environment Variables and ConfigMaps",
                description="Check if any required configuration secrets or environment variables are missing or misconfigured.",
                command="kubectl describe pod <pod-name> | grep -A 15 'Environment:'",
            ),
            RemediationAction(
                phase="preventative",
                title="Add Graceful Exception Handling and Validation",
                description="Ensure application entrypoint performs prerequisite checks and logs configuration errors cleanly before exiting.",
            ),
        ]

        return DiagnosticFinding(
            category="CrashLoopBackOff",
            title="Pod in CrashLoopBackOff Due to Application Process Crash",
            summary=summary,
            severity=SeverityLevel.CRITICAL,
            confidence=0.95,
            primary_evidence=evidence,
            contributing_factors=[
                "Application encountered an unhandled exception or missing configuration during startup",
                "Kubelet failed to keep container alive after repeated restart attempts",
            ],
            remediation_actions=remediation,
            affected_components=["Application Runtime", "Kubelet Restart Policy"],
        )
