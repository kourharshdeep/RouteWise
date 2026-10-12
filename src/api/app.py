"""FastAPI Application Factory for RouteWise."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.config import settings
from src.api.routes import corridor, health, risk


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
    app.include_router(risk.router, prefix=settings.api_prefix)
    app.include_router(corridor.router, prefix=settings.api_prefix)

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
