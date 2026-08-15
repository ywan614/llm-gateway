from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    status: str
    created_at: datetime


class KeyCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=200)
    rpm: int | None = Field(default=None, ge=1)
    tpm: int | None = Field(default=None, ge=1)
    max_parallel_requests: int | None = Field(default=None, ge=1)


class KeyCreated(BaseModel):
    key_id: str
    api_key: str
    alias: str
    message: str = "Store this API key now; it will not be shown again."


class UsageRead(BaseModel):
    user_id: uuid.UUID
    raw_usage: dict[str, object]
