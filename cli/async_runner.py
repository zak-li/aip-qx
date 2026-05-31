"""
cli/async_runner.py
-------------------
Safe asyncio.run() wrapper for synchronous (Typer / prompt_toolkit) callers.
Always creates a fresh event loop -- never reuses a running one.

Pending task cancellation captures each task exception individually
to prevent CancelledError from masking real errors on shutdown.
"""
from __future__ import annotations

import asyncio
import sys
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run(coro: Coroutine[Any, Any, T]) -> T:
    """Execute an async coroutine from a synchronous context."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        finally:
            loop.close()

