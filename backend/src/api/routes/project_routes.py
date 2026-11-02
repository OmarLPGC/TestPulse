from database.db_operations.projects import (
    ProjectNameConflict,
    create_project,
    get_project,
    list_projects,
)
from database.schemas.user_entity import User
from database.schemas.workspace_entity import Workspace, WorkspaceMembership
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.authz import has_workspace_membership
from api.dependencies import get_current_user, get_db_session
from api.schemas.project_schemas import ProjectCreate, ProjectRead

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project_endpoint(
    project_data: ProjectCreate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProjectRead:
    if project_data.workspace_id is None:
        personal_workspace = session.scalar(
            select(WorkspaceMembership.workspace_id)
            .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
            .where(
                WorkspaceMembership.user_id == current_user.id,
                WorkspaceMembership.role == "owner",
                Workspace.is_personal.is_(True),
            )
            .order_by(WorkspaceMembership.workspace_id)
        )
        workspace_id = personal_workspace
    else:
        workspace_id = project_data.workspace_id
    if workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An owner workspace is required to create a project.",
        )
    membership = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == current_user.id,
        )
    )
    if membership is None or membership.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can create projects.",
        )
    try:
        repository_url = (
            str(project_data.repository_url) if project_data.repository_url is not None else None
        )
        project = create_project(
            session,
            workspace_id=workspace_id,
            name=project_data.name,
            repository_url=repository_url,
        )
    except ProjectNameConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A project with this name already exists.",
        ) from error

    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
def list_projects_endpoint(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[ProjectRead]:
    return [
        ProjectRead.model_validate(project)
        for project in list_projects(session, user_id=current_user.id)
    ]


@router.get("/{project_id}", response_model=ProjectRead)
def get_project_endpoint(
    project_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProjectRead:
    project = get_project(session, project_id)
    if project is None or not has_workspace_membership(
        session, project.workspace_id, current_user.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return ProjectRead.model_validate(project)
