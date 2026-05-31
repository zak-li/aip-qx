"""`pxtly tribunal …` — regulator commit-reveal voting."""
from __future__ import annotations

import typer

from cli.api import tribunal as api_tribunal
from cli.commands._common import audited, run_api
from cli.ui.console import display_json_table

app = typer.Typer(name="tribunal", help="Regulator commit-reveal voting.")


@app.command("commit")
@audited("tribunal commit")
def commit(
    session_id: str = typer.Option(..., "--session"),
    commitment: str = typer.Option(..., help="Hash(vote || nonce)"),
) -> None:
    payload = {"session_id": session_id, "commitment": commitment}
    data = run_api(lambda: api_tribunal.vote_commit(payload))
    display_json_table(data, title="Vote committed")


@app.command("reveal")
@audited("tribunal reveal")
def reveal(
    session_id: str = typer.Option(..., "--session"),
    vote: str = typer.Option(...),
    nonce: str = typer.Option(...),
) -> None:
    payload = {"session_id": session_id, "vote": vote, "nonce": nonce}
    data = run_api(lambda: api_tribunal.vote_reveal(payload))
    display_json_table(data, title="Vote revealed")


@app.command("tally")
@audited("tribunal tally")
def tally(session_id: str) -> None:
    data = run_api(lambda: api_tribunal.tally(session_id))
    display_json_table(data, title=f"Tally — {session_id}")
