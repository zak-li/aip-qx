import json
import logging
import re

from core.config import settings

# ── Sensitive value redaction ────────────────────────────────────────────────

SENSITIVE_PATTERN = re.compile(
    r"(password|token|secret|api_key|authorization|hashed_password|private_key|vault_token)"
    r"\s*[:=]\s*\S+",
    re.IGNORECASE,
)

# Mask an email like `alice.smith@example.com` → `a******@example.com`.
# We keep the first character of the local-part and the full domain so logs
# remain useful for debugging without leaking PII.
EMAIL_PATTERN = re.compile(
    r"\b([A-Za-z0-9])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"
)


def _redact_kv(match: re.Match[str]) -> str:
    text = match.group(0)
    sep = ":" if ":" in text else "="
    key = text.split(sep, 1)[0]
    return f"{key}{sep}[REDACTED]"


def _mask_email(match: re.Match[str]) -> str:
    return f"{match.group(1)}***{match.group(2)}"


def _scrub(text: str) -> str:
    text = SENSITIVE_PATTERN.sub(_redact_kv, text)
    text = EMAIL_PATTERN.sub(_mask_email, text)
    return text


class SensitiveFilter(logging.Filter):
    """Redact secrets and mask emails in log messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        if record.args:
            args_iter = record.args if isinstance(record.args, list | tuple) else (record.args,)
            sanitized = tuple(_scrub(a) if isinstance(a, str) else a for a in args_iter)
            record.args = sanitized
        return True


# ── Structured JSON formatter ────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record.

    Includes exc_info/stack_info when present so unhandled exceptions are
    captured by the log shipper instead of being silently dropped.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "service": "rwa-api",
            "message": record.getMessage(),
        }

        for attr in ("trace_id", "user_id", "request_id"):
            value = getattr(record, attr, None)
            if value is not None:
                log_obj[attr] = value

        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_obj["stack"] = self.formatStack(record.stack_info)

        return json.dumps(log_obj, default=str, ensure_ascii=False)


# ── setup ────────────────────────────────────────────────────────────────────

def setup_logging(log_level: str = "INFO") -> None:
    effective_level = log_level.upper()

    if settings.environment == "production" and effective_level == "DEBUG":
        effective_level = "INFO"

    root_logger = logging.getLogger()
    root_logger.setLevel(effective_level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JSONFormatter())
    stream_handler.addFilter(SensitiveFilter())
    root_logger.addHandler(stream_handler)

    # Quieten chatty third-party loggers.
    for noisy in ("grpc", "hfc", "sqlalchemy.engine.Engine", "uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
