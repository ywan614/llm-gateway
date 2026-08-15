from __future__ import annotations

import argparse
import json
import uuid

import httpx

from llm_central_gateway.settings import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the local gateway")
    parser.add_argument("--live", action="store_true", help="send one short paid model request")
    args = parser.parse_args()
    settings = load_settings()
    base_url = "http://127.0.0.1:8080"

    for path in ("/health", "/api/v1/health", "/api/v1/ready"):
        response = httpx.get(base_url + path, timeout=20)
        response.raise_for_status()
        print(f"{path}: ok")

    if not args.live:
        return

    suffix = uuid.uuid4().hex[:8]
    admin_headers = {"Authorization": f"Bearer {settings.admin_api_token}"}
    response = httpx.post(
        base_url + "/api/v1/admin/users",
        headers=admin_headers,
        json={"name": "Automated Smoke Test", "email": f"smoke-{suffix}@local.invalid"},
        timeout=30,
    )
    response.raise_for_status()
    user_id = response.json()["id"]
    response = httpx.post(
        base_url + f"/api/v1/admin/users/{user_id}/keys",
        headers=admin_headers,
        json={"alias": f"smoke-{suffix}", "rpm": 10, "tpm": 10_000},
        timeout=30,
    )
    response.raise_for_status()
    api_key = response.json()["api_key"]

    chunks = 0
    completed = False
    with httpx.stream(
        "POST",
        base_url + "/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": settings.public_model_name,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": 8,
            "temperature": 0,
            "stream": True,
        },
        timeout=60,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                completed = True
                continue
            json.loads(data)
            chunks += 1
    if not completed or chunks == 0:
        raise RuntimeError("Streaming response did not complete")
    print(f"streaming model request: ok ({chunks} chunks)")


if __name__ == "__main__":
    main()
