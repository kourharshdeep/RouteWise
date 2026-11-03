"""FastAPI Application Factory for RouteWise."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.config import settings
from src.api.routes import alerts, auth, chat, corridor, disruptions, events, health, journey, live, reports, risk
from src.services.weather.scheduler import weather_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages application startup and shutdown events."""
    # Startup: Start live/replay weather scheduler if enabled
    weather_scheduler.start()
    yield
    # Shutdown: Stop scheduler cleanly
    await weather_scheduler.stop()


def create_app() -> FastAPI:
    """Creates and configures the FastAPI application instance."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Edge-resilient GeoAI and predictive logistics API for forecasting "
            "road-segment disruption risk on the Ramban–Banihal NH-44 pilot corridor."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # 1. CORS Middleware configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Register modular routers
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(reports.router, prefix=settings.api_prefix)
    app.include_router(risk.router, prefix=settings.api_prefix)
    app.include_router(live.router, prefix=settings.api_prefix)
    app.include_router(events.router, prefix=settings.api_prefix)
    app.include_router(alerts.router, prefix=settings.api_prefix)
    app.include_router(corridor.router, prefix=settings.api_prefix)
    app.include_router(journey.router, prefix=settings.api_prefix)
    app.include_router(disruptions.router, prefix=settings.api_prefix)
    app.include_router(chat.router, prefix=settings.api_prefix)

    @app.get("/", tags=["Root"])
    def root() -> JSONResponse:
        return JSONResponse(
            content={
                "service": settings.app_name,
                "version": settings.app_version,
                "docs": "/docs",
                "health": f"{settings.api_prefix}/health",
            }
        )

    return app


app = create_app()
