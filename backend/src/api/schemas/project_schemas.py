from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    repository_url: Optional[HttpUrl] = None
    workspace_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Project name must not be empty or whitespace.")
        return value


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    name: str
    repository_url: Optional[str]
    repository_provider: Optional[str] = None
    repository_id: Optional[int] = None
    repository_full_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
