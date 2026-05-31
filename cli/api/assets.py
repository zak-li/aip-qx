"""
cli/api/assets.py
-----------------
Asset lifecycle on the Pxtly ledger.

Endpoints (prefix /api/v1/assets):
  POST   /tokenize
  POST   /transfer
  POST   /freeze
  POST   /unfreeze
  GET    /{asset_id}
  GET    /{asset_id}/history
  POST   /{asset_id}/valuate
  GET    /{asset_id}/valuations
  GET    ""              (list)
"""
from __future__ import annotations

from typing import Any

from cli.http import request
from cli.settings import settings


def _u(path: str = "") -> str:
    return f"{settings.api_url}/assets{path}"


async def tokenize(payload: dict[str, Any]) -> dict[str, Any]:
    return (await request("POST", _u("/tokenize"), json=payload)).json()


async def transfer(payload: dict[str, Any]) -> dict[str, Any]:
    return (await request("POST", _u("/transfer"), json=payload)).json()


async def freeze(payload: dict[str, Any]) -> dict[str, Any]:
    return (await request("POST", _u("/freeze"), json=payload)).json()


async def unfreeze(payload: dict[str, Any]) -> dict[str, Any]:
    return (await request("POST", _u("/unfreeze"), json=payload)).json()


async def get(asset_id: str) -> dict[str, Any]:
    return (await request(
        "GET", _u(f"/{asset_id}"),
        cache_key=f"asset:{asset_id}", cache_ttl=300.0,
    )).json()


async def history(asset_id: str) -> list[dict[str, Any]]:
    return (await request(
        "GET", _u(f"/{asset_id}/history"),
        cache_key=f"asset:history:{asset_id}", cache_ttl=120.0,
    )).json()


async def valuate(asset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return (await request("POST", _u(f"/{asset_id}/valuate"), json=payload)).json()


async def valuations(asset_id: str) -> list[dict[str, Any]]:
    return (await request(
        "GET", _u(f"/{asset_id}/valuations"),
        cache_key=f"asset:val:{asset_id}", cache_ttl=120.0,
    )).json()


async def list_assets(
    status: str | None = None,
    asset_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    if asset_type:
        params["asset_type"] = asset_type
    return (await request("GET", _u(""), params=params)).json()
