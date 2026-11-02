from datetime import datetime, timezone

from database.db_operations.ingestion_tokens import (
    create_ingestion_token,
    list_ingestion_tokens,
    revoke_ingestion_token,
)
from database.schemas.user_entity import User
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.authz import require_project_owner
from api.dependencies import get_current_user, get_db_session
from api.schemas.auth_schemas import (
    IngestionTokenCreate,
    IngestionTokenCreated,
    IngestionTokenRead,
)

router = APIRouter(prefix="/api/v1/projects", tags=["ingestion tokens"])


@router.post(
    "/{project_id}/ingestion-tokens",
    response_model=IngestionTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_project_ingestion_token(
    project_id: int,
    token_data: IngestionTokenCreate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> IngestionTokenCreated:
    require_project_owner(session, project_id, current_user)
    if token_data.expires_at is not None:
        expiry = token_data.expires_at
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="expires_at must be a future timezone-aware timestamp.",
            )
    record, raw_token = create_ingestion_token(
        session, project_id, token_data.name, token_data.expires_at
    )
    return IngestionTokenCreated(
        id=record.id,
        project_id=record.project_id,
        name=record.name,
        created_at=record.created_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        last_used_at=record.last_used_at,
        token=raw_token,
    )


@router.get(
    "/{project_id}/ingestion-tokens",
    response_model=list[IngestionTokenRead],
)
def list_project_ingestion_tokens(
    project_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[IngestionTokenRead]:
    require_project_owner(session, project_id, current_user)
    return [
        IngestionTokenRead.model_validate(record)
        for record in list_ingestion_tokens(session, project_id)
    ]


@router.delete(
    "/{project_id}/ingestion-tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_project_ingestion_token(
    project_id: int,
    token_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    require_project_owner(session, project_id, current_user)
    token = revoke_ingestion_token(session, project_id, token_id)
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found.")
