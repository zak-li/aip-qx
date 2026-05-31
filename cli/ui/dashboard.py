"""
cli/ui/dashboard.py
-------------------
Full-screen Textual TUI dashboard -- Bloomberg Terminal aesthetic.

Layout (validated against Textual 8.x)
------
+----------------------------------------------------------+
|  TOPBAR   Pxtly                     PRODUCTION  ONLINE  |
+--------------------------------+-------------------------+
|  LEFT 60%                      |  RIGHT 40%              |
|  +-- NETWORK HEALTH ---------+ |  +-- RECENT EVENTS ---+ |
|  |  7-service status grid    | |  |  DataTable + deque | |
|  +---------------------------+ |  +-------------------+ |
|  +-- LIVE STREAM (SSE) ------+ |  +-- TELEMETRY ------+ |
|  |  RichLog, scrollable      | |  |  counters/uptime  | |
|  +---------------------------+ |  +-------------------+ |
+--------------------------------+-------------------------+
|  FOOTER  [Q] Quit  [R] Reconnect  [C] Clear             |
+----------------------------------------------------------+

Architecture decisions
----------------------
- `_ticker` is a Textual Timer (1 Hz) -- drains the SSE queue and
  refreshes all reactive widgets.  No asyncio.create_task calls outside
  the Textual event loop.
- Network-state callback fires on a foreign thread; forwarded to the
  Textual event loop via `call_from_thread`.
- DataTable row eviction uses an explicit `deque[RowKey]` -- never
  `get_row_at()[0]` (that returns a Row namedtuple, not a RowKey).
- SSE client is started inside `on_mount` (not at import time) so it
  always runs on the correct event loop.
- `on_unmount` cancels the SSE background task cleanly.
- All `query_one` calls are wrapped in try/except so a missing widget
  never crashes the whole app.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import DataTable, Footer, RichLog, Static
from textual.widgets._data_table import RowKey

from cli.api.events import SseEvent, sse_client
from cli.network_state import is_online, register_callback, unregister_callback
from cli.settings import settings
from cli.ui.theme import DASHBOARD_CSS

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Color map: SSE event type -> Rich markup colour
# ---------------------------------------------------------------------------
_EVENT_COLORS: dict[str, str] = {
    "FRAUD ALERT":   "red bold",
    "FRAUD":         "red",
    "BLOCK MINT":    "green",
    "TX CONFIRMED":  "green",
    "TRANSFER":      "cyan",
    "KYC PASSED":    "green dim",
    "KYC FAILED":    "red dim",
    "RAW":           "dim",
    "MESSAGE":       "#3b82f6",
    "ERROR":         "yellow",
    "WARN":          "yellow dim",
}
_DEFAULT_EVENT_COLOR = "#3b82f6"

_MAX_TABLE_ROWS = 200


# ---------------------------------------------------------------------------
# Reusable widgets
# ---------------------------------------------------------------------------

class PaneHeader(Static):
    """
    Single-line bold section title inside a pane.
    Thin bottom border separates it from the content below.
    """
    DEFAULT_CSS = (
        "PaneHeader {"
        "  height: 1;"
        "  color: #3b82f6;"
        "  text-style: bold;"
        "  padding: 0 1;"
        "  border-bottom: solid #1e3a8a;"
        "  margin-bottom: 1;"
        "}"
    )


class HealthGrid(Static):
    """
    Read-only 7-row service-health grid.
    Refreshed every second by the dashboard timer.
    """

    SERVICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("Keycloak IAM",  "auth"),
        ("MiCA Agent",    "agent"),
        ("Fabric Audit",  "audit"),
        ("Neo4j Graph",   "graph"),
        ("RWA Core",      "core"),
        ("Health Probe",  "health"),
        ("SSE Stream",    "sse"),
    )

    def _build_markup(self) -> str:
        online = is_online()
        sse_ok = sse_client.is_connected
        lines: list[str] = []
        for name, svc in self.SERVICES:
            if svc == "sse":
                ok = sse_ok
            else:
                ok = online
            state = "ONLINE " if ok else "OFFLINE"
            col   = "green"  if ok else ("red" if svc == "sse" else "yellow")
            lines.append(f"  [{col}]{state}[/]  [{col} dim]{name}[/]")
        return "\n".join(lines)

    def on_mount(self) -> None:
        self.update(self._build_markup())

    def refresh_health(self) -> None:
        self.update(self._build_markup())


class StatsBar(Static):
    """Telemetry counters in the bottom-right pane."""

    def on_mount(self) -> None:
        self.update(self._build_markup(0, 0.0))

    def _build_markup(self, event_count: int, uptime: float) -> str:
        h = int(uptime // 3600)
        m = int((uptime % 3600) // 60)
        s = int(uptime % 60)
        sse_col   = "green"  if sse_client.is_connected else "yellow"
        sse_label = "CONNECTED"    if sse_client.is_connected else "RECONNECTING"
        return (
            f"  [dim]SSE[/]      [{sse_col}]{sse_label}[/]\n"
            f"  [dim]Events[/]   [white]{event_count:,}[/]\n"
            f"  [dim]Uptime[/]   [white]{h:02d}:{m:02d}:{s:02d}[/]"
        )

    def refresh(self, event_count: int, uptime: float) -> None:  # type: ignore[override]
        self.update(self._build_markup(event_count, uptime))


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class QxDashboard(App[None]):
    """Pxtly CLI — Institutional real-time dashboard."""

    CSS = DASHBOARD_CSS
    TITLE = "Pxtly"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q",      "quit",          "Quit",      priority=True),
        Binding("r",      "reconnect_sse", "Reconnect"),
        Binding("c",      "clear_events",  "Clear"),
        Binding("ctrl+c", "quit",          "Quit",      show=False),
    ]

    # -- State ---------------------------------------------------------------

    _online: reactive[bool] = reactive(True)
    _start_time: float
    _ticker: Timer | None
    _audit_keys: deque[RowKey]

    def __init__(self) -> None:
        super().__init__()
        self._start_time = time.monotonic()
        self._ticker = None
        self._audit_keys: deque[RowKey] = deque(maxlen=_MAX_TABLE_ROWS)

    # -- Layout --------------------------------------------------------------

    def compose(self) -> ComposeResult:
        # Top status bar (1 line, no Textual Header widget to avoid clock unicode)
        with Horizontal(id="topbar"):
            yield Static("Pxtly", id="topbar-title")
            yield Static(
                f"{settings.environment.upper()}  //  ONLINE",
                id="topbar-env",
            )

        # Main body: two columns
        with Horizontal(id="body"):

            # Left column -- health grid + live stream
            with Vertical(id="left-col"):
                with Vertical(id="health-pane"):
                    yield PaneHeader("NETWORK HEALTH")
                    yield HealthGrid(id="health-grid")

                with Vertical(id="stream-pane"):
                    yield PaneHeader("LIVE STREAM", id="stream-header")
                    yield RichLog(
                        id="sse-log",
                        max_lines=settings.max_sse_events,
                        markup=True,
                        wrap=False,
                        highlight=False,
                    )

            # Right column -- event table + telemetry
            with Vertical(id="right-col"):
                with Vertical(id="audit-pane"):
                    yield PaneHeader("RECENT EVENTS")
                    yield DataTable(
                        id="audit-table",
                        cursor_type="row",
                        zebra_stripes=True,
                    )

                with Vertical(id="stats-pane"):
                    yield PaneHeader("TELEMETRY")
                    yield StatsBar(id="stats-bar")

        yield Footer()

    # -- Lifecycle -----------------------------------------------------------

    def on_mount(self) -> None:
        self._init_audit_table()
        self._apply_online_state(is_online())
        register_callback(self._on_network_change)
        sse_client.start()
        self._ticker = self.set_interval(1.0, self._tick)
        # The audit table starts empty each session — events accumulate as
        # they arrive on the SSE stream. Historical seeding was removed when
        # the SQLite audit_log table was dropped (see cli/cache.py).

    async def on_unmount(self) -> None:
        if self._ticker is not None:
            self._ticker.stop()
        unregister_callback(self._on_network_change)
        await sse_client.stop()

    # -- Timer ---------------------------------------------------------------

    async def _tick(self) -> None:
        """1 Hz heartbeat: drain SSE queue + refresh all panels."""
        # Drain up to 50 SSE events per tick
        for _ in range(50):
            event = await sse_client.get_event()
            if event is None:
                break
            self._log_sse_event(event)
            self._push_audit_row(event)

        # Refresh health grid
        self._safe_call(lambda: self.query_one("#health-grid", HealthGrid).refresh_health())

        # Refresh telemetry bar
        uptime = time.monotonic() - self._start_time
        self._safe_call(
            lambda: self.query_one("#stats-bar", StatsBar).refresh(
                sse_client.events_received, uptime
            )
        )

        # Update stream header with live connection state
        connected   = sse_client.is_connected
        conn_col    = "green" if connected else "yellow"
        conn_label  = "CONNECTED" if connected else "RECONNECTING"
        self._safe_call(
            lambda: self.query_one("#stream-header", PaneHeader).update(
                f"[{conn_col}]{conn_label}[/]"
                f"  [dim]|[/]  LIVE STREAM"
                f"  [dim]|[/]  [{conn_col}]{sse_client.events_received:,} events[/]"
            )
        )

    # -- Audit table ---------------------------------------------------------

    def _init_audit_table(self) -> None:
        table = self.query_one("#audit-table", DataTable)
        table.add_columns("Time", "Type", "Payload")

    def _push_audit_row(self, event: SseEvent) -> None:
        """
        Append one row; evict oldest row once table exceeds _MAX_TABLE_ROWS.
        Uses explicit RowKey tracking -- never get_row_at()[0].
        """
        try:
            table   = self.query_one("#audit-table", DataTable)
            ts      = datetime.fromtimestamp(event.ts).strftime("%H:%M:%S")
            etype   = event.label()
            payload = (str(event.payload)[:80] if event.payload else event.raw[:80])
            key = table.add_row(ts, etype, payload)
            self._audit_keys.append(key)

            # Evict oldest rows beyond the cap
            while table.row_count > _MAX_TABLE_ROWS and self._audit_keys:
                oldest = self._audit_keys.popleft()
                try:
                    table.remove_row(oldest)
                except Exception:
                    break
        except Exception as exc:
            log.debug("_push_audit_row: %s", exc)

    # -- SSE log rendering ---------------------------------------------------

    def _log_sse_event(self, event: SseEvent) -> None:
        try:
            log_widget = self.query_one("#sse-log", RichLog)
            ts         = datetime.fromtimestamp(event.ts).strftime("%H:%M:%S.%f")[:-3]
            etype      = event.label()
            color      = _EVENT_COLORS.get(etype, _DEFAULT_EVENT_COLOR)
            payload    = (str(event.payload)[:120] if event.payload else event.raw[:120])
            log_widget.write(
                f"[dim]{ts}[/]  [{color}]{etype:<16}[/]  [white]{payload}[/]"
            )
        except Exception as exc:
            log.debug("_log_sse_event: %s", exc)

    # -- Network state -------------------------------------------------------

    def _on_network_change(self, online: bool) -> None:
        """Called from a foreign thread -- forward to Textual thread."""
        self.call_from_thread(self._apply_online_state, online)

    def _apply_online_state(self, online: bool) -> None:
        self._online = online
        env    = settings.environment.upper()
        col    = "green" if online else "red"
        status = "ONLINE" if online else "OFFLINE"
        self._safe_call(
            lambda: self.query_one("#topbar-env", Static).update(
                f"{env}  //  [{col}]{status}[/]"
            )
        )

    # -- Actions -------------------------------------------------------------

    def action_reconnect_sse(self) -> None:
        sse_client.start()
        self._safe_call(
            lambda: self.query_one("#sse-log", RichLog).write(
                "[yellow dim]-- manual reconnect triggered --[/]"
            )
        )

    def action_clear_events(self) -> None:
        def _do() -> None:
            self.query_one("#sse-log", RichLog).clear()
            table = self.query_one("#audit-table", DataTable)
            table.clear()
            self._audit_keys.clear()
        self._safe_call(_do)

    async def action_quit(self) -> None:
        await sse_client.stop()
        self.exit()

    # -- Utilities -----------------------------------------------------------

    @staticmethod
    def _safe_call(fn: Callable[[], None]) -> None:
        """Execute fn, swallow and log any exception so the app never crashes."""
        try:
            fn()
        except Exception as exc:
            log.debug("_safe_call: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def launch_dashboard() -> None:
    """
    Launch the full-screen dashboard.
    Blocks until the user quits (Q / Ctrl+C).
    """
    QxDashboard().run()
