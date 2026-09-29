# Kubernetes Investigation Agent 🔍

An intelligent, production-ready Kubernetes investigation agent in Python that takes container, pod, and cluster logs as input, performs deep root-cause diagnosis, and provides a structured post-investigation analysis with verbatim supporting evidence, incident timelines, and actionable remediation steps.

---

## ✨ Features

- **Multi-Format Log Ingestion**:
  - Container runtime logs (CRI-O / Containerd standard format: `<ts> <stream> <F|P> <msg>`).
  - Structured JSON logs (Zap, Bunyan, Winston, Logrus, Python Structlog).
  - Standard RFC3339 / ISO-8601 plain text logs.
  - Kubernetes cluster events (`kubectl get events`, warning/normal notifications).
  - Multi-line stack trace grouping (Python `Tracebacks`, Go `panics`, Java `Exceptions`, Node.js unhandled rejections).

- **Domain-Specific Failure Detectors**:
  - **`OOMKilled`**: Linux kernel OOM killer, cgroup memory exhaustion, Java heap space, Exit Code 137.
  - **`CrashLoopBackOff`**: Application runtime crashes, syntax errors, missing environment variables (`KeyError`), fatal exit codes (1, 134 SIGABRT, 139 SIGSEGV).
  - **`ProbeFailure`**: Liveness probe timeouts (killing container) vs. Readiness probe failures (removing from endpoints) vs. Startup probe grace limits.
  - **`NetworkDNS`**: Cluster CoreDNS failures (`SERVFAIL`, `NXDOMAIN`), internal/external DNS resolution timeouts, TCP connection refused.
  - **`ImagePullBackOff`**: Container registry 401 Unauthorized / missing `imagePullSecrets`, manifest unknown, tag typos, CRI unpack failures.
  - **`DiskPressure`**: Volume capacity exhausted (`ENOSPC`), read-only filesystem remounts, node disk pressure evictions.
  - **`RBAC`**: Kubernetes API 403 Forbidden errors, missing ServiceAccount Role/ClusterRole bindings.

- **Post-Investigation Output with Verbatim Evidence**:
  - **Executive Summary**: Clear incident narrative and blast radius evaluation.
  - **Primary Root Cause**: Root cause category, title, confidence rating (e.g. 98%), and impacted components.
  - **Supporting Evidence Table**: Exact line numbers, timestamp, raw log snippet, and diagnostic explanation of why it proves the failure.
  - **Chronological Timeline**: Step-by-step cascade from first warning to fatal crash.
  - **Actionable Remediation**: Phase-based fixes (immediate mitigation commands, copy-paste YAML patches, and long-term preventative measures).

- **Dual Engine (Deterministic Expert + Optional LLM Synthesis)**:
  - **Offline Expert Engine**: Works completely offline out-of-the-box with zero API keys or external dependencies.
  - **LLM Synthesis (Optional)**: Automatically enriches findings using an LLM (e.g. OpenAI GPT-4o-mini) when `OPENAI_API_KEY` is provided.

- **Multiple Presentation Modes**:
  - Terminal interactive output with Rich panels, colored severity badges, and syntax-highlighted YAML.
  - GitHub-flavored Markdown reports (`--format markdown`, `--output report.md`).
  - Machine-readable JSON output (`--format json`, `--output report.json`) for CI/CD pipelines and webhooks.

---

## 🚀 Quickstart

### 1. Installation

```bash
git clone https://github.com/example/k8s-agent.git
cd k8s-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Run a Demonstration

The agent includes built-in realistic failure scenarios:

```bash
# List available sample scenarios
k8s-agent list-samples

# Investigate an OOMKilled scenario
k8s-agent demo oom_killed

# Investigate a CrashLoopBackOff scenario
k8s-agent demo crash_loop

# Investigate a CoreDNS failure scenario
k8s-agent demo dns_failure
```

### 3. Investigate Live Kubernetes Logs

Piping live logs directly from `kubectl`:

```bash
# Analyze a crashing pod's previous logs
kubectl logs <pod-name> --previous | k8s-agent investigate

# Analyze logs from a file and export a Markdown report
k8s-agent investigate /path/to/pod.log --format markdown --output incident-report.md

# Generate JSON for automated CI/CD pipeline verification
kubectl logs deployment/my-service --tail=500 | k8s-agent investigate --format json
```

---

## 🐍 Python API Usage

You can embed the investigation agent directly into your own Python applications, SRE bots, or Slack/Discord integrations:

```python
from k8s_agent import K8sInvestigationAgent, ReportFormatter

# Initialize the agent
agent = K8sInvestigationAgent(offline=True)

# Raw log string, file path, or stream
log_content = """
2026-09-28T14:10:45Z stdout F [WARN] High memory watermark reached: current=480MB, threshold=512MB
2026-09-28T14:11:02Z stderr F [ERROR] java.lang.OutOfMemoryError: Java heap space
2026-09-28T14:11:03Z system F Warning OOMKilled pod/worker-1 Memory cgroup out of memory: Container worker terminated with exit code 137
"""

# Perform investigation
report = agent.investigate(log_content)

# Access structured findings
print(f"Status: {report.status}")
print(f"Severity: {report.severity.value}")
print(f"Root Cause: {report.root_cause.title} ({int(report.root_cause.confidence_score * 100)}% confidence)")

# Inspect supporting evidence
for evidence in report.supporting_evidence:
    print(f"[Line #{evidence.line_number}] {evidence.category}: {evidence.log_snippet}")
    print(f"  ↳ Diagnostic Relevance: {evidence.relevance}")

# Render to Markdown or print to terminal
formatter = ReportFormatter()
formatter.print_terminal(report)
markdown_text = formatter.to_markdown(report)
```

---

## 📊 Architecture

```
                       ┌────────────────────────┐
                       │  Log Stream / Input   │
                       │ (kubectl / file / pipe)│
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │       LogParser        │
                       │ CRI / JSON / Plain /   │
                       │  Stacktrace Grouping   │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │ Anomaly Detectors      │
                       │ • OOMDetector          │
                       │ • CrashLoopDetector    │
                       │ • ProbeDetector        │
                       │ • NetworkDNSDetector   │
                       │ • ImagePullDetector    │
                       │ • StorageDetector      │
                       │ • RBACDetector         │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │    HeuristicEngine     │
                       │  • Causal Ranking      │
                       │  • Evidence Extraction │
                       │  • Timeline Synthesis  │
                       └───────────┬────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │ (Optional LLM Enrichment)   │
                    ▼                             ▼
       ┌────────────────────────┐    ┌────────────────────────┐
       │     Offline Report     │    │  LLM-Augmented Report  │
       └────────────┬───────────┘    └────────────┬───────────┘
                    │                             │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │    ReportFormatter     │
                       │ Rich CLI / MD / JSON   │
                       └────────────────────────┘
```

---

## 🧪 Running Tests

The test suite covers log parsing, detector accuracy, causal ranking, and CLI commands:

```bash
pytest -v
```
