"""Main Kubernetes Investigation Agent orchestrator."""

import os
from pathlib import Path
from typing import Optional, Union, TextIO
from k8s_agent.engine import HeuristicEngine, LLMEngine
from k8s_agent.models import InvestigationReport
from k8s_agent.parser import LogParser


class K8sInvestigationAgent:
    """Intelligent Kubernetes Investigation Agent that analyzes logs to perform root-cause diagnosis

    and produces detailed post-investigation analysis with supporting evidence.
    """

    def __init__(
        self,
        offline: bool = False,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        group_stacktraces: bool = True,
    ):
        self.offline = offline
        self.parser = LogParser(group_stacktraces=group_stacktraces)
        self.heuristic_engine = HeuristicEngine()
        self.llm_engine = LLMEngine(api_key=api_key, model=model)

    def investigate(self, log_input: Union[str, Path, TextIO]) -> InvestigationReport:
        """Run investigation on the provided log input.

        Args:
            log_input: Raw log text string, a Path to a log file, or an open file-like object.

        Returns:
            InvestigationReport: Detailed analysis with root cause, timeline, supporting evidence,
                                and remediation plan.
        """
        # Ingest text
        if hasattr(log_input, "read"):
            raw_text = log_input.read()
        elif isinstance(log_input, (str, Path)) and os.path.exists(str(log_input)):
            with open(log_input, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
        elif isinstance(log_input, str):
            raw_text = log_input
        else:
            raise ValueError(f"Unsupported log input type: {type(log_input)}")

        # 1. Parse and normalize log entries
        entries = self.parser.parse(raw_text)

        # 2. Perform heuristic expert investigation and causal ranking
        report = self.heuristic_engine.analyze(entries)

        # 3. If online and LLM configured, enrich analysis
        if not self.offline and self.llm_engine.is_available():
            report = self.llm_engine.enrich(report, entries)

        return report
