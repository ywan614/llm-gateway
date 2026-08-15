from __future__ import annotations

import os
import subprocess
import sys

from .settings import load_settings


def main() -> None:
    settings = load_settings()
    environment = os.environ.copy()
    environment.update(
        {
            "DASHSCOPE_API_KEY": settings.dashscope_api_key,
            "DATABASE_URL": settings.litellm_docker_postgres_uri,
            "LITELLM_MASTER_KEY": settings.litellm_master_key,
            "LITELLM_SALT_KEY": settings.litellm_salt_key,
            "MODEL_NAME": settings.provider_model_name,
            "LITELLM_MODEL": f"openai/{settings.provider_model_name}",
            "PUBLIC_MODEL_NAME": settings.public_model_name,
            "MODEL_BASE_URL": settings.model_base_url,
            "MODEL_TIMEOUT_SECONDS": str(settings.model_timeout_seconds),
            "MODEL_MAX_RETRIES": str(settings.model_max_retries),
            "HOST_UID": str(os.getuid()),
            "HOST_GID": str(os.getgid()),
        }
    )
    command = ["docker", "compose", *sys.argv[1:]]
    raise SystemExit(subprocess.run(command, env=environment, check=False).returncode)
