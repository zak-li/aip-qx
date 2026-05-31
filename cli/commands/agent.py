"""`pxtly agent …` — MiCA regulatory RAG agent."""
from __future__ import annotations

import typer

from cli.api import agent as api_agent
from cli.commands._common import audited, run_api
from cli.ui.console import display_agent_response, display_json_table, display_success

app = typer.Typer(name="agent", help="MiCA regulatory RAG agent.")


@app.command("ask")
@audited("agent ask")
def ask(query: str) -> None:
    """One-shot question for the MiCA agent."""
    data = run_api(lambda: api_agent.chat(query))
    answer = data.get("answer") or data.get("response") or "[empty]"
    display_agent_response(query, str(answer))


@app.command("search")
@audited("agent search")
def search(
    query: str,
    top_k: int = typer.Option(5, min=1, max=20),
) -> None:
    """Top-K semantic matches from the regulatory corpus."""
    data = run_api(lambda: api_agent.search(query, top_k))
    display_json_table(data, title=f"Search — {query!r}")


@app.command("status")
@audited("agent status")
def status() -> None:
    data = run_api(lambda: api_agent.status())
    display_json_table(data, title="Agent status")


@app.command("reindex")
@audited("agent reindex")
def reindex() -> None:
    """Force a re-index of the regulatory corpus (admin only, async)."""
    data = run_api(lambda: api_agent.reindex())
    display_success("Reindex task accepted.")
    display_json_table(data, title="Reindex")
