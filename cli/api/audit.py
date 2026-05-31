"""
cli/api/audit.py
----------------
On-chain audit trail + LLM-driven compliance reports.

Endpoints (prefix /api/v1/audit):
  GET    ""                              (paginated audit log)
  GET    /asset/{asset_id}
  POST   /report/generate/{asset_id}     -> {task_id}
  GET    /report/status/{task_id}
  POST   /fraud/scan                     (Celery — returns task ref)
"""
from __future__ import annotations

from typing import Any

from cli.http import request
from cli.settings import settings


def _u(path: str = "") -> str:
    return f"{settings.api_url}/audit{path}"


async def list_log(
    limit: int = 50,
    offset: int = 0,
    actor: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if actor:
        params["actor"] = actor
    return (await request("GET", _u(""), params=params)).json()


async def asset_trail(asset_id: str) -> list[dict[str, Any]]:
    return (await request(
        "GET", _u(f"/asset/{asset_id}"),
        cache_key=f"audit:asset:{asset_id}", cache_ttl=300.0,
    )).json()


async def generate_report(asset_id: str) -> dict[str, Any]:
    """Kick off the async LaTeX-rendered audit report. Returns {task_id}."""
    return (await request("POST", _u(f"/report/generate/{asset_id}"))).json()


async def report_status(task_id: str) -> dict[str, Any]:
    return (await request("GET", _u(f"/report/status/{task_id}"))).json()


async def fraud_scan(payload: dict[str, Any]) -> dict[str, Any]:
    return (await request("POST", _u("/fraud/scan"), json=payload)).json()
