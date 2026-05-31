"""`pxtly auth …` — login, logout, refresh, profile, GDPR exports."""
from __future__ import annotations

import json

import typer

from cli.api import auth as api_auth
from cli.commands._common import audited, run_api
from cli.security.tokens import get_token_bundle, has_tokens
from cli.ui.console import console, display_info, display_json_table, display_success

app = typer.Typer(name="auth", help="Keycloak authentication & session.")


@app.command("login")
@audited("auth login")
def login(
    pkce: bool = typer.Option(
        True,
        "--pkce/--password",
        help="Authorization Code + PKCE (default) or legacy password grant.",
    ),
    username: str = typer.Option(None, help="(--password only) username"),
    password: str = typer.Option(
        None,
        prompt=False,
        hide_input=True,
        help="(--password only) password — prompted if omitted",
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Print the auth URL instead of opening a browser.",
    ),
) -> None:
    """Authenticate to Keycloak and persist a full token bundle to the OS keyring."""
    if pkce:
        run_api(lambda: api_auth.login_pkce(open_browser=not no_browser))
    else:
        if not username:
            username = typer.prompt("Username")
        if not password:
            password = typer.prompt("Password", hide_input=True)
        run_api(lambda: api_auth.login_password(username, password))

    display_success("Session active. Tokens stored in the OS keyring.")


@app.command("logout")
@audited("auth logout")
def logout() -> None:
    """Revoke the refresh token on Keycloak and clear local tokens."""
    run_api(lambda: api_auth.logout())
    display_success("Logged out.")


@app.command("status")
@audited("auth status")
def status() -> None:
    """Show whether a session exists and when it expires."""
    bundle = get_token_bundle()
    if not bundle:
        display_info("Not authenticated. Run: pxtly auth login")
        return
    payload = {
        "token_type": bundle.token_type,
        "access_expired": bundle.is_access_expired(),
        "refresh_expired": bundle.is_refresh_expired(),
        "expires_in_seconds": max(0, int(bundle.expires_at - __import__("time").time())),
        "scope": bundle.scope,
    }
    display_json_table(payload, title="Session")


@app.command("refresh")
@audited("auth refresh")
def refresh() -> None:
    """Force an immediate refresh of the access token."""
    if not has_tokens():
        display_info("No session — nothing to refresh.")
        raise typer.Exit(1)
    new = run_api(lambda: api_auth.refresh_now())
    if new is None:
        display_info("Refresh token expired — run `pxtly auth login` again.")
        raise typer.Exit(1)
    display_success("Token refreshed.")


@app.command("me")
@audited("auth me")
def me() -> None:
    """Show the caller's profile as returned by /api/v1/auth/me."""
    data = run_api(lambda: api_auth.me())
    display_json_table(data, title="Profile")


@app.command("export")
@audited("auth export")
def export(
    output: str = typer.Option("-", "--output", "-o", help="File path or '-' for stdout."),
) -> None:
    """GDPR — download every record the platform holds about you."""
    data = run_api(lambda: api_auth.me_export())
    serialised = json.dumps(data, indent=2, default=str)
    if output == "-":
        console.print_json(serialised)
    else:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(serialised)
        display_success(f"Wrote {output}")


@app.command("delete-account")
@audited("auth delete-account")
def delete_account(
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """GDPR — permanently delete your account. Irreversible."""
    if not yes:
        confirm = typer.confirm(
            "This will delete your account, all tokenised assets owned, and "
            "all audit records you authored. Type 'yes' to confirm",
        )
        if not confirm:
            raise typer.Exit(0)
    run_api(lambda: api_auth.me_delete())
    display_success("Account deleted.")
