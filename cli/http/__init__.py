"""
cli/http/
---------
HTTP transport layer for the Pxtly CLI.

  - exceptions : typed error hierarchy raised on non-2xx
  - client     : the shared async request() entrypoint
  - auth       : Bearer-token injection + transparent refresh on 401
"""
from __future__ import annotations

from cli.http.client import (
    CachedResponse,
    ResponseLike,
    request,
)
from cli.http.exceptions import (
    AuthError,
    NetworkError,
    NotFoundError,
    PxtlyApiError,
    ServerError,
    ValidationError,
)

__all__ = [
    "AuthError",
    "CachedResponse",
    "NetworkError",
    "NotFoundError",
    "PxtlyApiError",
    "ResponseLike",
    "ServerError",
    "ValidationError",
    "request",
]
