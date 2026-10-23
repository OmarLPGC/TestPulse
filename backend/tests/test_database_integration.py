import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from database import (
    Project,
)
from database import (
    TestCase as CaseEntity,
)
from database import (
    TestOutcome as OutcomeEnum,
)
from database import (
    TestResult as ResultEntity,
)
from database import (
    TestRun as RunEntity,
)
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def postgres_engine():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")

    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL.")
    url = url.set(drivername="postgresql+psycopg")

    schema_name = f"testpulse_{uuid4().hex}"
    admin_engine = create_engine(url)
    engine = None
    schema_created = False
    try:
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')
        schema_created = True

        engine = create_engine(
            url,
            connect_args={"options": f"-c search_path={schema_name}"},
        )
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if schema_created:
            with admin_engine.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema_name}" CASCADE')
        admin_engine.dispose()


@pytest.fixture
def session(postgres_engine):
    connection = postgres_engine.connect()
    transaction = connection.begin()
    db_session = Session(bind=connection)
    db_session.begin_nested()
    try:
        yield db_session
    finally:
        db_session.close()
        transaction.rollback()
        connection.close()


def create_project(session: Session, name: str = "TestPulse") -> Project:
    project = Project(name=f"{name}-{uuid4().hex}")
    session.add(project)
    session.flush()
    return project


def create_test_run(session: Session, project_id: int) -> RunEntity:
    test_run = RunEntity(project_id=project_id)
    session.add(test_run)
    session.flush()
    return test_run


def create_test_case(
    session: Session, project_id: int, node_id: str = "tests/test_api.py::test_ok"
) -> CaseEntity:
    test_case = CaseEntity(project_id=project_id, node_id=node_id, name="test_ok")
    session.add(test_case)
    session.flush()
    return test_case


def test_initial_migration_creates_all_tables(postgres_engine) -> None:
    tables = set(inspect(postgres_engine).get_table_names())

    assert {"projects", "test_runs", "test_cases", "test_results", "alembic_version"} <= tables


def test_project_is_persisted(postgres_engine, session: Session) -> None:
    project = Project(name=f"Persisted-{uuid4().hex}", description="Integration test")
    session.add(project)
    session.flush()
    project_id = project.id
    session.expire_all()

    persisted = session.get(Project, project_id)

    assert persisted is not None
    assert persisted.name == project.name
    assert persisted.description == "Integration test"
    assert persisted.created_at is not None
    assert persisted.updated_at is not None


def test_duplicate_test_identity_in_project_is_rejected(session: Session) -> None:
    project = create_project(session)
    session.add_all(
        [
            CaseEntity(project_id=project.id, node_id="tests/test_api.py::test_ok", name="test_ok"),
            CaseEntity(project_id=project.id, node_id="tests/test_api.py::test_ok", name="test_ok"),
        ]
    )

    with pytest.raises(IntegrityError) as error:
        session.flush()

    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == "uq_test_cases_project_node"


def test_result_with_missing_run_is_rejected(session: Session) -> None:
    project = create_project(session)
    test_case = create_test_case(session, project.id)
    session.add(
        ResultEntity(
            project_id=project.id,
            test_run_id=999999,
            test_case_id=test_case.id,
            outcome=OutcomeEnum.PASSED,
        )
    )

    with pytest.raises(IntegrityError) as error:
        session.flush()

    assert error.value.orig.sqlstate == "23503"
    assert error.value.orig.diag.constraint_name == "fk_test_results_run_project"


def test_result_cannot_combine_different_projects(session: Session) -> None:
    run_project = create_project(session, "RunProject")
    case_project = create_project(session, "CaseProject")
    test_run = create_test_run(session, run_project.id)
    test_case = create_test_case(session, case_project.id)
    session.add(
        ResultEntity(
            project_id=run_project.id,
            test_run_id=test_run.id,
            test_case_id=test_case.id,
            outcome=OutcomeEnum.PASSED,
        )
    )

    with pytest.raises(IntegrityError) as error:
        session.flush()

    assert error.value.orig.sqlstate == "23503"
    assert error.value.orig.diag.constraint_name == "fk_test_results_case_project"


def test_duplicate_result_for_run_and_case_is_rejected(session: Session) -> None:
    project = create_project(session)
    test_run = create_test_run(session, project.id)
    test_case = create_test_case(session, project.id)
    result_values = {
        "project_id": project.id,
        "test_run_id": test_run.id,
        "test_case_id": test_case.id,
        "outcome": OutcomeEnum.PASSED,
    }
    session.add_all([ResultEntity(**result_values), ResultEntity(**result_values)])

    with pytest.raises(IntegrityError) as error:
        session.flush()

    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == "uq_test_results_run_case"


def test_database_rejects_unrecognized_run_status(session: Session) -> None:
    project = create_project(session)

    with pytest.raises(IntegrityError) as error:
        session.execute(
            text("INSERT INTO test_runs (project_id, status) VALUES (:project_id, :status)"),
            {"project_id": project.id, "status": "not-a-status"},
        )

    assert error.value.orig.sqlstate == "23514"
    assert error.value.orig.diag.constraint_name == "ck_test_runs_test_run_status"


def test_database_rejects_unrecognized_result_outcome(session: Session) -> None:
    project = create_project(session)
    test_run = create_test_run(session, project.id)
    test_case = create_test_case(session, project.id)

    with pytest.raises(IntegrityError) as error:
        session.execute(
            text(
                "INSERT INTO test_results "
                "(project_id, test_run_id, test_case_id, outcome) "
                "VALUES (:project_id, :test_run_id, :test_case_id, :outcome)"
            ),
            {
                "project_id": project.id,
                "test_run_id": test_run.id,
                "test_case_id": test_case.id,
                "outcome": "not-an-outcome",
            },
        )

    assert error.value.orig.sqlstate == "23514"
    assert error.value.orig.diag.constraint_name == "ck_test_results_test_outcome"
