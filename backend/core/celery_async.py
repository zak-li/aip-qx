"""Safely execute async coroutines from Celery task bodies.

Using ``asyncio.run()`` inside a Celery worker is unsafe when the worker pool
shares a process-wide event loop (gevent, eventlet, asyncio pools). Creating a
fresh loop per task call avoids deadlocks and guarantees clean teardown of
generators and child tasks.
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

_T = TypeVar("_T")

CELERY_AUDIT_IP = "internal"


def run_async(coro: Coroutine[Any, Any, _T]) -> _T:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
