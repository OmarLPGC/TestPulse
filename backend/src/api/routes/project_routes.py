from collections.abc import Generator

from database.db_operations.projects import (
    ProjectNameConflict,
    create_project,
    get_project,
    list_projects,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from api.schemas.project_schemas import ProjectCreate, ProjectRead

router = APIRouter(prefix="/projects", tags=["projects"])


def get_db_session(request: Request) -> Generator[Session, None, None]:
    with Session(request.app.state.database_engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project_endpoint(
    project_data: ProjectCreate,
    session: Session = Depends(get_db_session),
) -> ProjectRead:
    try:
        repository_url = (
            str(project_data.repository_url) if project_data.repository_url is not None else None
        )
        project = create_project(
            session,
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
def list_projects_endpoint(session: Session = Depends(get_db_session)) -> list[ProjectRead]:
    return [ProjectRead.model_validate(project) for project in list_projects(session)]


@router.get("/{project_id}", response_model=ProjectRead)
def get_project_endpoint(
    project_id: int,
    session: Session = Depends(get_db_session),
) -> ProjectRead:
    project = get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return ProjectRead.model_validate(project)
