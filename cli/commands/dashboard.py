"""`pxtly dashboard` — full-screen Textual TUI."""
from __future__ import annotations

import typer

from cli.ui.console import display_error

app = typer.Typer(
    name="dashboard",
    help="Full-screen real-time TUI dashboard.",
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def launch(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    try:
        from cli.ui.dashboard import launch_dashboard
        launch_dashboard()
    except ImportError as exc:
        display_error(f"Textual not installed: {exc}. Run: pip install textual")
        raise typer.Exit(1) from exc
    except Exception as exc:
        display_error(str(exc))
        raise typer.Exit(1) from exc
