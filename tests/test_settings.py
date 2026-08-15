from pathlib import Path

import pytest

from llm_central_gateway.settings import ConfigurationError, load_settings


def test_missing_config_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="missing"):
        load_settings(tmp_path / "missing.ini")


def test_example_config_is_complete() -> None:
    settings = load_settings(Path("config.example.ini"))
    assert settings.public_model_name == "qwen-plus"
    assert settings.log_include_payloads is False
    assert "host.docker.internal" in settings.docker_postgres_uri
    assert settings.litellm_docker_postgres_uri.endswith("/llm_gateway_litellm")
