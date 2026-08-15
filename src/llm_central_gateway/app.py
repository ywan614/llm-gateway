from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from sqlalchemy import text

from .adapters.litellm_admin import LiteLLMAdminClient
from .api.routes import router
from .database import create_database_engine, create_session_factory
from .logging import bind_request_id, configure_logging, reset_request_id
from .settings import Settings, load_settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(runtime_settings)
        engine = create_database_engine(runtime_settings.async_postgres_uri)
        app.state.settings = runtime_settings
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.litellm = LiteLLMAdminClient(
            runtime_settings.litellm_admin_url,
            runtime_settings.litellm_master_key,
        )
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("Application started", extra={"event": "application.startup.complete"})
        try:
            yield
        finally:
            logger.info("Application stopping", extra={"event": "application.shutdown.start"})
            await app.state.litellm.close()
            await engine.dispose()

    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = bind_request_id(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "HTTP request failed",
                extra={
                    "event": "http.request.error",
                    "data": {"method": request.method, "path": request.url.path},
                },
            )
            raise
        else:
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "HTTP request completed",
                extra={
                    "event": "http.request.complete",
                    "data": {
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    },
                },
            )
            return response
        finally:
            reset_request_id(token)

    return app


def run() -> None:
    settings = load_settings()
    uvicorn.run(
        "llm_central_gateway.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )
