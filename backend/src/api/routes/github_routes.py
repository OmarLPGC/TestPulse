from database.schemas.project_entity import Project
from database.schemas.user_entity import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from testpulse.github_app import GitHubAppClient, GitHubError

from api.authz import require_project_owner
from api.dependencies import (
    get_current_user,
    get_db_session,
    get_github_access_token,
    get_github_client,
)
from api.schemas.auth_schemas import (
    RepositoryConnect,
    RepositoryPage,
    RepositoryRead,
)

router = APIRouter(prefix="/api/v1", tags=["GitHub repositories"])


@router.get("/github/repositories", response_model=RepositoryPage)
def list_github_repositories(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    access_token: str = Depends(get_github_access_token),
    github: GitHubAppClient = Depends(get_github_client),
) -> RepositoryPage:
    try:
        repositories, has_next = github.list_repositories(
            access_token, page=page, per_page=per_page
        )
    except GitHubError as error:
        raise _github_http_error(
            error, "GitHub repositories could not be loaded."
        ) from error
    return RepositoryPage(
        items=[RepositoryRead(**repository) for repository in repositories],
        page=page,
        per_page=per_page,
        has_next=has_next,
    )


@router.post(
    "/projects/{project_id}/repository",
    response_model=RepositoryRead,
)
def connect_github_repository(
    project_id: int,
    repository_data: RepositoryConnect,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    access_token: str = Depends(get_github_access_token),
    github: GitHubAppClient = Depends(get_github_client),
) -> RepositoryRead:
    project = require_project_owner(session, project_id, current_user)
    try:
        repository = github.get_repository(access_token, repository_data.full_name)
    except GitHubError as error:
        raise _github_http_error(error, "GitHub repository could not be verified.") from error
    if repository["id"] != repository_data.github_repository_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="GitHub repository ID does not match the repository name.",
        )
    permissions = repository["permissions"]
    if not any(permissions.get(permission) is True for permission in ("pull", "push", "admin")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The GitHub account cannot read this repository.",
        )
    duplicate = session.scalar(
        select(Project.id).where(
            Project.workspace_id == project.workspace_id,
            Project.repository_provider == "github",
            Project.repository_id == repository["id"],
            Project.id != project.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This repository is already connected to another project in the workspace.",
        )
    try:
        with session.begin_nested():
            project.repository_provider = "github"
            project.repository_id = repository["id"]
            project.repository_full_name = repository["full_name"]
            project.repository_url = repository["html_url"]
            session.flush()
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This repository is already connected to another project in the workspace.",
        ) from error
    return RepositoryRead(**repository)


@router.delete("/projects/{project_id}/repository", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_github_repository(
    project_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    project = require_project_owner(session, project_id, current_user)
    project.repository_provider = None
    project.repository_id = None
    project.repository_full_name = None
    project.repository_url = None


def _github_http_error(error: GitHubError, message: str) -> HTTPException:
    if error.status_code in {401, 403}:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub authorization is no longer valid; reconnect your GitHub account.",
        )
    if error.status_code == 404:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The GitHub repository is not available to this account.",
        )
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=message)
