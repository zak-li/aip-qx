"""`pxtly tx …` — transaction history."""
from __future__ import annotations

import typer

from cli.api import transactions as api_tx
from cli.commands._common import audited, run_api
from cli.ui.console import display_json_table

app = typer.Typer(name="tx", help="Transaction history.")


@app.command("list")
@audited("tx list")
def list_(
    asset_id: str = typer.Option(None, "--asset"),
    limit: int = typer.Option(50, min=1, max=500),
    offset: int = typer.Option(0, min=0),
) -> None:
    data = run_api(lambda: api_tx.list_tx(asset_id, limit, offset))
    display_json_table(data, title="Transactions")


@app.command("stats")
@audited("tx stats")
def stats() -> None:
    """Summary stats — count, volume, top assets."""
    data = run_api(lambda: api_tx.stats())
    display_json_table(data, title="Tx stats")


@app.command("show")
@audited("tx show")
def show(tx_ref: str) -> None:
    data = run_api(lambda: api_tx.get(tx_ref))
    display_json_table(data, title=f"Tx — {tx_ref}")
