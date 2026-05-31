"""`pxtly zkp …` — zero-knowledge KYC credentials."""
from __future__ import annotations

import typer

from cli.api import zkp as api_zkp
from cli.commands._common import audited, run_api
from cli.ui.console import display_json_table, display_success

app = typer.Typer(name="zkp", help="ZK-KYC credentials.")


@app.command("setup-key")
@audited("zkp setup-key")
def setup_key(user_id: str = typer.Option(...)) -> None:
    """Generate a platform signing key pair for the given user."""
    payload = {"user_id": user_id}
    data = run_api(lambda: api_zkp.setup_key(payload))
    display_json_table(data, title=f"ZKP key — {user_id}")


@app.command("verify")
@audited("zkp verify")
def verify(
    credential_id: str = typer.Option(..., "--id"),
    proof: str = typer.Option(..., help="Hex-encoded Schnorr proof"),
) -> None:
    payload = {"credential_id": credential_id, "proof": proof}
    data = run_api(lambda: api_zkp.verify(payload))
    display_json_table(data, title="Verification")


@app.command("status")
@audited("zkp status")
def status() -> None:
    data = run_api(lambda: api_zkp.status())
    display_json_table(data, title="ZKP status")


@app.command("revoke")
@audited("zkp revoke")
def revoke(credential_id: str) -> None:
    data = run_api(lambda: api_zkp.revoke(credential_id))
    display_success(f"Revoked {credential_id}")
    display_json_table(data, title="Result")
