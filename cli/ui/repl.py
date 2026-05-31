"""
cli/ui/repl.py
--------------
Advanced prompt_toolkit REPL.

AESTHETIC RULES (v3):
  - Zero emojis anywhere.
  - Zero unicode icons. The ONLY exception: right-pointing chevron (>) for prompt.
  - Bottom toolbar: IBM-style dense format:
        [cli.OS] [Subscription: Online] [Status: Online|Offline] [Host: ...]

ARCHITECTURE:
  - Background async ping runs on a dedicated daemon thread with its own
    event loop -- never touches the main prompt_toolkit event loop.
  - All REPL handler coroutines run via utils.async_runner.run() which
    always creates a fresh, isolated event loop.
  - _ping_stop threading.Event allows clean shutdown on REPL exit.
  - All console.status() spinners use "dots2" (npm-style) with zero text.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings

from cli.async_runner import run
from cli.network_state import is_online, register_callback
from cli.settings import settings
from cli.ui.console import (
    clear_screen,
    console,
    display_agent_response,
    display_banner,
    display_error,
    display_help,
    display_info,
    display_json_table,
    display_offline_warning,
    display_success,
    enter_fullscreen,
    exit_fullscreen,
)
from cli.ui.theme import DIM, MUTED, V1, V2

log = logging.getLogger(__name__)

# -- Command registry for auto-suggest ---------------------------------------

_COMMANDS: list[str] = sorted([
    "/ask", "/auth", "/auth logout",
    "/audit",
    "/dashboard",
    "/exit",
    "/asset ", "/fraud ",
    "/help",
    "/status",
    "/clear",
])


class _CommandSuggest(AutoSuggest):
    def get_suggestion(self, buffer: Any, document: Any) -> Any:
        text = document.text
        if not text:
            return None
        low = text.lower()
        for cmd in _COMMANDS:
            if cmd.startswith(low) and cmd != low:
                return Suggestion(cmd[len(text):])
        return None


# -- Bottom toolbar ----------------------------------------------------------

_toolbar_status: str = "Connecting"
_toolbar_lock = threading.Lock()


def _update_toolbar_status(online: bool) -> None:
    global _toolbar_status
    with _toolbar_lock:
        _toolbar_status = "Online" if online else "Offline"


register_callback(_update_toolbar_status)


def _toolbar() -> HTML:
    with _toolbar_lock:
        status = _toolbar_status

    host = settings.host_label
    status_color = "#10b981" if status == "Online" else "#f59e0b"

    return HTML(
        '<style bg="#0D1117" fg="#475569"> '
        '<b><style fg="#3b82f6"> Pxtly </style>'
        '<style fg="#1e3a8a"> | </style> Subscription: Online '
        '<style fg="#1e3a8a"> | </style> Status: '
        f'<style fg="{status_color}">{status}</style> '
        '<style fg="#1e3a8a"> | </style> Host: '
        f'<style fg="#334155">{host}</style> '
        '</b>'
        '</style>'
    )


# -- Background ping daemon --------------------------------------------------

_ping_stop = threading.Event()


def _ping_daemon() -> None:
    """Runs on a dedicated daemon thread with its own asyncio event loop."""
    from cli.api.system import ping
    from cli.network_state import set_online

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _body() -> None:
        while not _ping_stop.is_set():
            try:
                online, _ = await ping()
                set_online(online)
            except Exception as exc:
                log.debug("Ping error: %s", exc)
                set_online(False)
            for _ in range(30):
                if _ping_stop.is_set():
                    break
                await asyncio.sleep(1)

    try:
        loop.run_until_complete(_body())
    finally:
        loop.close()


def _start_ping_daemon() -> None:
    t = threading.Thread(target=_ping_daemon, name="pxtly-ping", daemon=True)
    t.start()
    log.debug("Background ping daemon started.")


# -- Prompt helper -----------------------------------------------------------

def _prompt_value(label: str) -> str:
    from rich.prompt import Prompt
    while True:
        try:
            value = Prompt.ask(f"  [{V2}]{label}[/]", console=console).strip()
            if value:
                return value
        except (KeyboardInterrupt, EOFError):
            console.print(f"\n  [{MUTED}]Cancelled[/]")
            return ""


# -- Main REPL ---------------------------------------------------------------

def start_repl() -> None:
    enter_fullscreen()
    _start_ping_daemon()

    history_file = Path.home() / ".pxtly" / "history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    kb = KeyBindings()

    @kb.add("tab")
    def _tab(event: Any) -> None:
        b = event.current_buffer
        if b.suggestion:
            b.insert_text(b.suggestion.text)

    session: PromptSession[str] = PromptSession(
        auto_suggest=_CommandSuggest(),
        key_bindings=kb,
        history=FileHistory(str(history_file)),
        placeholder=HTML(f'<style color="{DIM}">/help</style>'),
        bottom_toolbar=_toolbar,
        refresh_interval=2,
    )

    try:
        display_banner()
        while True:
            console.print()
            try:
                raw: str = session.prompt(
                    HTML(f'  <b><style color="{V1}">></style></b> ')
                ).strip()
            except (KeyboardInterrupt, EOFError):
                console.print(f"\n  [{MUTED}]Type /exit to quit.[/]\n")
                continue
            except Exception as exc:
                log.debug("Prompt error: %s", exc)
                continue

            if not raw or raw.startswith("#"):
                continue

            if not is_online():
                display_offline_warning()

            parts = raw.split(None, 1)
            cmd = parts[0].lower().lstrip("/")
            arg = parts[1] if len(parts) > 1 else ""

            _dispatch(cmd, arg)

    finally:
        _ping_stop.set()
        exit_fullscreen()


# -- Dispatch table ----------------------------------------------------------

def _dispatch(cmd: str, arg: str) -> None:
    match cmd:
        case "exit" | "quit" | "q":
            console.print(f"\n  [{MUTED}]Secure session terminated.[/]\n")
            raise SystemExit(0)

        case "clear" | "cls" | "wipe":
            clear_screen()
            display_banner()

        case "help" | "h" | "?":
            display_help()

        case "ask" | "mica":
            _handle_ask(arg)

        case "auth" | "login":
            _handle_auth(arg)

        case "status":
            _handle_status()

        case "audit":
            _handle_audit(arg)

        case "fraud":
            _handle_fraud(arg)

        case "asset":
            _handle_asset(arg)

        case "dashboard":
            _launch_dashboard()

        case _:
            display_error(f"Unknown command: /{cmd}  --  run /help for available commands.")


# -- REPL sub-handlers -------------------------------------------------------

def _handle_ask(arg: str) -> None:
    from cli.api.agent import chat
    if not arg:
        arg = _prompt_value("Query")
    if not arg:
        return
    with console.status("", spinner="dots2", spinner_style=f"bold {V2}"):
        try:
            data = run(chat(arg))
            response = str(data.get("answer") or data.get("response") or "[empty]")
        except Exception as exc:
            display_error(str(exc))
            return
    display_agent_response(arg, response)


def _handle_auth(arg: str) -> None:
    from cli.api.auth import login_password, login_pkce
    from cli.api.auth import logout as _logout
    from cli.security import delete_tokens

    if arg.lower() == "logout":
        try:
            run(_logout())
        except Exception:
            delete_tokens()
        display_success("Session terminated.")
        return

    if arg.lower() == "pkce" or arg == "":
        display_info("PKCE login — opening browser…")
        with console.status("", spinner="dots2", spinner_style=f"bold {V2}"):
            try:
                run(login_pkce())
                display_success("Session active. Tokens stored in OS keyring.")
            except Exception as exc:
                display_error(str(exc))
        return

    # Legacy password flow: /auth password
    display_info("Password grant — discouraged (use /auth pkce when possible).")
    username = _prompt_value("Username")
    password = _prompt_value("Password")
    if not username or not password:
        return
    with console.status("", spinner="dots2", spinner_style=f"bold {V2}"):
        try:
            run(login_password(username, password))
            display_success("Session active. Tokens stored in OS keyring.")
        except Exception as exc:
            display_error(str(exc))
            display_info(f"Verify credentials for realm: {settings.keycloak_realm}")


def _handle_status() -> None:
    from cli.api.system import ping
    with console.status("", spinner="dots2", spinner_style=f"bold {V2}"):
        is_up, msg = run(ping())
    if is_up:
        display_success(f"Infrastructure operational -- {msg}")
    else:
        display_error(f"Infrastructure unreachable -- {msg}")


def _handle_audit(arg: str) -> None:
    from cli.api.audit import asset_trail
    if not arg:
        arg = _prompt_value("Asset ID")
    if not arg:
        return
    with console.status("", spinner="dots2", spinner_style=f"bold {V2}"):
        try:
            data = run(asset_trail(arg))
            display_success(f"Audit trail retrieved for {arg}")
            display_json_table(data, title=f"On-Chain Audit -- {arg}")
        except Exception as exc:
            display_error(str(exc))


def _handle_fraud(arg: str) -> None:
    """Run AML fraud-detection traversal (Celery task)."""
    from cli.api.audit import fraud_scan
    if not arg:
        arg = _prompt_value("User ID")
    if not arg:
        return
    with console.status("", spinner="dots2", spinner_style=f"bold {V2}"):
        try:
            data = run(fraud_scan({"user_id": arg, "depth": 2}))
            display_json_table(data, title=f"Fraud scan -- {arg}")
        except Exception as exc:
            display_error(str(exc))


def _handle_asset(arg: str) -> None:
    """Get one asset by ID."""
    from cli.api.assets import get as _get
    if not arg:
        arg = _prompt_value("Asset ID")
    if not arg:
        return
    with console.status("", spinner="dots2", spinner_style=f"bold {V2}"):
        try:
            data = run(_get(arg))
            display_json_table(data, title=f"Asset -- {arg}")
        except Exception as exc:
            display_error(str(exc))


def _launch_dashboard() -> None:
    from cli.ui.dashboard import launch_dashboard
    exit_fullscreen()
    try:
        launch_dashboard()
    except Exception as exc:
        import traceback
        crash_log = Path.home() / ".pxtly" / "dashboard_crash.log"
        crash_log.write_text(traceback.format_exc(), encoding="utf-8")
        display_error(f"Dashboard error: {exc}  (see {crash_log})")
    finally:
        enter_fullscreen()
        display_banner()

