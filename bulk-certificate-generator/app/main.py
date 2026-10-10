"""Application factory. `app` at the bottom is what uvicorn runs."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import certificates, jobs
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import create_db_engine, create_session_factory, init_db
from app.services.recovery import recover_interrupted_jobs

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging()

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        init_db(engine)
        recovered = recover_interrupted_jobs(session_factory)
        if recovered:
            logger.warning("%d interrupted job(s) recovered at startup", recovered)
        yield
        engine.dispose()

    app = FastAPI(
        title="Bulk Certificate Generator API",
        version="1.0.0",
        description="Submit many recipients in one request; track and download certificates.",
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.output_dir = settings.output_dir
    app.include_router(jobs.router)
    app.include_router(certificates.router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
