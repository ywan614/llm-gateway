from __future__ import annotations

from typing import Any

import httpx


class LiteLLMAdminError(RuntimeError):
    pass


class LiteLLMAdminClient:
    def __init__(self, base_url: str, master_key: str, timeout_seconds: int = 20) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {master_key}"},
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            response = await self._client.get("/health/liveliness")
            return response.is_success
        except httpx.HTTPError:
            return False

    async def create_key(
        self,
        *,
        user_id: str,
        alias: str,
        models: list[str],
        rpm: int,
        tpm: int,
        max_parallel_requests: int,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/key/generate",
            json={
                "user_id": user_id,
                "key_alias": alias,
                "models": models,
                "rpm_limit": rpm,
                "tpm_limit": tpm,
                "max_parallel_requests": max_parallel_requests,
            },
        )

    async def create_user(self, *, user_id: str, name: str, email: str | None) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/user/new",
            json={
                "user_id": user_id,
                "user_alias": name,
                "user_email": email,
                "user_role": "internal_user",
                "auto_create_key": False,
            },
        )

    async def disable_key(self, key_id: str) -> dict[str, Any]:
        return await self._request("POST", "/key/block", json={"key": key_id})

    async def user_info(self, user_id: str) -> dict[str, Any]:
        return await self._request("GET", "/user/info", params={"user_id": user_id})

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LiteLLMAdminError(f"LiteLLM admin request failed: {path}") from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise LiteLLMAdminError(f"Unexpected LiteLLM response: {path}")
        return payload
