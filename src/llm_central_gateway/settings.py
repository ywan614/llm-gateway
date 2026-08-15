from __future__ import annotations

import configparser
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path.cwd().resolve()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.ini"


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


class CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr: str) -> str:
        return optionstr


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    environment: str
    host: str
    port: int
    admin_api_token: str
    postgres_uri: str
    redis_uri: str
    litellm_admin_url: str
    litellm_database_name: str
    litellm_master_key: str
    litellm_salt_key: str
    dashscope_api_key: str
    public_model_name: str
    provider_model_name: str
    model_base_url: str
    model_timeout_seconds: int
    model_max_retries: int
    default_rpm: int
    default_tpm: int
    default_max_parallel_requests: int
    log_dir: Path
    log_file_name: str
    log_level: str
    log_max_bytes: int
    log_backup_count: int
    log_value_max_length: int
    log_console: bool
    log_include_payloads: bool

    @property
    def async_postgres_uri(self) -> str:
        uri = self.docker_postgres_uri if Path("/.dockerenv").exists() else self.postgres_uri
        return _replace_scheme(uri, "postgresql+psycopg")

    @property
    def docker_postgres_uri(self) -> str:
        parsed = urlsplit(self.postgres_uri)
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return self.postgres_uri
        auth = f"{parsed.netloc.rsplit('@', 1)[0]}@" if "@" in parsed.netloc else ""
        port = f":{parsed.port}" if parsed.port else ""
        return urlunsplit(
            (parsed.scheme, f"{auth}host.docker.internal{port}", parsed.path, parsed.query, "")
        )

    @property
    def litellm_docker_postgres_uri(self) -> str:
        parsed = urlsplit(self.docker_postgres_uri)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                f"/{self.litellm_database_name}",
                parsed.query,
                parsed.fragment,
            )
        )


def load_settings(path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    parser = CaseSensitiveConfigParser(interpolation=None)
    if not path.is_file():
        raise ConfigurationError(f"Configuration file is missing: {path}")
    parser.read(path, encoding="utf-8")

    def required(section: str, key: str) -> str:
        try:
            value = parser[section][key].strip()
        except KeyError as exc:
            raise ConfigurationError(f"Missing configuration field: [{section}] {key}") from exc
        if not value:
            raise ConfigurationError(f"Blank configuration field: [{section}] {key}")
        return value

    def integer(section: str, key: str, minimum: int = 0) -> int:
        raw = required(section, key)
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigurationError(f"Invalid integer field: [{section}] {key}") from exc
        if value < minimum:
            raise ConfigurationError(f"Out-of-range field: [{section}] {key}")
        return value

    try:
        console = parser.getboolean("logging", "LOG_CONSOLE")
        payloads = parser.getboolean("logging", "LOG_INCLUDE_PAYLOADS")
    except (ValueError, configparser.Error) as exc:
        raise ConfigurationError("Invalid logging boolean field") from exc

    log_dir = Path(required("logging", "LOG_DIR"))
    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir

    settings = Settings(
        app_name=required("application", "APP_NAME"),
        environment=required("application", "ENVIRONMENT"),
        host=required("application", "HOST"),
        port=integer("application", "PORT", 1),
        admin_api_token=required("application", "ADMIN_API_TOKEN"),
        postgres_uri=required("postgres", "POSTGRES_URI"),
        redis_uri=required("redis", "REDIS_URI"),
        litellm_admin_url=required("litellm", "LITELLM_ADMIN_URL").rstrip("/"),
        litellm_database_name=required("litellm", "LITELLM_DATABASE_NAME"),
        litellm_master_key=required("litellm", "LITELLM_MASTER_KEY"),
        litellm_salt_key=required("litellm", "LITELLM_SALT_KEY"),
        dashscope_api_key=required("openai", "OPENAI_API_KEY"),
        public_model_name=required("model", "PUBLIC_MODEL_NAME"),
        provider_model_name=required("model", "MODEL_NAME"),
        model_base_url=required("model", "MODEL_BASE_URL").rstrip("/"),
        model_timeout_seconds=integer("model", "MODEL_TIMEOUT_SECONDS", 1),
        model_max_retries=integer("model", "MODEL_MAX_RETRIES"),
        default_rpm=integer("limits", "DEFAULT_RPM", 1),
        default_tpm=integer("limits", "DEFAULT_TPM", 1),
        default_max_parallel_requests=integer("limits", "DEFAULT_MAX_PARALLEL_REQUESTS", 1),
        log_dir=log_dir,
        log_file_name=required("logging", "LOG_FILE_NAME"),
        log_level=required("logging", "LOG_LEVEL").upper(),
        log_max_bytes=integer("logging", "LOG_MAX_BYTES", 1),
        log_backup_count=integer("logging", "LOG_BACKUP_COUNT", 1),
        log_value_max_length=integer("logging", "LOG_VALUE_MAX_LENGTH", 100),
        log_console=console,
        log_include_payloads=payloads,
    )
    if settings.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError("Invalid field: [logging] LOG_LEVEL")
    return settings


def initialize_missing_config(path: Path = DEFAULT_CONFIG_PATH) -> list[str]:
    """Add safe defaults and generated local secrets without replacing existing values."""
    parser = CaseSensitiveConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    changed: list[str] = []

    defaults: dict[str, dict[str, str]] = {
        "application": {
            "APP_NAME": "llm-central-gateway",
            "ENVIRONMENT": "development",
            "HOST": "127.0.0.1",
            "PORT": "8000",
            "ADMIN_API_TOKEN": secrets.token_urlsafe(32),
        },
        "redis": {"REDIS_URI": "redis://redis:6379/0"},
        "litellm": {
            "LITELLM_ADMIN_URL": "http://litellm:4000",
            "LITELLM_DATABASE_NAME": "llm_gateway_litellm",
            "LITELLM_MASTER_KEY": f"sk-{secrets.token_urlsafe(32)}",
            "LITELLM_SALT_KEY": secrets.token_urlsafe(32),
        },
        "limits": {
            "DEFAULT_RPM": "60",
            "DEFAULT_TPM": "100000",
            "DEFAULT_MAX_PARALLEL_REQUESTS": "10",
        },
    }
    model_defaults = {
        "PUBLIC_MODEL_NAME": "qwen-plus",
        "MODEL_TIMEOUT_SECONDS": "120",
        "MODEL_MAX_RETRIES": "1",
    }
    logging_defaults = {"LOG_INCLUDE_PAYLOADS": "false"}
    defaults["model"] = model_defaults
    defaults["logging"] = logging_defaults

    for section, values in defaults.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in values.items():
            if not parser.has_option(section, key) or not parser[section][key].strip():
                parser[section][key] = value
                changed.append(f"[{section}] {key}")

    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle, space_around_delimiters=False)
    path.chmod(0o600)
    return changed


def _replace_scheme(uri: str, scheme: str) -> str:
    parsed = urlsplit(uri)
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))
