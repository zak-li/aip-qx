"""
cli/ui/console.py
-----------------
Rich console helpers -- display_* functions used across commands and REPL.

AESTHETIC RULES (strictly enforced):
  - NO unicode icons (no checkmarks, bullets, warning signs, dots).
  - Status messages use plain uppercase tags: [ERROR] [SUCCESS] [WARN] [INFO].
  - Zero emojis anywhere in this module.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from cli.ui.theme import (
    DANGER,
    DIM2,
    MUTED,
    NEUTRAL,
    OFFLINE,
    SUCCESS,
    V1,
    V2,
    WARN,
)

log = logging.getLogger(__name__)

custom_theme = Theme({
    "markdown.h1": "bold",
    "markdown.h2": "bold",
    "markdown.h3": "bold",
    "markdown.h4": "bold",
    "markdown.h5": "bold",
    "markdown.h6": "bold",
})
console = Console(highlight=False, theme=custom_theme)


# -- Screen helpers ----------------------------------------------------------

def enter_fullscreen() -> None:
    if sys.platform != "win32":
        sys.stdout.write("\033[?1049h\033[2J\033[H")
        sys.stdout.flush()
    else:
        os.system("cls")


def exit_fullscreen() -> None:
    if sys.platform != "win32":
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()


def clear_screen() -> None:
    if sys.platform == "win32":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


# -- Status helpers ----------------------------------------------------------

def display_error(msg: str) -> None:
    console.print(f"  [{DANGER}][ERROR][/] {msg}")
    log.error("UI error: %s", msg)


def display_info(msg: str) -> None:
    console.print(f"  [{MUTED}][INFO][/]  {msg}")


def display_success(msg: str) -> None:
    console.print(f"  [{SUCCESS}][OK][/]   {msg}")


def display_warn(msg: str) -> None:
    console.print(f"  [{WARN}][WARN][/]  {msg}")


def display_offline_warning() -> None:
    console.print(
        f"  [{OFFLINE} bold][OFFLINE][/]  "
        f"[{MUTED}]Serving cached data -- live services unreachable.[/]"
    )


# -- Banner ------------------------------------------------------------------

def display_banner() -> None:
    from rich.text import Text

    from cli.network_state import is_online
    from cli.ui.ascii import animate
    from cli.ui.theme import MUTED, NEUTRAL, V1, V2

    console.print()
    animate()
    console.print()

    ver = Text("  ")
    ver.append("Pxtly", style=f"bold {V2}")
    ver.append("   //   ", style=MUTED)
    ver.append("Crafted by ", style=NEUTRAL)
    ver.append("@zak-li ", style=f"italic {MUTED}")
    ver.append("x ", style=NEUTRAL)
    ver.append("@itsayaah20", style=f"italic {MUTED}")
    console.print(ver)

    if not is_online():
        console.print()
        display_offline_warning()

    hint = Text("  ")
    hint.append("Run ", style=f"italic {MUTED}")
    hint.append("/help", style=f"bold italic {V1}")
    hint.append(" for commands  --  ", style=f"italic {MUTED}")
    hint.append("/dashboard", style=f"bold italic {V1}")
    hint.append(" for full-screen TUI", style=f"italic {MUTED}")
    console.print()
    console.print(hint)
    console.print()


# -- Help table --------------------------------------------------------------

def display_help() -> None:
    console.print()
    console.print(f"  [{MUTED}]COMMANDS[/]")
    console.print()

    cmds = [
        ("/ask",         "Query the MiCA Regulatory Agent (LLM / RAG)"),
        ("/core wallet", "Fetch RWA asset  (e.g. /core wallet WALLET-001)"),
        ("/audit",       "On-chain audit history  (Hyperledger Fabric)"),
        ("/graph query", "Execute raw Cypher on Neo4j graph"),
        ("/graph fraud", "AML fraud detection for user ID"),
        ("/status",      "Ping all services, show network health"),
        ("/auth",        "Login via Keycloak OIDC  |  /auth logout"),
        ("/dashboard",   "Open full-screen real-time TUI dashboard"),
        ("/clear",       "Refresh the screen"),
        ("/exit",        "Quit the application"),
    ]
    for cmd, desc in cmds:
        t = Text("  ")
        t.append(f"{cmd:<24}", style=f"bold {V1}")
        t.append(desc, style=NEUTRAL)
        console.print(t)

    console.print()


# -- Agent response ----------------------------------------------------------

def display_agent_response(query: str, response: str) -> None:
    from rich.markdown import Markdown
    from rich.padding import Padding

    console.print()
    user_header = Text("  YOU", style=f"bold {MUTED}")
    user_body = Text(f"  {query}", style=NEUTRAL)
    console.print(user_header)
    console.print(user_body)
    console.print()

    agent_header = Text("  Pxtly", style=f"bold {V2}")
    console.print(agent_header)

    md = Markdown(response, justify="left")
    console.print(Padding(md, (0, 0, 0, 2)))
    console.print()


# -- JSON -> table -----------------------------------------------------------

def display_json_table(data: Any, title: str = "Data Record") -> None:
    """
    Render a JSON-y payload as a Rich panel.

    Accepts either:
      * dict — rendered as a flattened key/value table.
      * list of dicts — rendered as a multi-row table (union of keys).
      * list of scalars — rendered as a single-column table.
      * scalar — printed as plain text.
    """
    if data is None or (hasattr(data, "__len__") and len(data) == 0):
        display_info("No data returned.")
        return

    if isinstance(data, list):
        _render_list(data, title)
    elif isinstance(data, dict):
        _render_dict(data, title)
    else:
        console.print(Panel(
            str(data),
            title=f"[bold {V2}]{title}[/]",
            box=box.SQUARE, border_style=DIM2,
            expand=False, padding=(1, 2),
        ))


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        elif isinstance(v, list):
            out[key] = ", ".join(map(str, v))
        else:
            out[key] = str(v)
    return out


def _render_dict(data: dict[str, Any], title: str) -> None:
    t = Table(
        box=box.SQUARE, border_style=DIM2,
        show_header=True, header_style=f"bold {V2}",
        padding=(0, 2),
    )
    t.add_column("Key", style=f"bold {V1}", no_wrap=True)
    t.add_column("Value", style=NEUTRAL)
    for k, v in _flatten(data).items():
        t.add_row(k, v)
    console.print()
    console.print(Panel(
        t,
        title=f"[bold {V2}]{title}[/]",
        box=box.SQUARE, border_style=DIM2,
        expand=False, padding=(1, 2),
    ))
    console.print()


def _render_list(rows: list[Any], title: str) -> None:
    # Pick the union of keys across all dict rows so missing fields show
    # as blanks rather than raising.
    if all(isinstance(r, dict) for r in rows):
        columns: list[str] = []
        seen: set[str] = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    columns.append(str(k))
    else:
        columns = ["value"]

    t = Table(
        box=box.SQUARE, border_style=DIM2,
        show_header=True, header_style=f"bold {V2}",
        padding=(0, 2),
    )
    for col in columns:
        t.add_column(col, style=NEUTRAL, no_wrap=False)

    for r in rows:
        if isinstance(r, dict):
            t.add_row(*[str(r.get(c, ""))[:120] for c in columns])
        else:
            t.add_row(str(r)[:120])

    console.print()
    console.print(Panel(
        t,
        title=f"[bold {V2}]{title}[/] ({len(rows)} rows)",
        box=box.SQUARE, border_style=DIM2,
        expand=False, padding=(1, 2),
    ))
    console.print()


