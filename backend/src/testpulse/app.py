from collections.abc import AsyncIterator
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from sqlalchemy import create_engine

from testpulse.config import Settings, load_settings


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    app_settings = settings or load_settings()
    engine = create_engine(app_settings.database_url, pool_pre_ping=True)

    @AsyncGenerator
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
