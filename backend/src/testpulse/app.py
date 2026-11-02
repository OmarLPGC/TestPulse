from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from api.routes.analysis_job_routes import router as analysis_jobs_router
from api.routes.analysis_routes import router as analysis_router
from api.routes.auth_routes import router as auth_router
from api.routes.github_routes import router as github_router
from api.routes.ingestion_token_routes import router as ingestion_tokens_router
from api.routes.project_routes import router as projects_router
from api.routes.run_routes import router as runs_router
from api.routes.workspace_routes import router as workspaces_router
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from testpulse.config import Settings, load_settings


def create_app(
    settings: Optional[Settings] = None, database_engine: Optional[Engine] = None
) -> FastAPI:
    app_settings = settings or load_settings()
    owns_engine = database_engine is None
    engine = (
        database_engine
        if database_engine is not None
        else create_engine(app_settings.database_url, pool_pre_ping=True)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        try:
            yield
        finally:
            if owns_engine:
                engine.dispose()

    application = FastAPI(title="TestPulse API", version="0.1.0", lifespan=lifespan)
    application.state.settings = app_settings
    application.state.database_engine = engine
    application.include_router(auth_router)
    application.include_router(projects_router)
    application.include_router(runs_router)
    application.include_router(analysis_router)
    application.include_router(analysis_jobs_router)
    application.include_router(workspaces_router)
    application.include_router(github_router)
    application.include_router(ingestion_tokens_router)

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application
