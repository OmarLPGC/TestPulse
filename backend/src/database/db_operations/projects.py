from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.schemas.project_entity import Project


class ProjectNameConflict(Exception):
    """Raised when a project with the same name already exists."""


def create_project(session: Session, name: str, repository_url: Optional[str]) -> Project:
    existing = session.scalar(select(Project).where(Project.name == name))
    if existing is not None:
        raise ProjectNameConflict(name)

    project = Project(name=name, repository_url=repository_url)
    try:
        with session.begin_nested():
            session.add(project)
            session.flush()
    except IntegrityError as error:
        constraint_name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        sqlite_duplicate = "UNIQUE constraint failed: projects.name" in str(error.orig)
        if constraint_name == "uq_projects_name" or sqlite_duplicate:
            raise ProjectNameConflict(name) from error
        raise

    return project


def list_projects(session: Session) -> list[Project]:
    return list(session.scalars(select(Project).order_by(Project.id)))


def get_project(session: Session, project_id: int) -> Optional[Project]:
    return session.get(Project, project_id)
