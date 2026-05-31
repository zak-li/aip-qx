"""
cli/api/organizations.py — Org & user directory.

Endpoints (prefix /api/v1/organizations):
  GET   ""
  GET   /users
  GET   /{org_id}/portfolio
"""
from __future__ import annotations

from typing import Any

from cli.http import request
from cli.settings import settings


def _u(path: str = "") -> str:
    return f"{settings.api_url}/organizations{path}"


async def list_orgs() -> list[dict[str, Any]]:
    return (await request(
        "GET", _u(""),
        cache_key="orgs:list", cache_ttl=300.0,
    )).json()


async def list_users(
    role: str | None = None,
    country: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if role:
        params["role"] = role
    if country:
        params["country"] = country
    return (await request("GET", _u("/users"), params=params)).json()


async def portfolio(org_id: str) -> dict[str, Any]:
    return (await request(
        "GET", _u(f"/{org_id}/portfolio"),
        cache_key=f"orgs:portfolio:{org_id}", cache_ttl=120.0,
    )).json()
