"""FastAPI application entry point with global error handling."""
from __future__ import annotations

import os
import sys

# Add src/ to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from core.config import get_settings
from core.logging_config import get_logger, setup_logging
from core.exceptions import (
    LALandWholesaleError,
    ExternalServiceError,
    ServiceUnavailableError,
    RateLimitError,
    ConfigurationError,
    ValidationError,
)
from api.routes import (
    health, 
    ingestion, 
    leads, 
    outreach, 
    owners, 
    parcels,
    scoring, 
    metrics, 
    config,
    automation,
    markets,
    webhooks,
    buyers,
    dispositions,
    dashboard,
    twilio_webhooks,
    active_market,
    caller,
    call_prep,
    conversations,
)

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Sets up logging, validates database, and logs startup/shutdown events.
    Non-blocking startup - allows app to start even if database is not ready.
    """
    # Initialize logging based on config
    json_logging = SETTINGS.log_format == "json"
    setup_logging(level=SETTINGS.log_level, json_format=json_logging)

    # Log DRY_RUN warning prominently
    if not SETTINGS.dry_run:
        LOGGER.warning("!!! LIVE MODE !!! DRY_RUN=false - Real SMS will be sent!")
    else:
        LOGGER.info("DRY_RUN mode enabled - No real SMS will be sent")

    LOGGER.info(
        "API application starting",
        extra={"extra_data": {
            "environment": SETTINGS.environment,
            "dry_run": SETTINGS.dry_run,
            "enabled_services": SETTINGS.get_enabled_services(),
            "database_url": SETTINGS.database_url,
        }}
    )

    # Validate database connection and tables (non-blocking)
    # App will start even if database is not ready - allows health checks to pass
    try:
        from core.db import validate_database, init_db
        db_status = validate_database()

        if db_status["status"] == "error":
            LOGGER.error(
                "Database validation failed - app will start without database",
                extra={"extra_data": {"errors": db_status["errors"], "database_url": db_status["database_url"]}}
            )
        elif db_status["status"] == "missing_tables":
            LOGGER.warning(
                "Missing database tables detected - attempting to create",
                extra={"extra_data": {"missing": db_status["tables_missing"]}}
            )
            try:
                init_result = init_db(create_missing_only=True)
                if init_result["status"] == "error":
                    LOGGER.error(
                        "Failed to create missing tables",
                        extra={"extra_data": {"error": init_result.get("error")}}
                    )
                else:
                    LOGGER.info(
                        "Database tables created successfully",
                        extra={"extra_data": {"created": init_result["tables_created"]}}
                    )
            except Exception as e:
                LOGGER.error(f"Error creating database tables: {e}")
        else:
            LOGGER.info(
                "Database validation passed",
                extra={"extra_data": {"tables_found": len(db_status["tables_found"])}}
            )
    except Exception as e:
        LOGGER.error(f"Database validation error during startup: {e} - app will start anyway")

    yield
    LOGGER.info("API application shutting down")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance with:
        - CORS middleware
        - Global exception handlers
        - All API routes
    """
    application = FastAPI(
        title="LA Land Wholesale Engine",
        description="Multi-market automated land wholesaling platform API",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # -------------------------------------------------------------------------
    # CORS Middleware
    # -------------------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------------------------------------------------------
    # Global Exception Handlers
    # -------------------------------------------------------------------------

    @application.exception_handler(ServiceUnavailableError)
    async def service_unavailable_handler(
        request: Request, exc: ServiceUnavailableError
    ) -> JSONResponse:
        """Handle external service unavailable errors."""
        LOGGER.error(f"Service unavailable: {exc}", extra={"extra_data": {"path": request.url.path}})
        return JSONResponse(
            status_code=503,
            content={
                "error": "service_unavailable",
                "message": str(exc),
                "detail": "An external service is temporarily unavailable. Please try again later.",
            },
        )

    @application.exception_handler(RateLimitError)
    async def rate_limit_handler(
        request: Request, exc: RateLimitError
    ) -> JSONResponse:
        """Handle rate limit errors from external services."""
        LOGGER.warning(f"Rate limit hit: {exc}", extra={"extra_data": {"path": request.url.path}})
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": str(exc),
                "detail": "Rate limit exceeded. Please try again later.",
            },
        )

    @application.exception_handler(ExternalServiceError)
    async def external_service_handler(
        request: Request, exc: ExternalServiceError
    ) -> JSONResponse:
        """Handle general external service errors."""
        LOGGER.error(f"External service error: {exc}", extra={"extra_data": {"path": request.url.path}})
        return JSONResponse(
            status_code=502,
            content={
                "error": "external_service_error",
                "message": str(exc),
                "detail": "An error occurred while communicating with an external service.",
            },
        )

    @application.exception_handler(ConfigurationError)
    async def configuration_handler(
        request: Request, exc: ConfigurationError
    ) -> JSONResponse:
        """Handle configuration errors."""
        LOGGER.error(f"Configuration error: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "configuration_error",
                "message": "Service misconfiguration",
                "detail": "Please contact the administrator.",
            },
        )

    @application.exception_handler(ValidationError)
    async def validation_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        """Handle validation errors."""
        LOGGER.warning(f"Validation error: {exc}", extra={"extra_data": {"path": request.url.path}})
        return JSONResponse(
            status_code=400,
            content={
                "error": "validation_error",
                "message": str(exc),
            },
        )

    @application.exception_handler(LALandWholesaleError)
    async def app_error_handler(
        request: Request, exc: LALandWholesaleError
    ) -> JSONResponse:
        """Handle all other application errors."""
        LOGGER.error(f"Application error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "application_error",
                "message": str(exc),
            },
        )

    # -------------------------------------------------------------------------
    # Include Routers
    # -------------------------------------------------------------------------
    application.include_router(health.router, tags=["Health"])

    # Add root health check (for Railway healthcheck - no dependencies)
    @application.get("/health")
    async def root_health_check():
        """Lightweight health check for Railway - always returns OK."""
        return {"status": "ok", "service": "lalandwholesale"}

    application.include_router(ingestion.router, prefix="/ingest", tags=["Ingestion"])
    application.include_router(leads.router, prefix="/leads", tags=["Leads"])
    application.include_router(outreach.router, prefix="/outreach", tags=["Outreach"])
    application.include_router(owners.router, prefix="/owners", tags=["Owners"])
    application.include_router(parcels.router, prefix="/parcels", tags=["Parcels"])
    application.include_router(scoring.router, prefix="/scoring", tags=["Scoring"])
    application.include_router(metrics.router, prefix="/metrics", tags=["Metrics"])
    application.include_router(config.router, prefix="/config", tags=["Configuration"])
    
    # New routes for multi-market and automation
    application.include_router(markets.router, prefix="/markets", tags=["Markets"])
    application.include_router(automation.router, prefix="/automation", tags=["Automation"])
    application.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
    application.include_router(twilio_webhooks.router, prefix="/twilio", tags=["Twilio"])
    
    # Buyer and disposition routes
    application.include_router(buyers.router, prefix="/buyers", tags=["Buyers"])
    application.include_router(dispositions.router, prefix="/dispo", tags=["Dispositions"])
    
    # Dashboard API
    application.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
    
    # Active Market (area locking)
    application.include_router(active_market.router, prefix="/active-market", tags=["Active Market"])
    
    # Caller Sheet (sales-call-first workflow)
    application.include_router(caller.router, prefix="/caller", tags=["Caller"])
    
    # Call Prep Pack (everything needed to quote and close)
    application.include_router(call_prep.router, prefix="/call-prep", tags=["Call Prep"])
    
    # Conversations (Inbox threads derived from outreach)
    application.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])

    # -------------------------------------------------------------------------
    # Serve Frontend Static Files (Production)
    # -------------------------------------------------------------------------
    frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    if os.path.exists(frontend_dist):
        application.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

        @application.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            """Catch-all route to serve React frontend for client-side routing."""
            # Exclude API routes from frontend serving
            api_prefixes = (
                "health", "ingest/", "leads/", "outreach/", "owners/", "parcels/",
                "scoring/", "metrics/", "config/", "markets/", "automation/",
                "webhooks/", "twilio/", "buyers/", "dispo/", "dashboard/",
                "active-market/", "caller/", "call-prep/", "conversations/",
                "docs", "redoc", "openapi.json"
            )
            if full_path.startswith(api_prefixes):
                return JSONResponse(status_code=404, content={"error": "not_found"})

            # Check if file exists in dist
            file_path = os.path.join(frontend_dist, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)

            # Default to index.html for client-side routing (including root "/")
            return FileResponse(os.path.join(frontend_dist, "index.html"))

        LOGGER.info(f"Serving frontend from {frontend_dist}")
    else:
        LOGGER.warning(f"Frontend dist folder not found at {frontend_dist} - API only mode")

    return application


# Create the application instance
app = create_app()

LOGGER.info("API application initialized")
