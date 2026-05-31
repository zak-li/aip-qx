"""
cli/settings.py
---------------
Global application settings.

Precedence (highest to lowest):
    1. PXTLY_* environment variables
    2. ~/.pxtly/config.json
    3. Field defaults

Secrets are NEVER read from config.json — only from environment. The
config file is for non-secret state (api_url, realm name, TLS bundle path…).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CLI_DIR: Path = Path.home() / ".pxtly"
_CONFIG_FILE: Path = CLI_DIR / "config.json"
_LOG_DIR: Path = CLI_DIR / "logs"
_DB_PATH: Path = CLI_DIR / "cache.db"
_AUDIT_LOG: Path = CLI_DIR / "audit.log"

# Non-secret keys allowed in config.json. Anything else is rejected to keep
# secrets out of the on-disk file.
_PERSISTABLE_KEYS = {
    "api_url",
    "sse_url",
    "keycloak_url",
    "keycloak_realm",
    "keycloak_client_id",
    "environment",
    "http_timeout",
    "http_verify_ssl",
    "ca_bundle_path",
    "sse_reconnect_delay",
    "max_sse_events",
}


def _load_json_file() -> dict[str, object]:
    if not _CONFIG_FILE.exists():
        return {}
    try:
        raw = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {k: v for k, v in raw.items() if k in _PERSISTABLE_KEYS}


class Settings(BaseSettings):
    """
    All fields can be overridden via PXTLY_<FIELD>=... env vars.

    Secrets that *must* come from the environment (never persisted):
      - PXTLY_KEYCLOAK_CLIENT_SECRET  (optional, only for confidential clients)
    """

    model_config = SettingsConfigDict(
        env_prefix="PXTLY_",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Backend ─────────────────────────────────────────────────────────────
    # The API runs as a bare FastAPI on 8000 (no in-process TLS termination
    # — Keycloak on 8443 is the only TLS service). Override with
    # PXTLY_API_URL=https://… if you put a reverse proxy in front.
    api_url: str = Field(default="http://10.10.10.150:8000/api/v1")
    sse_url: str = Field(default="http://10.10.10.150:8000/api/v1/events/stream")

    # ── Keycloak ────────────────────────────────────────────────────────────
    keycloak_url: str = Field(default="https://10.10.10.150:8443")
    keycloak_realm: str = Field(default="qx")
    keycloak_client_id: str = Field(default="qx-api")
    # Only set when using a confidential client. Public clients (PKCE) leave
    # this empty. Read from env only; never persisted.
    keycloak_client_secret: str | None = Field(default=None, repr=False)

    # ── Transport security ──────────────────────────────────────────────────
    environment: Literal["production", "staging", "development"] = Field(default="production")
    http_timeout: float = Field(default=30.0, ge=1.0, le=300.0)
    # Secure by default. Override via PXTLY_HTTP_VERIFY_SSL=false at your own risk.
    http_verify_ssl: bool = Field(default=True)
    # Optional path to a CA bundle that signs the Keycloak / API certificates
    # (e.g. the self-signed CA from `stack/keycloak/gen-tls.sh`). When set,
    # this is used as the trust anchor instead of the system store.
    ca_bundle_path: str | None = Field(default=None)

    # ── Real-time ───────────────────────────────────────────────────────────
    sse_reconnect_delay: float = Field(default=5.0, ge=1.0, le=60.0)
    max_sse_events: int = Field(default=200, ge=10, le=2000)

    # ── Validators ──────────────────────────────────────────────────────────

    @field_validator("ca_bundle_path")
    @classmethod
    def _resolve_ca_bundle(cls, v: str | None) -> str | None:
        if not v:
            return None
        path = Path(v).expanduser()
        if not path.exists():
            # Don't fail config load — defer the error to first HTTPS call.
            return str(path)
        return str(path.resolve())

    @field_validator("http_verify_ssl", mode="before")
    @classmethod
    def _parse_bool(cls, v):
        if isinstance(v, str):
            return v.strip().lower() not in {"false", "0", "no", "off"}
        return v

    # ── Lifecycle ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> Settings:
        return cls(**_load_json_file())

    def persist(self) -> None:
        """Write non-secret fields to ~/.pxtly/config.json."""
        CLI_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            k: v for k, v in self.model_dump().items()
            if k in _PERSISTABLE_KEYS and v is not None
        }
        _CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(_CONFIG_FILE, 0o600)
        except OSError:
            pass

    # ── Convenience ─────────────────────────────────────────────────────────

    @property
    def log_dir(self) -> Path:
        return _LOG_DIR

    @property
    def db_path(self) -> Path:
        return _DB_PATH

    @property
    def audit_log_path(self) -> Path:
        return _AUDIT_LOG

    @property
    def host_label(self) -> str:
        from urllib.parse import urlparse
        try:
            return urlparse(self.api_url).netloc or self.api_url
        except Exception:
            return self.api_url

    @property
    def verify_param(self):
        """Value to pass as httpx `verify=` — bool or CA bundle path."""
        if not self.http_verify_ssl:
            return False
        if self.ca_bundle_path:
            return self.ca_bundle_path
        return True

    @property
    def is_confidential_client(self) -> bool:
        return bool(self.keycloak_client_secret)


settings: Settings = Settings.load()
