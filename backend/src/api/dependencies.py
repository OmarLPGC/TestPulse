import hashlib
import hmac
from collections.abc import Generator
from datetime import datetime, timezone

from database.schemas.user_entity import User
from database.schemas.user_session_entity import UserSession
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from testpulse.config import Settings
from testpulse.github_app import GitHubAppClient
from testpulse.token_crypto import decrypt_token, encrypt_token

SESSION_COOKIE_NAME = "testpulse_session"
SESSION_STATE_PARAMETER = "testpulse_state"


def get_db_session(request: Request) -> Generator[Session, None, None]:
    with Session(request.app.state.database_engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_github_client(settings: Settings = Depends(get_settings)) -> GitHubAppClient:
    if not settings.github_app_client_id or not settings.github_app_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub App authentication is not configured.",
        )
    return GitHubAppClient(settings.github_app_client_id, settings.github_app_client_secret)


def get_current_session(
    request: Request,
    session: Session = Depends(get_db_session),
) -> UserSession:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Cookie"},
        )
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    current_session = session.scalar(
        select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
    )
    if current_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired.",
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token or not hmac.compare_digest(csrf_token, current_session.csrf_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A valid X-CSRF-Token header is required.",
            )
    return current_session


def get_current_user(
    current_session: UserSession = Depends(get_current_session),
) -> User:
    return current_session.user


def get_github_access_token(
    current_session: UserSession = Depends(get_current_session),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    github: GitHubAppClient = Depends(get_github_client),
) -> str:
    if not settings.github_token_encryption_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub token encryption is not configured.",
        )
    now = datetime.now(timezone.utc)
    expires_at = current_session.github_token_expires_at
    if expires_at is not None and _as_utc(expires_at) <= now:
        if not current_session.github_refresh_token_ciphertext:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub authorization expired; reconnect your GitHub account.",
            )
        try:
            refresh_token = decrypt_token(
                current_session.github_refresh_token_ciphertext,
                settings.github_token_encryption_key,
            )
            credentials = github.refresh_credentials(refresh_token)
        except (ValueError, RuntimeError) as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub authorization expired; reconnect your GitHub account.",
            ) from error
        current_session.github_access_token_ciphertext = encrypt_token(
            credentials.access_token, settings.github_token_encryption_key
        )
        if credentials.refresh_token:
            current_session.github_refresh_token_ciphertext = encrypt_token(
                credentials.refresh_token, settings.github_token_encryption_key
            )
        current_session.github_token_expires_at = (
            datetime.fromtimestamp(now.timestamp() + credentials.expires_in, timezone.utc)
            if credentials.expires_in
            else None
        )
        session.flush()
    try:
        return decrypt_token(
            current_session.github_access_token_ciphertext,
            settings.github_token_encryption_key,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored GitHub authorization could not be decrypted.",
        ) from error


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
