"""CLI for workout replay test harness.

Commands:
  replay     - Replay a captured session and show diffs
  sessions  - List available capture sessions
  health    - Show pipeline health report
  trends    - Show corruption trends over time
  breakdown - Show corruption breakdown by type/source/device
  viewer    - Start trace viewer web server
"""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from .replay import (
    replay_session,
    get_device_path_diffs,
    load_session,
    DEFAULT_PIPELINE_STAGES,
)
from .analytics.health import health_report, print_health_table
from .analytics.breakdown import breakdown_report, print_breakdown_tables
from .analytics.trends import trend_report, print_trend_table


console = Console()


@click.group()
@click.option(
    "--capture-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="./captures",
    help="Directory containing captured sessions",
)
@click.pass_context
def main(ctx, capture_dir: Path):
    """Workout Replay Test Harness - Data Integrity Debugging Tool."""
    ctx.ensure_object(dict)
    ctx.obj["capture_dir"] = capture_dir


@main.command("sessions")
@click.option(
    "--capture-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="./captures",
    help="Directory containing captured sessions",
)
def list_sessions(capture_dir: Path):
    """List all available capture sessions."""
    if not capture_dir.exists():
        console.print("[yellow]No capture directory found.[/yellow]")
        return
    
    sessions = [d.name for d in capture_dir.iterdir() if d.is_dir()]
    
    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        return
    
    table = Table(title="Capture Sessions")
    table.add_column("Session Name", style="cyan")
    table.add_column("Snapshots", justify="right", style="green")
    table.add_column("First Capture", style="blue")
    
    for session in sorted(sessions):
        session_dir = capture_dir / session
        snapshots = list(session_dir.glob("*.json"))
        # Get first snapshot timestamp
        first_ts = "N/A"
        if snapshots:
            try:
                import json
                data = json.loads(snapshots[0].read_text())
                from datetime import datetime
                first_ts = datetime.fromtimestamp(data.get("timestamp", 0)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        table.add_row(session, str(len(snapshots)), first_ts)
    
    console.print(table)


@main.command("replay")
@click.argument("session_name")
@click.option(
    "--capture-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="./captures",
    help="Directory containing captured sessions",
)
@click.option(
    "--device",
    type=click.Choice(["garmin", "apple", "strava", "all"]),
    default="all",
    help="Device export path to test",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show full JSON diff details",
)
@click.pass_context
def replay(ctx, session_name: str, capture_dir: Path, device: str, verbose: bool):
    """Replay a captured session and show structured diffs."""
    capture_dir = ctx.obj.get("capture_dir", capture_dir)
    
    if device == "all":
        result = replay_session(capture_dir, session_name)
    else:
        result = get_device_path_diffs(capture_dir, session_name, device)
    
    if not result.snapshots:
        console.print(f"[red]No snapshots found for session: {session_name}[/red]")
        console.print(f"[yellow]Available sessions in {capture_dir}:[/yellow]")
        for d in capture_dir.iterdir():
            if d.is_dir():
                console.print(f"  - {d.name}")
        sys.exit(1)
    
    # Header
    status = "[green]CLEAN[/green]" if result.is_clean else "[red]CORRUPTED[/red]"
    console.print(Panel(
        f"[bold]Session:[/bold] {session_name}\n"
        f"[bold]Status:[/bold] {status}\n"
        f"[bold]Snapshots:[/bold] {len(result.snapshots)}",
        title="Replay Result"
    ))
    
    if result.first_corruption_hop:
        console.print(f"\n[bold red]⚠ First corruption at:[/bold red] {result.first_corruption_hop}")
    
    # Show pipeline stages found
    stages_found = list(dict.fromkeys(s.capture_point for s in result.snapshots))
    console.print(f"\n[bold]Pipeline stages:[/bold] {' → '.join(stages_found)}")
    
    if result.diffs:
        console.print(f"\n[bold yellow]Found {len(result.diffs)} differences:[/bold yellow]")
        
        table = Table(show_header=True)
        table.add_column("Path", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Old Value", style="red")
        table.add_column("New Value", style="green")
        
        for diff in result.diffs[:50]:  # Limit output
            old_v = str(diff.old_value)[:50] if diff.old_value is not None else "N/A"
            new_v = str(diff.new_value)[:50] if diff.new_value is not None else "N/A"
            table.add_row(diff.path[:60], diff.diff_type, old_v, new_v)
        
        console.print(table)
        
        if verbose:
            console.print("\n[bold]Full JSON diff:[/bold]")
            # Build a dict for pretty printing
            diff_dict = {
                "session": session_name,
                "first_corruption_hop": result.first_corruption_hop,
                "diffs": [
                    {
                        "path": d.path,
                        "type": d.diff_type,
                        "old_value": d.old_value,
                        "new_value": d.new_value,
                    }
                    for d in result.diffs
                ]
            }
            syntax = Syntax(
                str(diff_dict),
                "json",
                theme="monokai",
                line_numbers=False,
            )
            console.print(syntax)
    else:
        console.print("\n[green]No differences found - pipeline is clean![/green]")


@main.command("health")
@click.option(
    "--capture-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="./captures",
    help="Directory containing captured sessions",
)
@click.pass_context
def health(ctx, capture_dir: Path):
    """Show pipeline health report (per-hop clean rate and latency)."""
    capture_dir = ctx.obj.get("capture_dir", capture_dir)
    
    hop_health = health_report(capture_dir)
    console.print(print_health_table(hop_health))


@main.command("trends")
@click.option(
    "--weeks", default=8, help="Number of weeks to show"
)
@click.option(
    "--capture-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="./captures",
    help="Directory containing captured sessions",
)
@click.pass_context
def trends(ctx, weeks: int, capture_dir: Path):
    """Show corruption trends over time."""
    capture_dir = ctx.obj.get("capture_dir", capture_dir)
    
    trend_data = trend_report(capture_dir, weeks)
    console.print(print_trend_table(trend_data))


@main.command("breakdown")
@click.option(
    "--capture-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="./captures",
    help="Directory containing captured sessions",
)
@click.pass_context
def breakdown(ctx, capture_dir: Path):
    """Show corruption breakdown by workout type, source, and device."""
    capture_dir = ctx.obj.get("capture_dir", capture_dir)
    
    data = breakdown_report(capture_dir)
    console.print(print_breakdown_tables(data))


@main.command("viewer")
@click.option(
    "--capture-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="./captures",
    help="Directory containing captured sessions",
)
@click.option(
    "--port",
    default=8080,
    help="Port to serve the trace viewer",
)
@click.pass_context
def viewer(ctx, capture_dir: Path, port: int):
    """Start the trace viewer web server."""
    capture_dir = ctx.obj.get("capture_dir", capture_dir)
    
    console.print(f"[green]Starting trace viewer on http://localhost:{port}[/green]")
    console.print(f"[yellow]Serving captures from: {capture_dir}[/yellow]")
    
    try:
        import http.server
        import socketserver
        
        # Import the viewer HTML generator
        from .viewer import generate_viewer_html
        
        # Generate static HTML files for each session
        _generate_viewer_static(capture_dir)
        
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(capture_dir), **kwargs)
        
        with socketserver.TCPServer(("", port), Handler) as httpd:
            console.print("[green]Server running. Press Ctrl+C to stop.[/green]")
            httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/yellow]")


def _generate_viewer_static(capture_dir: Path):
    """Generate static HTML viewer files for sessions."""
    from .viewer import generate_viewer_html
    
    sessions = [d.name for d in capture_dir.iterdir() if d.is_dir()]
    
    for session in sessions:
        html = generate_viewer_html(capture_dir, session)
        output_file = capture_dir / session / "trace-viewer.html"
        output_file.write_text(html)
        console.print(f"Generated viewer: {output_file}")


if __name__ == "__main__":
    main()
