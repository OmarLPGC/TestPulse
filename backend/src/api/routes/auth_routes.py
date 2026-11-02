import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from database.schemas.oauth_state_entity import OAuthState
from database.schemas.user_entity import User
from database.schemas.user_session_entity import UserSession
from database.schemas.workspace_entity import Workspace, WorkspaceMembership
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from testpulse.config import Settings
from testpulse.github_app import GitHubAppClient, GitHubError
from testpulse.token_crypto import encrypt_token

from api.dependencies import (
    SESSION_COOKIE_NAME,
    get_current_session,
    get_db_session,
    get_github_client,
    get_settings,
)
from api.schemas.auth_schemas import AuthenticatedUserRead

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
OAUTH_STATE_TTL_SECONDS = 600
logger = logging.getLogger(__name__)


@router.get("/github/login")
def github_login(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    github: GitHubAppClient = Depends(get_github_client),
) -> RedirectResponse:
    if not settings.github_app_callback_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub App callback URL is not configured.",
        )
    now = datetime.now(timezone.utc)
    session.query(OAuthState).filter(OAuthState.expires_at <= now).delete(synchronize_session=False)
    raw_state = secrets.token_urlsafe(32)
    session.add(
        OAuthState(
            state_hash=_sha256(raw_state),
            expires_at=now + timedelta(seconds=OAUTH_STATE_TTL_SECONDS),
        )
    )
    session.flush()
    redirect = RedirectResponse(
        github.authorization_url(settings.github_app_callback_url, raw_state),
        status_code=status.HTTP_302_FOUND,
    )
    redirect.set_cookie(
        "testpulse_oauth_state",
        raw_state,
        max_age=OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/api/v1/auth/github/callback",
    )
    return redirect


@router.get("/github/callback")
def github_callback(
    request: Request,
    code: Optional[str] = Query(default=None, min_length=1, max_length=2048),
    state: Optional[str] = Query(default=None, min_length=1, max_length=256),
    error: Optional[str] = None,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    github: GitHubAppClient = Depends(get_github_client),
) -> Response:
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub authorization was not completed.",
        )
    state_cookie = request.cookies.get("testpulse_oauth_state")
    if (
        not code
        or not state
        or not state_cookie
        or not hmac.compare_digest(state, state_cookie)
        or not settings.github_token_encryption_key
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub callback is missing required authorization data.",
        )

    now = datetime.now(timezone.utc)
    oauth_state = session.scalar(
        select(OAuthState).where(
            OAuthState.state_hash == _sha256(state),
            OAuthState.expires_at > now,
        )
    )
    if oauth_state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub authorization state is invalid or expired.",
        )
    session.delete(oauth_state)
    session.commit()

    try:
        credentials = github.exchange_code(code)
    except GitHubError as exception:
        logger.warning(
            "GitHub OAuth code exchange failed (upstream_status=%s, provider_error=%s).",
            exception.status_code,
            exception.provider_error,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub authorization could not be completed.",
        ) from exception

    try:
        profile = github.get_authenticated_user(credentials.access_token)
    except GitHubError as exception:
        logger.warning(
            "GitHub authenticated-user lookup failed (upstream_status=%s).",
            exception.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub authorization could not be completed.",
        ) from exception

    user = _get_or_create_user(session, profile)
    raw_session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            token_hash=_sha256(raw_session_token),
            user_id=user.id,
            csrf_token=csrf_token,
            github_access_token_ciphertext=encrypt_token(
                credentials.access_token, settings.github_token_encryption_key
            ),
            github_refresh_token_ciphertext=(
                encrypt_token(credentials.refresh_token, settings.github_token_encryption_key)
                if credentials.refresh_token
                else None
            ),
            github_token_expires_at=(
                now + timedelta(seconds=credentials.expires_in) if credentials.expires_in else None
            ),
            expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    session.flush()
    public_base_url = settings.public_base_url
    if public_base_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Public application URL is not configured.",
        )
    redirect = RedirectResponse(public_base_url + "/", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        SESSION_COOKIE_NAME,
        raw_session_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )
    redirect.delete_cookie(
        "testpulse_oauth_state",
        path="/api/v1/auth/github/callback",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )
    redirect.set_cookie(
        "testpulse_csrf",
        csrf_token,
        max_age=settings.session_ttl_seconds,
        httponly=False,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )
    return redirect


@router.get("/me", response_model=AuthenticatedUserRead)
def get_authenticated_user(
    current_session: UserSession = Depends(get_current_session),
) -> AuthenticatedUserRead:
    user = current_session.user
    return AuthenticatedUserRead(
        id=user.id,
        github_user_id=user.github_user_id,
        github_login=user.github_login,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        csrf_token=current_session.csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    current_session: UserSession = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    current_session.revoked_at = datetime.now(timezone.utc)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )
    response.delete_cookie(
        "testpulse_csrf",
        path="/",
        secure=settings.app_env == "production",
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def _get_or_create_user(session: Session, profile: dict[str, object]) -> User:
    github_user_id = profile["id"]
    github_login = profile["login"]
    if not isinstance(github_user_id, int) or not isinstance(github_login, str):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub returned an invalid user profile.",
        )
    user = session.scalar(select(User).where(User.github_user_id == github_user_id))
    if user is not None:
        user.github_login = github_login
        user.display_name = _optional_string(profile.get("name"))
        user.avatar_url = _optional_string(profile.get("avatar_url"))
        session.flush()
        return user

    try:
        with session.begin_nested():
            user = User(
                github_user_id=github_user_id,
                github_login=github_login,
                display_name=_optional_string(profile.get("name")),
                avatar_url=_optional_string(profile.get("avatar_url")),
            )
            session.add(user)
            session.flush()
    except IntegrityError:
        user = session.scalar(select(User).where(User.github_user_id == github_user_id))
        if user is None:
            raise
        return user

    workspace = Workspace(name=f"{github_login}'s workspace", is_personal=True)
    session.add(workspace)
    session.flush()
    session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    session.flush()
    return user


def _optional_string(value: object) -> Optional[str]:
    return value if isinstance(value, str) else None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
