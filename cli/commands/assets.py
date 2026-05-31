"""`pxtly assets …` — RWA asset lifecycle."""
from __future__ import annotations

import typer

from cli.api import assets as api_assets
from cli.commands._common import audited, run_api
from cli.ui.console import display_json_table, display_success

app = typer.Typer(name="assets", help="Tokenised asset lifecycle.")


@app.command("list")
@audited("assets list")
def list_(
    status: str = typer.Option(None, help="Filter by status (ACTIF, GELE, …)"),
    asset_type: str = typer.Option(None, "--type", help="Filter by asset_type"),
    limit: int = typer.Option(50, min=1, max=500),
    offset: int = typer.Option(0, min=0),
) -> None:
    data = run_api(lambda: api_assets.list_assets(status, asset_type, limit, offset))
    display_json_table(data, title="Assets")


@app.command("show")
@audited("assets show")
def show(asset_id: str) -> None:
    """Get one asset by ID."""
    data = run_api(lambda: api_assets.get(asset_id))
    display_json_table(data, title=f"Asset — {asset_id}")


@app.command("history")
@audited("assets history")
def history(asset_id: str) -> None:
    """On-chain provenance trail for an asset."""
    data = run_api(lambda: api_assets.history(asset_id))
    display_json_table(data, title=f"Provenance — {asset_id}")


@app.command("tokenize")
@audited("assets tokenize")
def tokenize(
    asset_id: str = typer.Option(..., help="RWA-XX-XXX-YYYY-NNN"),
    isin: str = typer.Option(...),
    asset_type: str = typer.Option(..., "--type"),
    asset_name: str = typer.Option(...),
    issuer_lei: str = typer.Option(..., "--lei"),
    nominal_value: float = typer.Option(..., "--value"),
    currency: str = typer.Option("EUR"),
    issuance_date: str = typer.Option(..., help="ISO-8601 date"),
    justification: str = typer.Option(""),
) -> None:
    """Issue a new tokenised asset on the ledger (BANK01MSP only)."""
    payload = {
        "asset_id": asset_id,
        "isin": isin,
        "asset_type": asset_type,
        "asset_name": asset_name,
        "issuer_lei": issuer_lei,
        "nominal_value": nominal_value,
        "currency": currency,
        "issuance_date": issuance_date,
        "justification": justification,
    }
    data = run_api(lambda: api_assets.tokenize(payload))
    display_success(f"Tokenised {asset_id}")
    display_json_table(data, title="Result")


@app.command("transfer")
@audited("assets transfer")
def transfer(
    asset_id: str = typer.Option(...),
    to_owner: str = typer.Option(..., "--to", help="New owner DN"),
    price: float = typer.Option(...),
    justification: str = typer.Option(""),
) -> None:
    """Transfer ownership of an asset (BANK01MSP only)."""
    payload = {
        "asset_id": asset_id,
        "to_owner": to_owner,
        "price": price,
        "justification": justification,
    }
    data = run_api(lambda: api_assets.transfer(payload))
    display_success(f"Transferred {asset_id} → {to_owner}")
    display_json_table(data, title="Result")


@app.command("freeze")
@audited("assets freeze")
def freeze(
    asset_id: str = typer.Option(...),
    reason: str = typer.Option(...),
    regulatory_ref: str = typer.Option(..., "--ref", help="REG-CATEGORY-YYYY-NNN"),
) -> None:
    """Freeze an asset (REG01MSP only). Blocks further transfers."""
    payload = {"asset_id": asset_id, "reason": reason, "regulatory_ref": regulatory_ref}
    data = run_api(lambda: api_assets.freeze(payload))
    display_success(f"Frozen {asset_id}")
    display_json_table(data, title="Result")


@app.command("unfreeze")
@audited("assets unfreeze")
def unfreeze(
    asset_id: str = typer.Option(...),
    justification: str = typer.Option(""),
) -> None:
    """Lift a freeze on an asset (REG01MSP only)."""
    payload = {"asset_id": asset_id, "justification": justification}
    data = run_api(lambda: api_assets.unfreeze(payload))
    display_success(f"Unfrozen {asset_id}")
    display_json_table(data, title="Result")


@app.command("valuate")
@audited("assets valuate")
def valuate(
    asset_id: str,
    value: float = typer.Option(..., "--value"),
    source: str = typer.Option("internal"),
) -> None:
    """Record a new valuation point for an asset."""
    payload = {"value": value, "source": source}
    data = run_api(lambda: api_assets.valuate(asset_id, payload))
    display_json_table(data, title=f"Valuation — {asset_id}")


@app.command("valuations")
@audited("assets valuations")
def valuations(asset_id: str) -> None:
    """List historical valuations for an asset."""
    data = run_api(lambda: api_assets.valuations(asset_id))
    display_json_table(data, title=f"Valuations — {asset_id}")
