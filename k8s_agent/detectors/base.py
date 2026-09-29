"""Base class and common types for Kubernetes anomaly detectors."""

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field
from k8s_agent.models import EvidenceItem, LogEntry, RemediationAction, SeverityLevel


class DiagnosticFinding(BaseModel):
    """Result of an individual detector analyzing the log stream."""
    category: str
    title: str
    summary: str
    severity: SeverityLevel
    confidence: float = Field(ge=0.0, le=1.0)
    primary_evidence: List[EvidenceItem] = Field(default_factory=list)
    contributing_factors: List[str] = Field(default_factory=list)
    remediation_actions: List[RemediationAction] = Field(default_factory=list)
    affected_components: List[str] = Field(default_factory=list)


class BaseDetector(ABC):
    """Abstract base class for domain-specific Kubernetes log detectors."""

    @abstractmethod
    def detect(self, entries: List[LogEntry]) -> Optional[DiagnosticFinding]:
        """Analyze log entries and return a DiagnosticFinding if the failure pattern matches."""
        pass
