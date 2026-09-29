"""Unit tests for the CLI commands."""

import json
from pathlib import Path
from click.testing import CliRunner
from k8s_agent.cli import main


def test_cli_list_samples():
    runner = CliRunner()
    result = runner.invoke(main, ["list-samples"])
    assert result.exit_code == 0
    assert "oom_killed" in result.output
    assert "crash_loop" in result.output
    assert "dns_failure" in result.output


def test_cli_demo_oom_killed():
    runner = CliRunner()
    result = runner.invoke(main, ["demo", "oom_killed"])
    assert result.exit_code == 0
    assert "OOMKilled" in result.output
    assert "Supporting Evidence" in result.output


def test_cli_demo_markdown_output(tmp_path: Path):
    out_file = tmp_path / "report.md"
    runner = CliRunner()
    result = runner.invoke(main, ["demo", "crash_loop", "--format", "markdown", "-o", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "# Kubernetes Investigation Report" in content
    assert "CrashLoopBackOff" in content
    assert "DATABASE_URL" in content


def test_cli_demo_json_output(tmp_path: Path):
    out_file = tmp_path / "report.json"
    runner = CliRunner()
    result = runner.invoke(main, ["demo", "probe_timeout", "--format", "json", "-o", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["status"] == "ROOT_CAUSE_IDENTIFIED"
    assert data["root_cause"]["category"] == "ProbeFailure"
    assert len(data["supporting_evidence"]) > 0


def test_cli_investigate_pipe():
    runner = CliRunner()
    log_input = """
2026-09-28T08:00:00Z system F Warning Failed pod/vault-1 Error: ImagePullBackOff
2026-09-28T08:00:00Z system F Warning Failed pod/vault-1 Failed to pull image: 401 Unauthorized
"""
    result = runner.invoke(main, ["investigate", "--offline", "--format", "json"], input=log_input)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["root_cause"]["category"] == "ImagePullBackOff"
    assert len(data["supporting_evidence"]) > 0
