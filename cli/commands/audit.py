"""`pxtly audit …` — on-chain audit + LLM-generated PDF reports."""
from __future__ import annotations

import typer

from cli.api import audit as api_audit
from cli.commands._common import audited, run_api
from cli.ui.console import display_json_table, display_success

app = typer.Typer(name="audit", help="Audit trail + compliance reports.")


@app.command("log")
@audited("audit log")
def log_(
    limit: int = typer.Option(50, min=1, max=500),
    offset: int = typer.Option(0, min=0),
    actor_filter: str = typer.Option(None, "--actor"),
) -> None:
    data = run_api(lambda: api_audit.list_log(limit, offset, actor_filter))
    display_json_table(data, title="Audit log")


@app.command("asset")
@audited("audit asset")
def asset(asset_id: str) -> None:
    """Full on-chain audit trail for an asset."""
    data = run_api(lambda: api_audit.asset_trail(asset_id))
    display_json_table(data, title=f"On-chain audit — {asset_id}")


@app.command("report")
@audited("audit report")
def report(asset_id: str) -> None:
    """Kick off async LaTeX-rendered compliance report. Returns a task_id."""
    data = run_api(lambda: api_audit.generate_report(asset_id))
    display_success(f"Report task accepted (task_id={data.get('task_id')})")
    display_json_table(data, title="Report task")


@app.command("report-status")
@audited("audit report-status")
def report_status(task_id: str) -> None:
    data = run_api(lambda: api_audit.report_status(task_id))
    display_json_table(data, title=f"Report task — {task_id}")


@app.command("fraud-scan")
@audited("audit fraud-scan")
def fraud_scan(
    user_id: str = typer.Option(..., help="User to scan"),
    depth: int = typer.Option(2, min=1, max=4),
) -> None:
    """Run an AML graph traversal (async Celery task)."""
    payload = {"user_id": user_id, "depth": depth}
    data = run_api(lambda: api_audit.fraud_scan(payload))
    display_json_table(data, title=f"Fraud scan — {user_id}")
