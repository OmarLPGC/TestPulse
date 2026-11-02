from pathlib import Path
from typing import Optional

from api.dependencies import get_current_user
from database import Base
from database.schemas.user_entity import User
from database.schemas.workspace_entity import Workspace, WorkspaceMembership
from fastapi import FastAPI
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from testpulse.app import create_app
from testpulse.config import Settings


def create_authenticated_test_app(
    database_path: Path,
    *,
    max_junit_report_bytes: Optional[int] = None,
    max_junit_test_cases: Optional[int] = None,
) -> tuple[FastAPI, User]:
    settings = Settings(
        app_env="test",
        database_url=URL.create("sqlite", database=str(database_path)),
        **(
            {"max_junit_report_bytes": max_junit_report_bytes}
            if max_junit_report_bytes is not None
            else {}
        ),
        **(
            {"max_junit_test_cases": max_junit_test_cases}
            if max_junit_test_cases is not None
            else {}
        ),
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.database_engine)
    with Session(app.state.database_engine) as session:
        user = User(github_user_id=123456, github_login="test-user")
        workspace = Workspace(name="Test workspace", is_personal=True)
        session.add_all((user, workspace))
        session.flush()
        session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
        session.commit()
        session.refresh(user)
        session.expunge(user)
    app.dependency_overrides[get_current_user] = lambda: user
    return app, user
