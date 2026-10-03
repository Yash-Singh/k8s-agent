# Kubernetes Investigation & SRE Agent ☸️🔍

An autonomous Kubernetes Site Reliability Engineering (SRE) and cluster troubleshooting agent built with the **Google Agent Development Kit (ADK)** and **Gemini**. The agent connects to Kubernetes clusters, investigates crashing pods, inspects cluster lifecycle events, analyzes rollout revisions, and produces structured post-investigation SRE incident reports.

---

## 🏛️ Project Anatomy

This project follows the official Google ADK and `agents-cli` standard directory anatomy:

```text
k8s-agent/
├── agents-cli-manifest.yaml   # agents-cli project specification
├── app/
│   ├── __init__.py
│   ├── agent.py               # ADK root_agent definition, prompt & model configuration
│   ├── tools.py               # Kubernetes inspection tools using official client
│   ├── fast_api_app.py        # FastAPI server hosting ADK SSE & A2A protocol endpoints
│   └── app_utils/             # Session services and A2A helpers
├── tests/
│   ├── unit/                  # Unit tests for tools and logic
│   │   ├── test_k8s_tools.py  # Mock tests for all Kubernetes tools
│   │   └── test_dummy.py
│   ├── integration/           # E2E server and A2A integration tests
│   │   ├── test_adk_agent.py  # Agent streaming test
│   │   └── test_server_e2e.py # FastAPI / A2A RPC endpoint tests
│   └── eval/                  # Quality evaluation datasets and metrics
│       ├── datasets/          # Multi-turn and single-turn evaluation datasets
│       ├── eval_config.yaml   # LLM-as-judge evaluation configuration
│       └── response_quality.py# Response quality judge metric
├── pyproject.toml             # Project dependencies and packaging
├── GEMINI.md                  # Development guide & coding agent rules
└── README.md
```

---

## 🛠️ Kubernetes Tools (`app/tools.py`)

The agent is equipped with native tools powered by the official Python Kubernetes Client library (`kubernetes`):

- **`inspect_kubernetes_pods`**: Inspects pods across namespaces or filters by name, displaying ready counts, phases, restart counts, and pod IPs.
- **`check_kubernetes_deployments`**: Lists deployments with replica counts, available pods, and up-to-date status.
- **`get_pod_events`**: Fetches and sorts lifecycle events (e.g. `BackOff`, `ImagePullBackOff`, `OOMKilling`, `Unhealthy`) with event counts and timestamps.
- **`get_pod_logs`**: Retrieves runtime logs with customizable tail lines and supports fetching logs from previously terminated/crashed containers (`previous=True`).
- **`get_deployment_history`**: Examines deployment rollout revisions (ReplicaSets) and automatically detects container image updates or configuration differences between revisions.

Both in-cluster configuration (`load_incluster_config`) for deployed pods/services and local workstation kubeconfig (`load_kube_config`) are supported out-of-the-box.

---

## 🚀 Quickstart & Development

### 1. Prerequisites

Install the `google-agents-cli` and `uv`:

```bash
uv tool install google-agents-cli
uv sync
```

### 2. Interactive Testing (Playground)

Launch the interactive web UI to test and converse with the agent:

```bash
agents-cli playground
```

Or run a single prompt directly from the terminal:

```bash
agents-cli run "Inspect the pods in the default namespace and report any failures"
```

### 3. Run the FastAPI Server (Local & A2A Protocol)

Start the local server hosting ADK SSE and A2A agent-to-agent communication:

```bash
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🧪 Testing & Evaluation

### Unit Tests
Run the unit test suite verifying Kubernetes tools:

```bash
uv run pytest tests/unit
```

### Integration Tests
Run end-to-end tests for the FastAPI server and A2A streaming:

```bash
uv run pytest tests/integration
```

### Quality Evaluation Flywheel
Run the LLM-as-judge evaluation suite across your test dataset:

```bash
agents-cli eval run
```

---

## 📋 Incident Report Output Format

When investigating failures, the agent synthesizes findings into a standardized SRE Investigation Report:

1. **Incident Overview**: Key metadata table (resource, namespace, severity badge, status phase, active image).
2. **Executive Summary & Impact**: Concise incident summary and availability impact assessment.
3. **Root Cause Analysis (RCA)**: Explicit failure category, confidence score, and technical diagnosis.
4. **Supporting Evidence Table**: Verbatim events and logs with line numbers and diagnostic significance.
5. **Rollout & Version History**: Deployment revision tracking and detected image tag differences.
6. **Remediation Plan**: Numbered, copy-pasteable commands for immediate fix, status verification, and long-term prevention.
