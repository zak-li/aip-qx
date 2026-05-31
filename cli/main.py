"""
cli/main.py
-----------
Typer application root.

  - No sub-command           → launches the interactive REPL.
  - Sub-command provided     → executes non-interactively (CI / scripts).

Logging is configured before any sub-application module is imported so the
sub-apps inherit the right log level / file rotation.
"""
from __future__ import annotations

import typer

from cli.logging_config import configure_logging
from cli.settings import settings

configure_logging(settings.log_dir)

# Sub-applications — imported *after* logging is configured. The order
# determines the listing in `pxtly --help`.
from cli.commands.agent import app as agent_app
from cli.commands.assets import app as assets_app
from cli.commands.audit import app as audit_app
from cli.commands.auth import app as auth_app
from cli.commands.compliance import app as compliance_app
from cli.commands.dashboard import app as dashboard_app
from cli.commands.events import app as events_app
from cli.commands.organizations import app as orgs_app
from cli.commands.system import app as system_app
from cli.commands.transactions import app as tx_app
from cli.commands.tribunal import app as tribunal_app
from cli.commands.zkp import app as zkp_app

app = typer.Typer(
    name="pxtly",
    help="Pxtly — Institutional RWA tokenisation control plane.",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)

# Order matters for --help readability: identity first, then resources,
# then platform-wide operations, then UI.
app.add_typer(auth_app)
app.add_typer(assets_app)
app.add_typer(tx_app)
app.add_typer(audit_app)
app.add_typer(compliance_app)
app.add_typer(zkp_app)
app.add_typer(tribunal_app)
app.add_typer(orgs_app)
app.add_typer(agent_app)
app.add_typer(events_app)
app.add_typer(system_app)
app.add_typer(dashboard_app)


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Launch the interactive REPL when no sub-command is given."""
    if ctx.invoked_subcommand is None:
        from cli.ui.repl import start_repl
        start_repl()


@app.command("version")
def version() -> None:
    """Print the CLI version."""
    from cli import __version__
    typer.echo(f"Pxtly CLI {__version__}")


if __name__ == "__main__":
    app()
