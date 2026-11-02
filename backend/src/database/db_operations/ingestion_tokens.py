import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.schemas.project_ingestion_token_entity import ProjectIngestionToken


def create_ingestion_token(
    session: Session, project_id: int, name: str, expires_at: Optional[datetime]
) -> tuple[ProjectIngestionToken, str]:
    raw_token = secrets.token_urlsafe(32)
    record = ProjectIngestionToken(
        project_id=project_id,
        name=name,
        token_hash=_hash_token(raw_token),
        expires_at=expires_at,
    )
    session.add(record)
    session.flush()
    return record, raw_token


def list_ingestion_tokens(session: Session, project_id: int) -> list[ProjectIngestionToken]:
    return list(
        session.scalars(
            select(ProjectIngestionToken)
            .where(ProjectIngestionToken.project_id == project_id)
            .order_by(ProjectIngestionToken.id)
        )
    )


def revoke_ingestion_token(
    session: Session, project_id: int, token_id: int
) -> Optional[ProjectIngestionToken]:
    record = session.scalar(
        select(ProjectIngestionToken).where(
            ProjectIngestionToken.id == token_id,
            ProjectIngestionToken.project_id == project_id,
        )
    )
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)
    return record


def authenticate_ingestion_token(
    session: Session,
    project_id: int,
    raw_token: Optional[str],
) -> Optional[ProjectIngestionToken]:
    if not raw_token:
        return None
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    record = session.scalar(
        select(ProjectIngestionToken).where(
            ProjectIngestionToken.project_id == project_id,
            ProjectIngestionToken.token_hash == token_hash,
            ProjectIngestionToken.revoked_at.is_(None),
        )
    )
    if record is None:
        return None
    if record.expires_at is not None:
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            return None
    record.last_used_at = now
    return record


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
