"""Unit tests for the top-level K8sInvestigationAgent orchestrator."""

from pathlib import Path
from k8s_agent.agent import K8sInvestigationAgent
from k8s_agent.models import SeverityLevel
from k8s_agent.samples import get_sample_log


def test_agent_investigate_text():
    sample_text = get_sample_log("oom_killed")
    agent = K8sInvestigationAgent(offline=True)
    report = agent.investigate(sample_text)

    assert report is not None
    assert report.status == "ROOT_CAUSE_IDENTIFIED"
    assert report.severity == SeverityLevel.CRITICAL
    assert report.root_cause.category == "OOMKilled"
    assert report.root_cause.confidence_score >= 0.95
    assert len(report.supporting_evidence) > 0
    assert len(report.remediation) > 0
    assert report.stats.total_lines_analyzed > 0


def test_agent_investigate_file(tmp_path: Path):
    log_file = tmp_path / "test_app.log"
    log_file.write_text("""
2026-09-28T10:00:00Z stdout F Starting payment API
2026-09-28T10:00:01Z stderr F Traceback (most recent call last):
2026-09-28T10:00:01Z stderr F   File "/app/server.py", line 10, in <module>
2026-09-28T10:00:01Z stderr F KeyError: 'DATABASE_URL'
2026-09-28T10:00:02Z system F command terminated with exit code 1
2026-09-28T10:00:10Z system F Warning BackOff pod/payment CrashLoopBackOff
""", encoding="utf-8")

    agent = K8sInvestigationAgent(offline=True)
    report = agent.investigate(log_file)

    assert report.root_cause.category == "CrashLoopBackOff"
    assert any("KeyError: 'DATABASE_URL'" in ev.log_snippet for ev in report.supporting_evidence)


def test_agent_unknown_log():
    normal_logs = """
2026-09-28 10:00:00 [INFO] User logged in: user_id=123
2026-09-28 10:00:01 [INFO] Page requested: /dashboard
2026-09-28 10:00:02 [INFO] Response status 200 in 12ms
"""
    agent = K8sInvestigationAgent(offline=True)
    report = agent.investigate(normal_logs)

    assert report.status in ("INCONCLUSIVE", "PARTIAL_ROOT_CAUSE")
    assert report.severity == SeverityLevel.INFO
    assert report.stats.error_count == 0
