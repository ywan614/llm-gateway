from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..adapters.litellm_admin import LiteLLMAdminError
from ..models import ApiKeyBinding, AuditEvent, User
from ..schemas import KeyCreate, KeyCreated, UsageRead, UserCreate, UserRead
from .dependencies import (
    AdminDependency,
    LiteLLMDependency,
    SessionDependency,
    SettingsDependency,
)

router = APIRouter(prefix="/api/v1")


@router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", tags=["health"])
async def ready(litellm: LiteLLMDependency) -> dict[str, str]:
    if not await litellm.health():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Not ready")
    return {"status": "ready"}


@router.post("/admin/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _: AdminDependency,
    session: SessionDependency,
    litellm: LiteLLMDependency,
) -> User:
    user = User(id=uuid.uuid4(), name=body.name, email=body.email)
    try:
        await litellm.create_user(
            user_id=str(user.id),
            name=user.name,
            email=user.email,
        )
    except LiteLLMAdminError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    session.add(user)
    session.add(
        AuditEvent(
            actor="admin",
            action="user.created",
            target_type="user",
            target_id=str(user.id),
        )
    )
    await session.commit()
    await session.refresh(user)
    return user


@router.post(
    "/admin/users/{user_id}/keys", response_model=KeyCreated, status_code=status.HTTP_201_CREATED
)
async def create_key(
    user_id: uuid.UUID,
    body: KeyCreate,
    _: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    litellm: LiteLLMDependency,
) -> KeyCreated:
    user = await session.get(User, user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active user not found")
    try:
        result = await litellm.create_key(
            user_id=str(user_id),
            alias=body.alias,
            models=[settings.public_model_name],
            rpm=body.rpm or settings.default_rpm,
            tpm=body.tpm or settings.default_tpm,
            max_parallel_requests=(
                body.max_parallel_requests or settings.default_max_parallel_requests
            ),
        )
    except LiteLLMAdminError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    api_key = str(result.get("key", ""))
    key_id = str(result.get("token_id") or result.get("key_name") or "")
    if not api_key or not key_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="LiteLLM returned an invalid key"
        )
    session.add(
        ApiKeyBinding(
            user_id=user_id,
            litellm_key_id=key_id,
            key_alias=body.alias,
        )
    )
    session.add(
        AuditEvent(
            actor="admin",
            action="key.created",
            target_type="api_key",
            target_id=key_id,
            details={"alias": body.alias},
        )
    )
    await session.commit()
    return KeyCreated(key_id=key_id, api_key=api_key, alias=body.alias)


@router.post("/admin/keys/{key_id}/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_key(
    key_id: str,
    _: AdminDependency,
    session: SessionDependency,
    litellm: LiteLLMDependency,
) -> None:
    binding = await session.scalar(
        select(ApiKeyBinding).where(ApiKeyBinding.litellm_key_id == key_id)
    )
    if binding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    try:
        await litellm.disable_key(key_id)
    except LiteLLMAdminError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    binding.status = "disabled"
    binding.revoked_at = datetime.now(UTC)
    session.add(
        AuditEvent(
            actor="admin",
            action="key.disabled",
            target_type="api_key",
            target_id=key_id,
        )
    )
    await session.commit()


@router.get("/admin/users/{user_id}/usage", response_model=UsageRead)
async def get_usage(
    user_id: uuid.UUID,
    _: AdminDependency,
    session: SessionDependency,
    litellm: LiteLLMDependency,
) -> UsageRead:
    if await session.get(User, user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        usage = await litellm.user_info(str(user_id))
    except LiteLLMAdminError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return UsageRead(user_id=user_id, raw_usage=usage)


@router.get("/admin/models")
async def models(_: AdminDependency, settings: SettingsDependency) -> dict[str, list[str]]:
    return {"models": [settings.public_model_name]}
