import json
import logging
import re

from backend.config import settings

SENSITIVE_FIELDS = {"password", "token", "secret", "key", "authorization", "hashed_password", "private_key"}
SENSITIVE_PATTERN = re.compile(
    r"(password|token|secret|key|authorization|hashed_password|private_key)\s*[:=]\s*\S+",
    re.IGNORECASE,
)

class SensitiveFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = SENSITIVE_PATTERN.sub(
                lambda m: m.group().split("=")[0].split(":")[0] + "=[REDACTED]",
                record.msg,
            )
        if hasattr(record, "args") and record.args:
            sanitized = []
            for arg in record.args if isinstance(record.args, (list, tuple)) else [record.args]:
                if isinstance(arg, str):
                    arg = SENSITIVE_PATTERN.sub(
                        lambda m: m.group().split("=")[0].split(":")[0] + "=[REDACTED]",
                        arg,
                    )
                sanitized.append(arg)
            record.args = tuple(sanitized)
        return True

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, str | int | None] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "service": "rwa-api",
            "message": record.getMessage(),
        }

        if hasattr(record, "trace_id"):
            log_obj["trace_id"] = record.trace_id

        return json.dumps(log_obj)

def setup_logging(log_level: str = "INFO") -> None:
    effective_level = log_level.upper()

    if settings.environment == "production" and effective_level == "DEBUG":
        effective_level = "INFO"

    root_logger = logging.getLogger()
    root_logger.setLevel(effective_level)

    if root_logger.handlers:
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JSONFormatter())
    stream_handler.addFilter(SensitiveFilter())
    root_logger.addHandler(stream_handler)

    logging.getLogger("grpc").setLevel(logging.WARNING)
    logging.getLogger("hfc").setLevel(logging.WARNING)
