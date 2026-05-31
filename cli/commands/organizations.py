"""`pxtly orgs …` — institutions, users, portfolios."""
from __future__ import annotations

import typer

from cli.api import organizations as api_orgs
from cli.commands._common import audited, run_api
from cli.ui.console import display_json_table

app = typer.Typer(name="orgs", help="Organisations & users directory.")


@app.command("list")
@audited("orgs list")
def list_() -> None:
    data = run_api(lambda: api_orgs.list_orgs())
    display_json_table(data, title="Organisations")


@app.command("users")
@audited("orgs users")
def users(
    role: str = typer.Option(None),
    country: str = typer.Option(None),
) -> None:
    data = run_api(lambda: api_orgs.list_users(role, country))
    display_json_table(data, title="Users")


@app.command("portfolio")
@audited("orgs portfolio")
def portfolio(org_id: str) -> None:
    data = run_api(lambda: api_orgs.portfolio(org_id))
    display_json_table(data, title=f"Portfolio — {org_id}")
