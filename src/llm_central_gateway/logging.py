from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .settings import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_SENSITIVE = {"api_key", "authorization", "cookie", "password", "secret", "token"}


class JsonFormatter(logging.Formatter):
    def __init__(self, max_length: int) -> None:
        super().__init__()
        self.max_length = max_length

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "application.log"),
            "message": record.getMessage()[: self.max_length],
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        data = getattr(record, "data", None)
        if data is not None:
            payload["data"] = _redact(data, self.max_length)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)[: self.max_length]
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> Path:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.log_dir / settings.log_file_name
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_gateway_handler", False):
            root.removeHandler(handler)
            handler.close()
    formatter = JsonFormatter(settings.log_value_max_length)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler._gateway_handler = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    if settings.log_console:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console._gateway_handler = True  # type: ignore[attr-defined]
        root.addHandler(console)
    root.setLevel(settings.log_level)
    return log_path


def bind_request_id(request_id: str) -> Token[str | None]:
    return request_id_var.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    request_id_var.reset(token)


def _redact(value: Any, max_length: int) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if any(part in str(key).lower() for part in _SENSITIVE)
            else _redact(item, max_length)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item, max_length) for item in value]
    if isinstance(value, str) and len(value) > max_length:
        return f"{value[:max_length]}...[truncated {len(value) - max_length} chars]"
    return value
