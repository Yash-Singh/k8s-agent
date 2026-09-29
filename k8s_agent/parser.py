"""Log parsing and normalization for Kubernetes container logs, events, and stack traces."""

import json
import re
from typing import List, Optional
from k8s_agent.models import LogEntry

# Regex for CRI / Containerd format: "2026-09-28T18:24:01.123456789Z stderr F <message>"
CRI_REGEX = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\s+(stdout|stderr|system)\s+([FP]) (.*)$"
)

# Standard timestamp formats in logs
ISO_TIMESTAMP_REGEX = re.compile(
    r"^\[?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\]?"
)

# Syslog / Kernel timestamp: "Sep 28 18:24:01"
SYSLOG_TIMESTAMP_REGEX = re.compile(
    r"^([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
)

# Kubernetes Event pattern: "Warning  Unhealthy  pod/api-xxx  Liveness probe failed..."
K8S_EVENT_REGEX = re.compile(
    r"^(Normal|Warning)\s+([A-Za-z0-9_-]+)\s+([^\s]+)\s+(.*)$"
)

# Severity keywords
SEVERITY_PATTERNS = [
    (re.compile(r"\b(FATAL|PANIC|CRITICAL|EMERGENCY|SEVERE)\b", re.IGNORECASE), "FATAL"),
    (re.compile(r"\b(ERROR|ERR|FAILED|FAILURE|EXCEPTION)\b", re.IGNORECASE), "ERROR"),
    (re.compile(r"\b(WARN|WARNING)\b", re.IGNORECASE), "WARN"),
    (re.compile(r"\b(INFO|NOTICE)\b", re.IGNORECASE), "INFO"),
    (re.compile(r"\b(DEBUG|TRACE)\b", re.IGNORECASE), "DEBUG"),
]


def detect_severity(text: str, default: str = "INFO") -> str:
    """Detect log severity level from text."""
    for pattern, level in SEVERITY_PATTERNS:
        if pattern.search(text):
            return level
    return default


def parse_json_log(line: str, line_number: int) -> Optional[LogEntry]:
    """Attempt to parse a single line as JSON log."""
    stripped = line.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None

    try:
        data = json.loads(stripped)
        if not isinstance(data, dict):
            return None

        # Look for timestamp
        timestamp = (
            data.get("timestamp")
            or data.get("ts")
            or data.get("time")
            or data.get("@timestamp")
            or data.get("datetime")
        )
        if timestamp is not None:
            timestamp = str(timestamp)

        # Look for message
        message = (
            data.get("message")
            or data.get("msg")
            or data.get("log")
            or data.get("error")
            or data.get("event")
            or ""
        )
        if not message:
            message = json.dumps(data)

        level_raw = (
            data.get("level")
            or data.get("severity")
            or data.get("status")
            or data.get("log_level")
            or ""
        )
        level = detect_severity(str(level_raw), default="INFO") if level_raw else detect_severity(message, "INFO")
        stream = str(data.get("stream", "stdout")).lower()

        return LogEntry(
            line_number=line_number,
            timestamp=timestamp,
            level=level,
            stream=stream,
            message=str(message),
            raw=line,
            attributes=data,
        )
    except Exception:
        return None


def parse_cri_log(line: str, line_number: int) -> Optional[LogEntry]:
    """Parse containerd/CRI formatted log line."""
    match = CRI_REGEX.match(line.strip())
    if not match:
        return None

    ts, stream, tag, msg = match.groups()
    level = detect_severity(msg, default="INFO")
    return LogEntry(
        line_number=line_number,
        timestamp=ts,
        level=level,
        stream=stream,
        message=msg,
        raw=line,
        attributes={"tag": tag},
    )


def parse_k8s_event(line: str, line_number: int) -> Optional[LogEntry]:
    """Parse k8s event format: Warning FailedScheduling ..."""
    match = K8S_EVENT_REGEX.match(line.strip())
    if not match:
        return None

    event_type, reason, resource, msg = match.groups()
    level = "WARN" if event_type == "Warning" else "INFO"
    if any(k in reason.lower() for k in ["fail", "error", "kill", "unhealthy", "backoff"]):
        level = "ERROR" if event_type == "Warning" else "WARN"

    return LogEntry(
        line_number=line_number,
        timestamp=None,
        level=level,
        stream="system",
        message=f"[{event_type}] {reason} on {resource}: {msg}",
        raw=line,
        attributes={"event_type": event_type, "reason": reason, "resource": resource},
    )


def parse_plain_log(line: str, line_number: int) -> LogEntry:
    """Parse a plain text log line with timestamp and severity heuristics."""
    stripped = line.strip()

    ts_match = ISO_TIMESTAMP_REGEX.match(stripped)
    timestamp = None
    msg = stripped

    if ts_match:
        timestamp = ts_match.group(1)
        msg = stripped[ts_match.end():].strip()
    else:
        sys_match = SYSLOG_TIMESTAMP_REGEX.match(stripped)
        if sys_match:
            timestamp = sys_match.group(1)
            msg = stripped[sys_match.end():].strip()

    level = detect_severity(stripped, default="INFO")
    stream = "stderr" if level in ("ERROR", "FATAL") else "stdout"

    return LogEntry(
        line_number=line_number,
        timestamp=timestamp,
        level=level,
        stream=stream,
        message=msg if msg else stripped,
        raw=line,
        attributes={},
    )


def parse_line(line: str, line_num: int) -> LogEntry:
    """Parse a single line into a LogEntry using cascade of strategies."""
    parsed = parse_json_log(line, line_num)
    if parsed:
        return parsed
    parsed = parse_cri_log(line, line_num)
    if parsed:
        return parsed
    parsed = parse_k8s_event(line, line_num)
    if parsed:
        return parsed
    return parse_plain_log(line, line_num)


class LogParser:
    """Parser that ingests raw log stream, handles multi-line blocks, and returns normalized entries."""

    def __init__(self, group_stacktraces: bool = True):
        self.group_stacktraces = group_stacktraces

    def parse(self, raw_text: str) -> List[LogEntry]:
        """Parse raw text containing Kubernetes logs into structured LogEntry models."""
        raw_lines = raw_text.splitlines()
        entries: List[LogEntry] = []

        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            line_num = i + 1

            if not line.strip():
                i += 1
                continue

            entry = parse_line(line, line_num)

            # Check if this line starts a multi-line stack trace or exception block
            if self.group_stacktraces and self._is_stacktrace_start(entry.message):
                accumulated_msgs = [entry.message]
                accumulated_raws = [entry.raw]
                j = i + 1
                traceback_finished = False

                while j < len(raw_lines) and not traceback_finished:
                    next_entry = parse_line(raw_lines[j], j + 1)
                    if self._is_stacktrace_continuation(next_entry.message, raw_lines[j]):
                        accumulated_msgs.append(next_entry.message)
                        accumulated_raws.append(next_entry.raw)
                        # If this continuation is the final exception line like "KeyError: 'DATABASE_URL'"
                        if self._is_exception_terminal_line(next_entry.message):
                            traceback_finished = True
                        j += 1
                    else:
                        break

                if len(accumulated_msgs) > 1:
                    entry.message = "\n".join(accumulated_msgs)
                    entry.raw = "\n".join(accumulated_raws)
                    entry.level = "ERROR"
                    entry.stream = "stderr"
                    i = j - 1

            entries.append(entry)
            i += 1

        return entries

    def _is_stacktrace_start(self, text: str) -> bool:
        indicators = [
            "Traceback (most recent call last):",
            "panic: runtime error:",
            "goroutine ",
            "Exception in thread ",
            "FATAL EXCEPTION",
            "Uncaught Exception",
            "uncaughtException",
            "UnhandledPromiseRejection",
        ]
        return any(ind in text for ind in indicators)

    def _is_stacktrace_continuation(self, msg: str, raw_line: str) -> bool:
        stripped_msg = msg.strip()
        if not stripped_msg:
            return False

        # Python traceback frames or final error
        if msg.startswith("  ") or msg.startswith("\t"):
            return True
        if stripped_msg.startswith("File \"") or stripped_msg.startswith("raise "):
            return True
        if self._is_exception_terminal_line(stripped_msg):
            return True

        # Java stacktrace frames
        if stripped_msg.startswith("at ") or stripped_msg.startswith("Caused by:"):
            return True

        # Go goroutine lines
        if stripped_msg.startswith("/") or stripped_msg.startswith("created by "):
            return True

        return False

    def _is_exception_terminal_line(self, text: str) -> bool:
        stripped = text.strip()
        pattern = re.compile(
            r"^(?:[A-Za-z0-9_.]*(?:Error|Exception|Panic|Failure)|KeyError|ValueError|TypeError|AttributeError|ImportError|NameError|IndexError|OperationalError|TimeoutError):\s*.*"
        )
        return bool(pattern.match(stripped))
