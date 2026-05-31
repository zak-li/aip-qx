"""`pxtly events stream` — live tail of the platform SSE feed."""
from __future__ import annotations

import typer

from cli.commands._common import audited
from cli.ui.console import console, display_error

app = typer.Typer(name="events", help="Live event stream.")


@app.command("stream")
@audited("events stream")
def stream(
    max_events: int = typer.Option(0, "--max", help="Stop after N events (0 = forever)."),
) -> None:
    """Tail /api/v1/events/stream (Server-Sent Events)."""
    try:
        from cli.api.events import stream_events
    except ImportError as exc:
        display_error(f"SSE backend unavailable: {exc}")
        raise typer.Exit(1) from exc

    console.print("[dim]Streaming events — Ctrl-C to stop.[/dim]")
    try:
        stream_events(max_events=max_events or None)
    except KeyboardInterrupt:
        console.print("[dim]Stream stopped.[/dim]")
