from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from sqlalchemy import create_engine

from testpulse.config import Settings, load_settings


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    app_settings = settings or load_settings()
    engine = create_engine(app_settings.database_url, pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="TestPulse API", version="0.1.0", lifespan=lifespan)
    application.state.settings = app_settings
    application.state.database_engine = engine

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application
