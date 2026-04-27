"""Client IP extraction with proxy header support.

The app sits behind nginx / a load balancer in production, so
`request.client.host` is the proxy address. The real client IP is in
`X-Forwarded-For` (or `X-Real-IP`) — but those headers are forgeable when
we're not behind a trusted proxy. The TRUSTED_PROXY_NETS env var lists CIDRs
of proxies whose forwarded headers can be trusted; from any other source we
fall back to the direct peer address.

Usage in middleware:
    request.state.client_ip = extract_client_ip(request)
    set_request_ip(request.state.client_ip)   # propagate to deep callees
Usage in audit log inserts:
    ip_address=get_request_ip()
"""
from __future__ import annotations

import contextvars
import ipaddress
import os
from collections.abc import Iterable

from fastapi import Request


# Default sentinel used when no request context is available — e.g. background
# Celery tasks or startup-time checks. Distinguishable from a real address.
_NO_REQUEST_SENTINEL = "internal"

_request_ip_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_ip", default=_NO_REQUEST_SENTINEL
)


def set_request_ip(ip: str) -> None:
    _request_ip_var.set(ip or _NO_REQUEST_SENTINEL)


def get_request_ip() -> str:
    return _request_ip_var.get()


def _parse_networks(raw: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for token in (t.strip() for t in raw.split(",")):
        if not token:
            continue
        try:
            nets.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            continue
    return nets


_TRUSTED_PROXY_NETS = _parse_networks(
    os.getenv("TRUSTED_PROXY_NETS", "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
)


def _peer_in_trusted_nets(peer_ip: str, nets: Iterable[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> bool:
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(addr in n for n in nets)


def extract_client_ip(request: Request) -> str:
    """Return the best-known client IP for a given request.

    - If the direct peer is in a trusted proxy network, use the leftmost entry
      of `X-Forwarded-For` (or `X-Real-IP`).
    - Otherwise return the direct peer address.
    - Falls back to "unknown" if neither is available.
    """
    peer = request.client.host if request.client else None

    if peer and _peer_in_trusted_nets(peer, _TRUSTED_PROXY_NETS):
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
        x_real = request.headers.get("X-Real-IP")
        if x_real:
            return x_real.strip()

    return peer or "unknown"
