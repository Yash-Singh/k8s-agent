"""Data models for Kubernetes Investigation Agent."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class LogEntry(BaseModel):
    """Normalized log line from a Kubernetes pod/container."""
    line_number: int
    timestamp: Optional[str] = None
    level: str = "INFO"
    stream: str = "stdout"  # stdout, stderr, or system
    message: str
    raw: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    """Specific piece of log evidence supporting the investigation diagnosis."""
    line_number: int
    timestamp: Optional[str] = None
    log_snippet: str
    relevance: str
    category: str = "Symptom"  # Root Trigger, Fatal Event, Symptom, Context


class TimelineEvent(BaseModel):
    """Key event along the failure timeline."""
    timestamp: str
    title: str
    description: str
    severity: SeverityLevel = SeverityLevel.INFO
    line_number: Optional[int] = None


class RootCause(BaseModel):
    """Detailed root cause diagnosis."""
    category: str
    title: str
    summary: str
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence between 0.0 and 1.0")
    affected_components: List[str] = Field(default_factory=list)


class RemediationAction(BaseModel):
    """Prescriptive remediation step to resolve or prevent the issue."""
    phase: str  # "immediate", "preventative", "diagnostic"
    title: str
    description: str
    command: Optional[str] = None
    yaml_patch: Optional[str] = None


class InvestigationStats(BaseModel):
    """Log metrics and statistics analyzed during investigation."""
    total_lines_analyzed: int = 0
    error_count: int = 0
    warning_count: int = 0
    timespan_start: Optional[str] = None
    timespan_end: Optional[str] = None


class InvestigationReport(BaseModel):
    """Comprehensive post-investigation report with supporting evidence."""
    investigation_id: str
    created_at: str
    status: str = "ROOT_CAUSE_IDENTIFIED"
    severity: SeverityLevel
    summary: str
    root_cause: RootCause
    contributing_factors: List[str] = Field(default_factory=list)
    supporting_evidence: List[EvidenceItem] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    impact_assessment: str
    remediation: List[RemediationAction] = Field(default_factory=list)
    stats: InvestigationStats = Field(default_factory=InvestigationStats)
    analysis_engine: str = "deterministic_expert"
