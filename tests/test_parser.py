"""Unit tests for Kubernetes log parsing."""

import pytest
from k8s_agent.parser import LogParser, parse_line


def test_plain_log_parsing():
    raw = "2026-09-28 14:00:00 [ERROR] Database connection lost"
    entry = parse_line(raw, 1)
    assert entry.level == "ERROR"
    assert "Database connection lost" in entry.message
    assert entry.timestamp == "2026-09-28 14:00:00"
    assert entry.stream == "stderr"


def test_json_log_parsing():
    raw = '{"ts": "2026-09-28T14:00:00Z", "level": "warn", "msg": "Cache miss rate high", "service": "api"}'
    entry = parse_line(raw, 5)
    assert entry.level == "WARN"
    assert entry.message == "Cache miss rate high"
    assert entry.attributes.get("service") == "api"


def test_cri_log_parsing():
    raw = "2026-09-28T14:10:00.123456Z stderr F [ERROR] Process killed"
    entry = parse_line(raw, 10)
    assert entry.timestamp == "2026-09-28T14:10:00.123456Z"
    assert entry.stream == "stderr"
    assert entry.level == "ERROR"
    assert "[ERROR] Process killed" in entry.message


def test_k8s_event_parsing():
    raw = "Warning  Unhealthy  pod/web-app-123  Liveness probe failed: HTTP 500"
    entry = parse_line(raw, 15)
    assert entry.level == "ERROR"
    assert entry.stream == "system"
    assert "Liveness probe failed" in entry.message


def test_stacktrace_grouping():
    log_data = """2026-09-28T10:00:00Z stderr F Traceback (most recent call last):
2026-09-28T10:00:00Z stderr F   File "/app/main.py", line 12, in <module>
2026-09-28T10:00:00Z stderr F     run_server()
2026-09-28T10:00:00Z stderr F   File "/app/main.py", line 8, in run_server
2026-09-28T10:00:00Z stderr F     raise ConnectionError("Failed to reach redis")
2026-09-28T10:00:00Z stderr F ConnectionError: Failed to reach redis
2026-09-28T10:00:01Z system F command terminated with exit code 1"""

    parser = LogParser(group_stacktraces=True)
    entries = parser.parse(log_data)

    # Should group traceback into a single entry
    assert len(entries) == 2
    tb_entry = entries[0]
    assert "ConnectionError: Failed to reach redis" in tb_entry.message
    assert tb_entry.level == "ERROR"
    assert tb_entry.line_number == 1

    exit_entry = entries[1]
    assert "exit code 1" in exit_entry.message
