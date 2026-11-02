from database.schemas.project_entity import Project
from database.schemas.user_entity import User
from database.schemas.workspace_entity import WorkspaceMembership
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session


def has_workspace_membership(session: Session, workspace_id: int, user_id: int) -> bool:
    return (
        session.scalar(
            select(WorkspaceMembership.id).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )
        is not None
    )


def require_project_member(session: Session, project_id: int, user: User) -> Project:
    project = session.get(Project, project_id)
    if project is None or not has_workspace_membership(
        session, project.workspace_id, user.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def require_project_owner(session: Session, project_id: int, user: User) -> Project:
    project = require_project_member(session, project_id, user)
    membership = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == project.workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if membership is None or membership.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage this project.",
        )
    return project
