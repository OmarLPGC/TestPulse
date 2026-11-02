from database.schemas.user_entity import User
from database.schemas.workspace_entity import Workspace, WorkspaceMembership
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from testpulse.config import Settings

from api.dependencies import get_current_user, get_db_session, get_settings
from api.schemas.auth_schemas import (
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberRead,
    WorkspaceRead,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(
    workspace_data: WorkspaceCreate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkspaceRead:
    workspace = Workspace(name=workspace_data.name.strip())
    if not workspace.name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Workspace name must not be empty or whitespace.",
        )
    session.add(workspace)
    session.flush()
    session.add(
        WorkspaceMembership(workspace_id=workspace.id, user_id=current_user.id, role="owner")
    )
    session.flush()
    return WorkspaceRead(id=workspace.id, name=workspace.name, role="owner", is_legacy=False)


@router.get("", response_model=list[WorkspaceRead])
def list_workspaces(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[WorkspaceRead]:
    rows = session.execute(
        select(Workspace, WorkspaceMembership.role)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == current_user.id)
        .order_by(Workspace.id)
    )
    return [
        WorkspaceRead(
            id=workspace.id,
            name=workspace.name,
            role=role,
            is_legacy=workspace.is_legacy,
            is_personal=workspace.is_personal,
        )
        for workspace, role in rows
    ]


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberRead])
def list_workspace_members(
    workspace_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[WorkspaceMemberRead]:
    _require_membership(session, workspace_id, current_user.id)
    rows = session.scalars(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .options(joinedload(WorkspaceMembership.user))
        .order_by(WorkspaceMembership.id)
    )
    return [
        WorkspaceMemberRead(
            user_id=membership.user.id,
            github_user_id=membership.user.github_user_id,
            github_login=membership.user.github_login,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership in rows
    ]


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_workspace_member(
    workspace_id: int,
    member_data: WorkspaceMemberCreate,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkspaceMemberRead:
    _require_owner(session, workspace_id, current_user.id)
    target_user = session.scalar(
        select(User).where(User.github_user_id == member_data.github_user_id)
    )
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The GitHub user must sign in before being added.",
        )
    membership = WorkspaceMembership(
        workspace_id=workspace_id, user_id=target_user.id, role="member"
    )
    try:
        with session.begin_nested():
            session.add(membership)
            session.flush()
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The user is already a workspace member.",
        ) from error
    return WorkspaceMemberRead(
        user_id=target_user.id,
        github_user_id=target_user.github_user_id,
        github_login=target_user.github_login,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_workspace_member(
    workspace_id: int,
    user_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    _require_owner(session, workspace_id, current_user.id)
    membership = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
    if membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace owners cannot be removed.",
        )
    session.delete(membership)


@router.post("/legacy/claim", response_model=WorkspaceRead)
def claim_legacy_workspace(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> WorkspaceRead:
    if settings.bootstrap_github_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Legacy workspace bootstrap is not configured.",
        )
    if current_user.github_user_id != settings.bootstrap_github_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This GitHub account is not authorized to claim the legacy workspace.",
        )
    workspace = session.scalar(
        select(Workspace).where(Workspace.is_legacy.is_(True)).with_for_update()
    )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Legacy workspace does not exist.",
        )
    memberships = list(
        session.scalars(
            select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace.id)
        )
    )
    if memberships:
        own_membership = next(
            (item for item in memberships if item.user_id == current_user.id), None
        )
        if own_membership and own_membership.role == "owner":
            return WorkspaceRead(
                id=workspace.id, name=workspace.name, role="owner", is_legacy=True
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The legacy workspace has already been claimed.",
        )
    membership = WorkspaceMembership(
        workspace_id=workspace.id, user_id=current_user.id, role="owner"
    )
    session.add(membership)
    session.flush()
    return WorkspaceRead(
        id=workspace.id, name=workspace.name, role="owner", is_legacy=True, is_personal=False
    )


def _require_membership(session: Session, workspace_id: int, user_id: int) -> WorkspaceMembership:
    membership = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return membership


def _require_owner(session: Session, workspace_id: int, user_id: int) -> WorkspaceMembership:
    membership = _require_membership(session, workspace_id, user_id)
    if membership.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage members.",
        )
    return membership
