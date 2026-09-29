"""Formatting and report export utilities for terminal (Rich), Markdown, and JSON."""

import json
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.syntax import Syntax
from k8s_agent.models import InvestigationReport, SeverityLevel


def get_severity_style(severity: SeverityLevel) -> str:
    styles = {
        SeverityLevel.CRITICAL: "bold white on red",
        SeverityLevel.HIGH: "bold white on dark_orange",
        SeverityLevel.MEDIUM: "bold black on yellow",
        SeverityLevel.LOW: "bold white on blue",
        SeverityLevel.INFO: "bold white on green",
    }
    return styles.get(severity, "bold white on blue")


class ReportFormatter:
    """Renders investigation reports in various formats: Rich terminal, Markdown, or JSON."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def print_terminal(self, report: InvestigationReport) -> None:
        """Render beautiful, interactive terminal output using Rich."""
        c = self.console
        c.print()

        # 1. Header Banner
        sev_style = get_severity_style(report.severity)
        c.print(
            Panel(
                f"[bold cyan]Kubernetes Investigation Report[/bold cyan]  •  "
                f"[dim]ID: {report.investigation_id}[/dim]  •  "
                f"[dim]{report.created_at}[/dim]\n"
                f"Status: [bold green]{report.status}[/bold green]   |   "
                f"Engine: [italic]{report.analysis_engine}[/italic]",
                title=f"[{sev_style}] {report.severity.value} [/{sev_style}]",
                border_style="cyan",
            )
        )

        # 2. Executive Summary
        c.print(
            Panel(
                f"[white]{report.summary}[/white]\n\n"
                f"[bold yellow]Impact Assessment:[/bold yellow] [dim]{report.impact_assessment}[/dim]",
                title="[bold yellow]Executive Summary[/bold yellow]",
                border_style="yellow",
            )
        )

        # 3. Root Cause Diagnosis
        rc = report.root_cause
        conf_pct = int(rc.confidence_score * 100)
        conf_color = "green" if conf_pct >= 85 else ("yellow" if conf_pct >= 60 else "red")
        
        components_str = ", ".join(rc.affected_components) if rc.affected_components else "General"
        rc_content = (
            f"[bold underline]{rc.title}[/bold underline]\n"
            f"[dim]Category:[/dim] [cyan]{rc.category}[/cyan]  •  "
            f"[dim]Confidence:[/dim] [{conf_color}]{conf_pct}%[/{conf_color}]  •  "
            f"[dim]Components:[/dim] [magenta]{components_str}[/magenta]\n\n"
            f"{rc.summary}"
        )
        c.print(
            Panel(
                rc_content,
                title="[bold red]Primary Root Cause[/bold red]",
                border_style="red",
            )
        )

        # 4. Supporting Evidence
        if report.supporting_evidence:
            ev_table = Table(
                title="[bold cyan]Supporting Evidence (Extracted from Logs)[/bold cyan]",
                show_header=True,
                header_style="bold magenta",
                expand=True,
            )
            ev_table.add_column("Line", style="dim", width=8, justify="right")
            ev_table.add_column("Category", style="cyan", width=14)
            ev_table.add_column("Log Evidence Snippet", style="white", ratio=2)
            ev_table.add_column("Relevance & Diagnosis", style="yellow", ratio=2)

            for ev in report.supporting_evidence:
                ev_table.add_row(
                    f"#{ev.line_number}",
                    ev.category,
                    ev.log_snippet,
                    ev.relevance,
                )
            c.print(ev_table)
            c.print()

        # 5. Timeline of Events
        if report.timeline:
            tl_table = Table(
                title="[bold blue]Timeline of Events[/bold blue]",
                show_header=True,
                header_style="bold blue",
                expand=True,
            )
            tl_table.add_column("Time / Location", style="dim", width=22)
            tl_table.add_column("Severity", width=12)
            tl_table.add_column("Event Description", style="white")

            for t in report.timeline:
                tl_table.add_row(
                    t.timestamp,
                    f"[{get_severity_style(t.severity)}] {t.severity.value} [/]",
                    t.title,
                )
            c.print(tl_table)
            c.print()

        # 6. Remediation Actions
        if report.remediation:
            c.print("[bold green]Recommended Remediation Plan:[/bold green]")
            for i, rem in enumerate(report.remediation, 1):
                phase_badge = f"[bold cyan][{rem.phase.upper()}][/bold cyan]"
                c.print(f" {i}. {phase_badge} [bold]{rem.title}[/bold]: {rem.description}")
                if rem.command:
                    c.print("    [dim]$ Command:[/dim]")
                    c.print(f"    [green]{rem.command}[/green]")
                if rem.yaml_patch:
                    c.print("    [dim]YAML Patch Configuration:[/dim]")
                    c.print(Syntax(rem.yaml_patch, "yaml", theme="monokai", line_numbers=False, padding=(0, 4)))
            c.print()

        # 7. Summary Stats Footer
        stats = report.stats
        c.print(
            f"[dim]Analyzed {stats.total_lines_analyzed} log entries | "
            f"Errors: {stats.error_count} | Warnings: {stats.warning_count} | "
            f"Timespan: {stats.timespan_start or 'N/A'} -> {stats.timespan_end or 'N/A'}[/dim]\n"
        )

    def to_markdown(self, report: InvestigationReport) -> str:
        """Render report as formatted Markdown."""
        lines = []
        lines.append(f"# Kubernetes Investigation Report: {report.root_cause.title}")
        lines.append(f"**Investigation ID**: `{report.investigation_id}`  ")
        lines.append(f"**Created At**: `{report.created_at}`  ")
        lines.append(f"**Severity**: **{report.severity.value}**  ")
        lines.append(f"**Status**: `{report.status}`  ")
        lines.append(f"**Analysis Engine**: `{report.analysis_engine}`  \n")

        lines.append("## Executive Summary")
        lines.append(report.summary)
        lines.append("")
        lines.append(f"> **Impact Assessment**: {report.impact_assessment}\n")

        lines.append("## Root Cause Diagnosis")
        lines.append(f"### {report.root_cause.title}")
        lines.append(f"- **Category**: `{report.root_cause.category}`")
        lines.append(f"- **Confidence Score**: `{int(report.root_cause.confidence_score * 100)}%`")
        lines.append(f"- **Affected Components**: {', '.join(report.root_cause.affected_components)}")
        lines.append("")
        lines.append(report.root_cause.summary)
        lines.append("")

        if report.contributing_factors:
            lines.append("### Contributing Factors")
            for factor in report.contributing_factors:
                lines.append(f"- {factor}")
            lines.append("")

        if report.supporting_evidence:
            lines.append("## Supporting Evidence")
            lines.append("| Line | Category | Log Snippet | Relevance & SRE Diagnosis |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for ev in report.supporting_evidence:
                snippet = ev.log_snippet.replace("|", "\\|").replace("\n", " ")
                rel = ev.relevance.replace("|", "\\|")
                lines.append(f"| #{ev.line_number} | {ev.category} | `{snippet}` | {rel} |")
            lines.append("")

        if report.timeline:
            lines.append("## Timeline of Events")
            lines.append("| Time / Line | Severity | Event |")
            lines.append("| :--- | :--- | :--- |")
            for t in report.timeline:
                title = t.title.replace("|", "\\|")
                lines.append(f"| {t.timestamp} | {t.severity.value} | {title} |")
            lines.append("")

        if report.remediation:
            lines.append("## Remediation Plan")
            for i, r in enumerate(report.remediation, 1):
                lines.append(f"### {i}. [{r.phase.upper()}] {r.title}")
                lines.append(r.description)
                lines.append("")
                if r.command:
                    lines.append(f"```bash\n{r.command}\n```\n")
                if r.yaml_patch:
                    lines.append(f"```yaml\n{r.yaml_patch}\n```\n")

        lines.append("## Investigation Metrics")
        stats = report.stats
        lines.append(f"- **Total Lines Analyzed**: {stats.total_lines_analyzed}")
        lines.append(f"- **Error Count**: {stats.error_count}")
        lines.append(f"- **Warning Count**: {stats.warning_count}")
        lines.append(f"- **Timespan**: {stats.timespan_start or 'N/A'} — {stats.timespan_end or 'N/A'}")
        lines.append("")

        return "\n".join(lines)

    def to_json(self, report: InvestigationReport) -> str:
        """Render report as structured JSON."""
        return report.model_dump_json(indent=2)
