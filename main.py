#!/usr/bin/env python3
# ruff: noqa: BLE001
"""Kubernetes Log Investigation Agent CLI.

Allows running investigations on Kubernetes logs from files, stdin, or raw text,
outputting visually stunning terminal reports, markdown, or JSON with supporting evidence.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from app.agent import root_agent

# Ensure environment variables (.env) are loaded
load_dotenv()

console = Console()


async def execute_agent_query(prompt_text: str, console_obj: Console) -> str:
    """Run a prompt through the Google ADK root_agent and return the text response."""
    session_service = InMemorySessionService()
    session = await session_service.create_session(user_id="sre_user", app_name="app")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="app")

    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])

    response_parts: list[str] = []
    with console_obj.status(
        "[bold cyan]Agent is investigating cluster and analyzing evidence...[/bold cyan]"
    ):
        async for event in runner.run_async(
            new_message=message, user_id="sre_user", session_id=session.id
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_parts.append(part.text)

    return "".join(response_parts)


def display_banner(console_obj: Console) -> None:
    """Display the CLI banner."""
    title = "[bold white]Kubernetes Investigation & SRE Agent[/bold white] ☸️ 🔍"
    subtitle = "[dim]Powered by Google ADK & Gemini[/dim]"
    panel = Panel(
        f"{title}\n{subtitle}\n\n[cyan]Commands:[/cyan] Type your query or issue to investigate, or [bold red]exit[/bold red] to quit.",
        box=box.ROUNDED,
        border_style="cyan",
    )
    console_obj.print(panel)


def format_and_output(
    report_text: str,
    output_format: str,
    output_path: Path | None,
    console_obj: Console,
) -> None:
    """Format the report and write to console and/or file."""
    if output_format == "json":
        json_output = json.dumps({"report": report_text}, indent=2)
        if output_path:
            output_path.write_text(json_output, encoding="utf-8")
            console_obj.print(f"[dim]JSON report written to {output_path}[/dim]")
        else:
            console_obj.print(json_output)
    elif output_format == "markdown":
        if output_path:
            output_path.write_text(report_text, encoding="utf-8")
            console_obj.print(f"[dim]Markdown report written to {output_path}[/dim]")
        else:
            print(report_text)
    else:  # 'rich' default terminal format
        console_obj.print()
        console_obj.print(
            Panel(
                Markdown(report_text.strip()),
                box=box.ROUNDED,
                border_style="cyan",
                padding=(1, 2),
            )
        )
        console_obj.print()
        if output_path:
            output_path.write_text(report_text, encoding="utf-8")
            console_obj.print(f"[dim]Report saved to {output_path}[/dim]")


async def interactive_loop(console_obj: Console) -> None:
    """Run an interactive REPL investigation loop."""
    display_banner(console_obj)
    while True:
        try:
            console_obj.print("[bold green]k8s-agent>[/bold green] ", end="")
            user_input = input().strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                console_obj.print(
                    "[yellow]Exiting investigation session. Goodbye![/yellow]"
                )
                break

            response = await execute_agent_query(user_input, console_obj)
            console_obj.print()
            console_obj.print(
                Panel(
                    Markdown(response.strip()),
                    box=box.ROUNDED,
                    border_style="cyan",
                    padding=(1, 2),
                )
            )
            console_obj.print()
        except (KeyboardInterrupt, EOFError):
            console_obj.print("\n[yellow]Session interrupted. Goodbye![/yellow]")
            break
        except Exception as err:
            console_obj.print(
                f"[bold red]Error running investigation: {err!s}[/bold red]"
            )


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Kubernetes Log Investigation Agent CLI (Powered by Google ADK)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode:
  python main.py

  # Direct investigation query:
  python main.py "Investigate pod nginx-b7b4d9b7d-zv7tg in namespace apps"

  # Direct pod investigation:
  python main.py --pod nginx-b7b4d9b7d-zv7tg -n apps

  # Piping logs from kubectl:
  kubectl logs my-pod --previous | python main.py

  # Piping events from kubectl:
  kubectl get events -n apps | python main.py

  # Analyze a log file and export Markdown report:
  python main.py --file crash.log --format markdown -o incident-report.md
        """,
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Investigation query or prompt (e.g. 'Investigate failing pods in apps namespace')",
    )
    parser.add_argument(
        "--pod",
        "-p",
        type=str,
        default="",
        help="Specific pod name to investigate",
    )
    parser.add_argument(
        "--namespace",
        "-n",
        type=str,
        default="default",
        help="Kubernetes namespace (default: 'default')",
    )
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        default=None,
        help="Log file path to ingest and analyze",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="File path to save the generated report",
    )
    parser.add_argument(
        "--format",
        choices=["rich", "markdown", "json"],
        default="rich",
        help="Output presentation format (default: 'rich')",
    )
    return parser.parse_args()


async def main_async() -> None:
    """Main async entry point."""
    args = parse_arguments()

    # Case 1: Piped stdin (e.g. kubectl logs ... | python main.py)
    if not sys.stdin.isatty():
        piped_content = sys.stdin.read().strip()
        if not piped_content:
            console.print(
                "[bold red]Error: Received empty input from stdin.[/bold red]"
            )
            sys.exit(1)

        query_text = (
            " ".join(args.query)
            if args.query
            else "Investigate the following Kubernetes logs/events, determine root cause, and provide a full incident report:"
        )
        full_prompt = f"{query_text}\n\n```text\n{piped_content}\n```"
        report = await execute_agent_query(full_prompt, console)
        format_and_output(report, args.format, args.output, console)
        return

    # Case 2: Reading from a specified log file
    if args.file:
        if not args.file.exists():
            console.print(
                f"[bold red]Error: Log file not found at '{args.file}'[/bold red]"
            )
            sys.exit(1)
        file_content = args.file.read_text(encoding="utf-8", errors="replace")
        query_text = (
            " ".join(args.query)
            if args.query
            else f"Investigate the Kubernetes logs from file '{args.file.name}', determine root cause, and provide a full SRE incident report:"
        )
        full_prompt = f"{query_text}\n\n```text\n{file_content}\n```"
        report = await execute_agent_query(full_prompt, console)
        format_and_output(report, args.format, args.output, console)
        return

    # Case 3: Investigating a specific pod
    if args.pod:
        ns = args.namespace or "default"
        full_prompt = (
            f"Investigate failing pod '{args.pod}' in namespace '{ns}'. "
            f"Check its lifecycle events, retrieve its logs (including previous crash logs if applicable), "
            f"and check the deployment rollout history to produce a complete SRE investigation report."
        )
        report = await execute_agent_query(full_prompt, console)
        format_and_output(report, args.format, args.output, console)
        return

    # Case 4: Query provided via positional arguments
    if args.query:
        query_str = " ".join(args.query)
        report = await execute_agent_query(query_str, console)
        format_and_output(report, args.format, args.output, console)
        return

    # Case 5: Interactive REPL session
    await interactive_loop(console)


def main() -> None:
    """CLI script entry point."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        console.print("\n[yellow]Process cancelled by user.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
