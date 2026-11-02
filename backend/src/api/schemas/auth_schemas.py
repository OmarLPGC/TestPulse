import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuthenticatedUserRead(BaseModel):
    id: int
    github_user_id: int
    github_login: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    csrf_token: str


class WorkspaceRead(BaseModel):
    id: int
    name: str
    role: str
    is_legacy: bool
    is_personal: bool = False


class WorkspaceMemberRead(BaseModel):
    user_id: int
    github_user_id: int
    github_login: str
    role: str
    created_at: datetime


class WorkspaceMemberCreate(BaseModel):
    github_user_id: int = Field(gt=0)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class RepositoryRead(BaseModel):
    id: int
    full_name: str
    html_url: str
    private: bool
    permissions: dict[str, bool]


class RepositoryPage(BaseModel):
    items: list[RepositoryRead]
    page: int
    per_page: int
    has_next: bool


class RepositoryConnect(BaseModel):
    github_repository_id: int = Field(gt=0)
    full_name: str = Field(min_length=3, max_length=255)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
            raise ValueError("full_name must use the owner/repository format.")
        if value.startswith(".") or "/." in value:
            raise ValueError("full_name contains an invalid owner or repository.")
        return value


class IngestionTokenCreate(BaseModel):
    expires_at: Optional[datetime] = None


class IngestionTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    last_used_at: Optional[datetime]


class IngestionTokenCreated(IngestionTokenRead):
    token: str
