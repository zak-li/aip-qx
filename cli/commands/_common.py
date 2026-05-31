"""
cli/commands/_common.py
-----------------------
Cross-cutting helpers shared by every Typer subcommand.

  * `audited(name)`             — decorator that wraps a sync command,
                                  catches exceptions, logs the outcome to
                                  ~/.pxtly/audit.log, and converts to a
                                  Typer.Exit on failure.
  * `run_api(coro_factory)`     — execute an async API call inside a Rich
                                  status spinner with consistent error
                                  rendering.
  * `actor()`                   — current authenticated user (from the
                                  stored JWT) for audit attribution.
"""
from __future__ import annotations

import base64
import functools
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import typer

from cli.async_runner import run
from cli.http import AuthError, PxtlyApiError
from cli.security.audit import audit_event
from cli.security.tokens import get_token_bundle
from cli.ui.console import console, display_error
from cli.ui.theme import V2

log = logging.getLogger(__name__)


def actor() -> str | None:
    """
    Best-effort actor identifier — pulled from the JWT 'preferred_username'
    or 'sub' claim. Used only for the local audit log; never trusted as
    authentication.
    """
    bundle = get_token_bundle()
    if not bundle:
        return None
    try:
        parts = bundle.access_token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims.get("preferred_username") or claims.get("email") or claims.get("sub")
    except Exception:
        return None


def run_api(coro_factory: Callable[[], Awaitable[Any]]) -> Any:
    """Run an async API call inside a spinner. Returns the awaited result."""
    with console.status("", spinner="dots2", spinner_style=f"bold {V2}"):
        return run(coro_factory())


def audited(command_name: str) -> Callable:
    """
    Decorator factory: wraps a command so that every invocation produces one
    audit line (success or failure) and any PxtlyApiError is rendered via the
    common error pipeline instead of bubbling up a stack trace.
    """

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = fn(*args, **kwargs)
                audit_event(command_name, args=kwargs, actor=actor(), result="ok")
                return result
            except AuthError as exc:
                audit_event(
                    command_name, args=kwargs, actor=actor(),
                    result="auth_error", status_code=exc.status_code,
                )
                display_error(
                    "Authentication required or session expired. "
                    "Run: pxtly auth login"
                )
                raise typer.Exit(1) from exc
            except PxtlyApiError as exc:
                audit_event(
                    command_name, args=kwargs, actor=actor(),
                    result="api_error", status_code=exc.status_code,
                )
                display_error(str(exc))
                raise typer.Exit(1) from exc
            except typer.Exit:
                raise
            except Exception as exc:
                log.exception("Unhandled error in %s", command_name)
                audit_event(
                    command_name, args=kwargs, actor=actor(),
                    result="error", extra={"exception_type": type(exc).__name__},
                )
                display_error(f"{type(exc).__name__}: {exc}")
                raise typer.Exit(2) from exc

        return wrapper

    return deco
