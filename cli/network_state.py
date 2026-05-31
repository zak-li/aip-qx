"""
cli/network_state.py
--------------------
Thread-safe, observable network-state singleton.

Callbacks are dispatched AFTER releasing _lock to prevent deadlock
when a callback calls is_online() re-entrantly.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

_lock = threading.Lock()
_online: bool | None = None
_callbacks: list[Callable[[bool], None]] = []


def is_online() -> bool:
    with _lock:
        return _online if _online is not None else True


def set_online(value: bool) -> None:
    global _online
    callbacks_to_fire: list[Callable[[bool], None]] = []
    with _lock:
        if _online != value:
            _online = value
            callbacks_to_fire = list(_callbacks)

    if callbacks_to_fire:
        log.info("Network state -> %s", "ONLINE" if value else "OFFLINE")
        for cb in callbacks_to_fire:
            try:
                cb(value)
            except Exception as exc:
                log.warning("Network callback error: %s", exc)


def register_callback(cb: Callable[[bool], None]) -> None:
    with _lock:
        if cb not in _callbacks:
            _callbacks.append(cb)


def unregister_callback(cb: Callable[[bool], None]) -> None:
    with _lock:
        try:
            _callbacks.remove(cb)
        except ValueError:
            pass

