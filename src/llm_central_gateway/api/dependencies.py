from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.litellm_admin import LiteLLMAdminClient
from ..settings import Settings


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_litellm(request: Request) -> LiteLLMAdminClient:
    return cast(LiteLLMAdminClient, request.app.state.litellm)


def require_admin(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = f"Bearer {settings.admin_api_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


SessionDependency = Annotated[AsyncSession, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
LiteLLMDependency = Annotated[LiteLLMAdminClient, Depends(get_litellm)]
AdminDependency = Annotated[None, Depends(require_admin)]
