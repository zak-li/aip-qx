"""
cli/api/transactions.py — Off-chain transaction history.

Endpoints (prefix /api/v1/transactions):
  GET   ""
  GET   /stats/summary
  GET   /{tx_ref}
"""
from __future__ import annotations

from typing import Any

from cli.http import request
from cli.settings import settings


def _u(path: str = "") -> str:
    return f"{settings.api_url}/transactions{path}"


async def list_tx(
    asset_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if asset_id:
        params["asset_id"] = asset_id
    return (await request("GET", _u(""), params=params)).json()


async def stats() -> dict[str, Any]:
    return (await request(
        "GET", _u("/stats/summary"),
        cache_key="tx:stats", cache_ttl=60.0,
    )).json()


async def get(tx_ref: str) -> dict[str, Any]:
    return (await request(
        "GET", _u(f"/{tx_ref}"),
        cache_key=f"tx:{tx_ref}", cache_ttl=300.0,
    )).json()
