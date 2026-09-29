"""CLI entry point for the Kubernetes Investigation Agent."""

import sys
from pathlib import Path
from typing import Optional
import click
from rich.console import Console

from k8s_agent.agent import K8sInvestigationAgent
from k8s_agent.formatter import ReportFormatter
from k8s_agent.samples import get_available_samples, get_sample_log

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version="0.1.0", prog_name="k8s-agent")
def main(ctx: click.Context):
    """Kubernetes Investigation Agent: Analyzes container & cluster logs to diagnose root causes."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command(name="investigate")
@click.argument("log_source", required=False, default="-")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["rich", "markdown", "json"], case_sensitive=False),
    default="rich",
    help="Output presentation format.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(writable=True, path_type=Path),
    default=None,
    help="Write report output to specified file.",
)
@click.option(
    "--offline",
    is_flag=True,
    default=False,
    help="Force offline deterministic expert analysis (disables external LLM calls).",
)
@click.option(
    "--api-key",
    envvar="OPENAI_API_KEY",
    default=None,
    help="OpenAI API key for LLM-augmented synthesis (or OPENAI_API_KEY env var).",
)
@click.option(
    "--model",
    default="gpt-4o-mini",
    help="LLM model name to use when LLM synthesis is enabled.",
)
def investigate_cmd(
    log_source: str,
    output_format: str,
    output: Optional[Path],
    offline: bool,
    api_key: Optional[str],
    model: str,
):
    """Investigate Kubernetes logs from a file, URL, or standard input (pipe).

    \b
    Examples:
      k8s-agent investigate /path/to/pod.log
      kubectl logs my-pod --previous | k8s-agent investigate
      k8s-agent investigate /path/to/pod.log --format markdown -o report.md
    """
    # Read log content
    if log_source == "-" or not log_source:
        if sys.stdin.isatty():
            console.print("[bold yellow]Waiting for logs from stdin (press Ctrl+D when finished, or pipe logs)...[/bold yellow]")
        raw_text = sys.stdin.read()
    else:
        path = Path(log_source)
        if not path.exists():
            console.print(f"[bold red]Error: Log file not found at '{path}'[/bold red]")
            sys.exit(1)
        raw_text = path.read_text(encoding="utf-8", errors="replace")

    if not raw_text.strip():
        console.print("[bold red]Error: Provided log input is empty.[/bold red]")
        sys.exit(1)

    agent = K8sInvestigationAgent(offline=offline, api_key=api_key, model=model)
    formatter = ReportFormatter(console=console)

    with console.status("[bold cyan]Investigating Kubernetes logs and isolating evidence...[/bold cyan]"):
        report = agent.investigate(raw_text)

    # Render output
    if output_format.lower() == "rich":
        formatter.print_terminal(report)
        if output:
            output.write_text(formatter.to_markdown(report), encoding="utf-8")
            console.print(f"[dim]Report saved to: {output}[/dim]")
    elif output_format.lower() == "markdown":
        md = formatter.to_markdown(report)
        if output:
            output.write_text(md, encoding="utf-8")
            console.print(f"[dim]Markdown report saved to: {output}[/dim]")
        else:
            click.echo(md)
    elif output_format.lower() == "json":
        js = formatter.to_json(report)
        if output:
            output.write_text(js, encoding="utf-8")
            console.print(f"[dim]JSON report saved to: {output}[/dim]")
        else:
            click.echo(js)


@main.command(name="demo")
@click.argument("sample_name", default="oom_killed")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["rich", "markdown", "json"], case_sensitive=False),
    default="rich",
    help="Output presentation format.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(writable=True, path_type=Path),
    default=None,
    help="Write report output to specified file.",
)
def demo_cmd(sample_name: str, output_format: str, output: Optional[Path]):
    """Run an automated investigation on a built-in realistic failure scenario.

    \b
    Examples:
      k8s-agent demo oom_killed
      k8s-agent demo crash_loop
      k8s-agent demo probe_timeout
    """
    try:
        raw_text = get_sample_log(sample_name)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        sys.exit(1)

    agent = K8sInvestigationAgent(offline=True)
    formatter = ReportFormatter(console=console)

    with console.status(f"[bold cyan]Running demonstration investigation on sample '{sample_name}'...[/bold cyan]"):
        report = agent.investigate(raw_text)

    if output_format.lower() == "rich":
        formatter.print_terminal(report)
        if output:
            output.write_text(formatter.to_markdown(report), encoding="utf-8")
            console.print(f"[dim]Report saved to: {output}[/dim]")
    elif output_format.lower() == "markdown":
        md = formatter.to_markdown(report)
        if output:
            output.write_text(md, encoding="utf-8")
            console.print(f"[dim]Markdown report saved to: {output}[/dim]")
        else:
            click.echo(md)
    elif output_format.lower() == "json":
        js = formatter.to_json(report)
        if output:
            output.write_text(js, encoding="utf-8")
            console.print(f"[dim]JSON report saved to: {output}[/dim]")
        else:
            click.echo(js)


@main.command(name="list-samples")
def list_samples_cmd():
    """List available built-in demonstration failure scenarios."""
    samples = get_available_samples()
    console.print("\n[bold cyan]Available Built-in Kubernetes Failure Scenarios:[/bold cyan]")
    descriptions = {
        "oom_killed": "Process terminated by Linux OOM killer with Exit Code 137 due to cgroup limit",
        "crash_loop": "Application startup crash with unhandled Python KeyError traceback and CrashLoopBackOff",
        "image_pull_error": "Private registry authentication 401 Unauthorized resulting in ErrImagePull",
        "probe_timeout": "Slow initialization causing Liveness/Readiness probe timeouts and pod termination",
        "dns_failure": "Cluster CoreDNS resolution timeout and upstream connection refused",
        "disk_pressure": "Storage volume capacity exhausted (ENOSPC) and node disk pressure eviction",
    }
    for name in sorted(samples.keys()):
        desc = descriptions.get(name, "Log sample")
        console.print(f"  • [bold green]{name:18}[/bold green] [dim]- {desc}[/dim]")
    console.print("\n[dim]Run: k8s-agent demo <sample_name>[/dim]\n")


if __name__ == "__main__":
    main()
