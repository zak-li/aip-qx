"""`pxtly system …` — platform health, config, audit log."""
from __future__ import annotations

import typer

from cli.api import system as api_system
from cli.commands._common import audited, run_api
from cli.security.audit import recent_events
from cli.settings import settings
from cli.ui.console import console, display_error, display_json_table, display_success

app = typer.Typer(name="system", help="Platform health, config, audit log.")


@app.command("status")
@audited("system status")
def status() -> None:
    """Quick /health probe."""
    is_up, msg = run_api(lambda: api_system.ping())
    if is_up:
        display_success(f"Online — {msg}")
    else:
        display_error(f"Offline — {msg}")
        raise typer.Exit(1)


@app.command("health")
@audited("system health")
def deep_health() -> None:
    """Deep readiness probe — Fabric, Vault, Neo4j, …"""
    data = run_api(lambda: api_system.deep_health())
    display_json_table(data, title="Deep health")


@app.command("config")
@audited("system config")
def config() -> None:
    """Print the effective settings (secrets redacted)."""
    payload = settings.model_dump(exclude={"keycloak_client_secret"})
    payload["keycloak_client_secret_set"] = settings.is_confidential_client
    payload["audit_log"] = str(settings.audit_log_path)
    display_json_table(payload, title="Settings")


@app.command("audit")
def audit(
    n: int = typer.Option(20, min=1, max=500, help="How many recent events to show."),
) -> None:
    """Show the last N entries from the local audit log."""
    events = list(recent_events(n))
    if not events:
        console.print("[dim]No audit events recorded yet.[/dim]")
        return
    display_json_table(events, title=f"Local audit log (last {n})")
