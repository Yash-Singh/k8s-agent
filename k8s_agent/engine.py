"""Investigation analysis engine combining heuristic rule evaluation and optional LLM synthesis."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from k8s_agent.detectors import BaseDetector, DiagnosticFinding, get_default_detectors
from k8s_agent.models import (
    EvidenceItem,
    InvestigationReport,
    InvestigationStats,
    LogEntry,
    RemediationAction,
    RootCause,
    SeverityLevel,
    TimelineEvent,
)


class HeuristicEngine:
    """Deterministic Kubernetes diagnostic engine with causal ranking and evidence extraction."""

    def __init__(self, detectors: Optional[List[BaseDetector]] = None):
        self.detectors = detectors or get_default_detectors()

    def analyze(self, entries: List[LogEntry]) -> InvestigationReport:
        now_str = datetime.now(timezone.utc).isoformat()
        inv_id = f"k8s-inv-{uuid.uuid4().hex[:8]}"

        # 1. Compute log metrics
        stats = self._compute_stats(entries)

        # 2. Extract timeline
        timeline = self._build_timeline(entries)

        # 3. Run all detectors to gather findings
        findings: List[DiagnosticFinding] = []
        for detector in self.detectors:
            finding = detector.detect(entries)
            if finding:
                findings.append(finding)

        # 4. If no specific signature matched, generate general anomaly diagnosis
        if not findings:
            return self._handle_unknown_anomaly(entries, stats, timeline, inv_id, now_str)

        # 5. Causal ranking: determine primary root cause vs secondary cascades
        primary, secondaries = self._rank_findings(findings)

        # Combine all primary evidence + secondary evidence
        combined_evidence = list(primary.primary_evidence)
        for sec in secondaries:
            for ev in sec.primary_evidence:
                if not any(e.line_number == ev.line_number for e in combined_evidence):
                    combined_evidence.append(ev)

        # Sort evidence chronologically by line number
        combined_evidence.sort(key=lambda x: x.line_number)

        # Consolidate contributing factors
        contributing = list(primary.contributing_factors)
        for sec in secondaries:
            contributing.append(f"Cascade effect: {sec.title}")

        # Consolidate remediation
        remediation = list(primary.remediation_actions)
        for sec in secondaries:
            for r in sec.remediation_actions:
                if not any(existing.title == r.title for existing in remediation):
                    remediation.append(r)

        root_cause = RootCause(
            category=primary.category,
            title=primary.title,
            summary=primary.summary,
            confidence_score=primary.confidence,
            affected_components=primary.affected_components,
        )

        summary = (
            f"Investigation identified {primary.title} with {int(primary.confidence * 100)}% confidence. "
            f"Analyzed {stats.total_lines_analyzed} log entries ({stats.error_count} errors, {stats.warning_count} warnings). "
            f"{len(combined_evidence)} critical evidence points were isolated."
        )

        impact_assessment = (
            f"Severity: {primary.severity.value}. Impacted components: {', '.join(primary.affected_components)}. "
            "Pod is unable to serve production traffic reliably or is caught in an automated restart cycle."
        )

        return InvestigationReport(
            investigation_id=inv_id,
            created_at=now_str,
            status="ROOT_CAUSE_IDENTIFIED",
            severity=primary.severity,
            summary=summary,
            root_cause=root_cause,
            contributing_factors=contributing,
            supporting_evidence=combined_evidence,
            timeline=timeline,
            impact_assessment=impact_assessment,
            remediation=remediation,
            stats=stats,
            analysis_engine="deterministic_expert",
        )

    def _compute_stats(self, entries: List[LogEntry]) -> InvestigationStats:
        total = len(entries)
        errors = sum(1 for e in entries if e.level in ("ERROR", "FATAL"))
        warnings = sum(1 for e in entries if e.level == "WARN")

        ts_start = None
        ts_end = None
        for e in entries:
            if e.timestamp:
                if not ts_start:
                    ts_start = e.timestamp
                ts_end = e.timestamp

        return InvestigationStats(
            total_lines_analyzed=total,
            error_count=errors,
            warning_count=warnings,
            timespan_start=ts_start,
            timespan_end=ts_end,
        )

    def _build_timeline(self, entries: List[LogEntry]) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        for e in entries:
            if e.level in ("FATAL", "ERROR", "WARN") or "kill" in e.message.lower() or "started" in e.message.lower():
                sev = SeverityLevel.CRITICAL if e.level == "FATAL" else (
                    SeverityLevel.HIGH if e.level == "ERROR" else SeverityLevel.MEDIUM
                )
                ts = e.timestamp or f"Line #{e.line_number}"
                # Truncate title
                first_line = e.message.strip().splitlines()[0]
                title = (first_line[:80] + "...") if len(first_line) > 80 else first_line
                events.append(
                    TimelineEvent(
                        timestamp=ts,
                        title=title,
                        description=first_line,
                        severity=sev,
                        line_number=e.line_number,
                    )
                )
                if len(events) >= 12:  # Cap timeline to avoid information overload
                    break
        return events

    def _rank_findings(self, findings: List[DiagnosticFinding]) -> Tuple[DiagnosticFinding, List[DiagnosticFinding]]:
        """Rank findings by root cause priority (e.g. underlying network/DB or OOM usually triggers probe/crashloop)."""
        priority_map = {
            "OOMKilled": 100,
            "NetworkDNS": 95,
            "RBAC": 90,
            "DiskPressure": 85,
            "ImagePullBackOff": 80,
            "CrashLoopBackOff": 70,
            "ProbeFailure": 60,
        }

        sorted_findings = sorted(
            findings,
            key=lambda f: (priority_map.get(f.category, 50), f.confidence),
            reverse=True,
        )
        primary = sorted_findings[0]
        secondaries = sorted_findings[1:]
        return primary, secondaries

    def _handle_unknown_anomaly(
        self,
        entries: List[LogEntry],
        stats: InvestigationStats,
        timeline: List[TimelineEvent],
        inv_id: str,
        now_str: str,
    ) -> InvestigationReport:
        # Check if there are error entries to extract as evidence
        error_entries = [e for e in entries if e.level in ("ERROR", "FATAL")]
        evidence = [
            EvidenceItem(
                line_number=e.line_number,
                timestamp=e.timestamp,
                log_snippet=e.message.strip(),
                relevance="Detected error level log entry in stream",
                category="Symptom",
            )
            for e in error_entries[:5]
        ]

        sev = SeverityLevel.HIGH if stats.error_count > 0 else (
            SeverityLevel.MEDIUM if stats.warning_count > 0 else SeverityLevel.INFO
        )

        root_cause = RootCause(
            category="GenericAnomaly",
            title="Unclassified Log Pattern or Application Degraded State",
            summary=(
                f"Identified {stats.error_count} error log events and {stats.warning_count} warnings, "
                "but no standard Kubernetes failure signature (e.g., OOMKilled, CrashLoopBackOff) was matched with high confidence."
            ),
            confidence_score=0.5 if stats.error_count > 0 else 0.2,
            affected_components=["Application Service"],
        )

        remediation = [
            RemediationAction(
                phase="diagnostic",
                title="Inspect Application Logs with Increased Verbosity",
                description="Enable DEBUG level logging to obtain more diagnostic traces.",
                command="kubectl logs <pod-name> --tail=200",
            ),
            RemediationAction(
                phase="diagnostic",
                title="Check Pod Events for Cluster Infrastructure Notifications",
                description="Fetch kubelet events associated with the pod.",
                command="kubectl describe pod <pod-name>",
            ),
        ]

        return InvestigationReport(
            investigation_id=inv_id,
            created_at=now_str,
            status="INCONCLUSIVE" if stats.error_count == 0 else "PARTIAL_ROOT_CAUSE",
            severity=sev,
            summary=f"Analyzed {stats.total_lines_analyzed} lines. {stats.error_count} errors and {stats.warning_count} warnings detected.",
            root_cause=root_cause,
            contributing_factors=["No fatal exit code or standard Kubernetes event signature was explicitly present."],
            supporting_evidence=evidence,
            timeline=timeline,
            impact_assessment=f"Pod logs contain {stats.error_count} errors requiring developer triage.",
            remediation=remediation,
            stats=stats,
            analysis_engine="deterministic_expert",
        )


class LLMEngine:
    """Optional LLM-augmented investigator for deep synthesis and context reasoning."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("sk-") and len(self.api_key) > 20)

    def enrich(self, report: InvestigationReport, entries: List[LogEntry]) -> InvestigationReport:
        """Enrich deterministic report using LLM if available, falling back gracefully."""
        if not self.is_available():
            return report

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)

            # Prepare distilled context
            evidence_context = "\n".join(
                f"[Line {ev.line_number}] ({ev.category}) {ev.log_snippet}"
                for ev in report.supporting_evidence[:15]
            )

            prompt = f"""You are an expert Kubernetes SRE and Principal Reliability Engineer.
Review the following Kubernetes investigation findings and supporting log evidence:

Root Cause Category: {report.root_cause.category}
Detected Title: {report.root_cause.title}
Confidence: {report.root_cause.confidence_score}
Supporting Evidence:
{evidence_context}

Please provide an enriched executive analysis in JSON format with exactly these fields:
{{
  "executive_summary": "1-2 concise, high-impact paragraphs explaining the exact chain of events and failure mechanism.",
  "impact_assessment": "Clear explanation of blast radius, traffic loss, and dependencies affected.",
  "additional_contributing_factors": ["list of secondary or architectural factors"],
  "refined_remediation": [
     {{
       "phase": "immediate" or "preventative" or "diagnostic",
       "title": "Short title",
       "description": "Clear instructions",
       "command": "Optional kubectl command or null"
     }}
  ]
}}
Respond with raw JSON only."""

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a Kubernetes diagnostic specialist. Output pure JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if content:
                data = json.loads(content)
                if "executive_summary" in data:
                    report.summary = data["executive_summary"]
                if "impact_assessment" in data:
                    report.impact_assessment = data["impact_assessment"]
                if "additional_contributing_factors" in data:
                    for factor in data["additional_contributing_factors"]:
                        if factor not in report.contributing_factors:
                            report.contributing_factors.append(factor)
                if "refined_remediation" in data and isinstance(data["refined_remediation"], list):
                    refined_actions = []
                    for r in data["refined_remediation"]:
                        refined_actions.append(
                            RemediationAction(
                                phase=r.get("phase", "immediate"),
                                title=r.get("title", ""),
                                description=r.get("description", ""),
                                command=r.get("command"),
                            )
                        )
                    if refined_actions:
                        report.remediation = refined_actions

                report.analysis_engine = "llm_augmented"

        except Exception:
            # Fallback cleanly to deterministic report if LLM fails
            pass

        return report
