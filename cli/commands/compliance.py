"""`pxtly compliance …` — KYC / AML / sanctions workflows."""
from __future__ import annotations

import typer

from cli.api import compliance as api_compliance
from cli.commands._common import audited, run_api
from cli.ui.console import display_json_table

app = typer.Typer(name="compliance", help="KYC / AML / sanctions.")


@app.command("summary")
@audited("compliance summary")
def summary() -> None:
    data = run_api(lambda: api_compliance.summary())
    display_json_table(data, title="Compliance summary")


@app.command("alerts")
@audited("compliance alerts")
def alerts() -> None:
    """Active AML / sanctions alerts."""
    data = run_api(lambda: api_compliance.alerts())
    display_json_table(data, title="Active alerts")


@app.command("user")
@audited("compliance user")
def user(user_id: str) -> None:
    data = run_api(lambda: api_compliance.user_status(user_id))
    display_json_table(data, title=f"Compliance — {user_id}")


@app.command("kyc-submit")
@audited("compliance kyc-submit")
def kyc_submit(
    user_id: str = typer.Option(...),
    document_hash: str = typer.Option(..., "--hash"),
    document_type: str = typer.Option(..., "--type"),
) -> None:
    """Submit a KYC document hash for approval."""
    payload = {
        "user_id": user_id,
        "document_hash": document_hash,
        "document_type": document_type,
    }
    data = run_api(lambda: api_compliance.kyc_submit(payload))
    display_json_table(data, title="KYC submission")


@app.command("kyc-approve")
@audited("compliance kyc-approve")
def kyc_approve(
    submission_id: str = typer.Option(..., "--id"),
    decision: str = typer.Option("APPROVED", help="APPROVED | REJECTED"),
    notes: str = typer.Option(""),
) -> None:
    payload = {"submission_id": submission_id, "decision": decision, "notes": notes}
    data = run_api(lambda: api_compliance.kyc_approve(payload))
    display_json_table(data, title="KYC decision")


@app.command("screening")
@audited("compliance screening")
def screening(
    user_id: str = typer.Option(...),
    full_name: str = typer.Option(...),
) -> None:
    """Run a sanctions / PEP screening for a user."""
    payload = {"user_id": user_id, "full_name": full_name}
    data = run_api(lambda: api_compliance.screening_run(payload))
    display_json_table(data, title=f"Screening — {full_name}")
