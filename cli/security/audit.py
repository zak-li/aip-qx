"""
cli/security/audit.py
---------------------
Append-only local audit log for the Pxtly CLI.

Each command execution writes one JSON line to ~/.pxtly/audit.log:

    {"ts": 1717084821.39, "actor": "thomas.martin@bank01.fr",
     "command": "assets transfer", "args": {"asset_id": "RWA-OBL-…"},
     "result": "ok", "status_code": 201}

Secrets (passwords, tokens, client secrets, raw request bodies) are
never written. Arguments are filtered by name; keys matching any of the
patterns in `_REDACT_KEYS` are replaced with `"<redacted>"`.

The file is created with 0o600 (rw owner only) on POSIX. On Windows the
default ACL inherited from the user profile is what applies.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REDACT_KEYS = {
    "password",
    "client_secret",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "private_key",
    "code_verifier",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("<redacted>" if k.lower() in _REDACT_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def audit_event(
    command: str,
    *,
    args: dict[str, Any] | None = None,
    actor: str | None = None,
    result: str = "ok",
    status_code: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write one audit line. Best-effort: never raises."""
    from cli.settings import settings

    record = {
        "ts": time.time(),
        "actor": actor or "",
        "command": command,
        "args": _redact(args or {}),
        "result": result,
        "status_code": status_code,
    }
    if extra:
        record["extra"] = _redact(extra)

    try:
        path: Path = settings.audit_log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not path.exists()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        if new_file:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
    except Exception as exc:
        # Audit is best-effort; never break a command because logging failed.
        log.debug("Audit write failed: %s", exc)


def recent_events(n: int = 50) -> Iterable[dict[str, Any]]:
    """Yield the last `n` events, newest first."""
    from cli.settings import settings

    path = settings.audit_log_path
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines[-n:]):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
