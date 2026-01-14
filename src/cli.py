#!/usr/bin/env python3
"""Command Line Interface for LA Land Wholesale Engine.

Requires: pip install -r requirements.txt

Usage:
    cd src
    python cli.py server       # Start API server
    python cli.py score        # Run lead scoring
    python cli.py ingest full  # Run full ingestion
    python cli.py info         # Show configuration
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
import uvicorn

from core.config import get_settings
from core.logging_config import get_logger, setup_logging
from core.db import get_session

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

app = typer.Typer(help="LA Land Wholesale Engine CLI")
ingest_app = typer.Typer(help="Ingestion commands")
outreach_app = typer.Typer(help="Outreach commands")
app.add_typer(ingest_app, name="ingest")
app.add_typer(outreach_app, name="outreach")


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """LA Land Wholesale Engine - Automated Real Estate Wholesaling Platform."""
    log_level = "DEBUG" if verbose else SETTINGS.log_level
    setup_logging(level=log_level)


# =============================================================================
# Ingestion Commands
# =============================================================================


@ingest_app.command("tax-roll")
def ingest_tax_roll(
    file_path: str = typer.Argument(..., help="Path to tax roll CSV"),
) -> None:
    """Ingest tax roll data."""
    from domain.ingestion import IngestionService

    typer.echo(f"Ingesting tax roll from: {file_path}")
    service = IngestionService()
    result = service.run_pipeline(tax_roll_path=file_path)
    typer.echo(f"Result: {result}")


@ingest_app.command("gis")
def ingest_gis(
    file_path: str = typer.Argument(..., help="Path to GIS file"),
) -> None:
    """Ingest GIS data."""
    from domain.ingestion import IngestionService

    typer.echo(f"Ingesting GIS from: {file_path}")
    service = IngestionService()
    result = service.run_pipeline(gis_path=file_path)
    typer.echo(f"Result: {result}")


@ingest_app.command("adjudicated")
def ingest_adjudicated(
    file_path: str = typer.Argument(..., help="Path to adjudicated CSV"),
) -> None:
    """Ingest adjudicated property list."""
    from domain.ingestion import IngestionService

    typer.echo(f"Ingesting adjudicated from: {file_path}")
    service = IngestionService()
    result = service.run_pipeline(adjudicated_path=file_path)
    typer.echo(f"Result: {result}")


@ingest_app.command("full")
def ingest_full() -> None:
    """Run full ingestion pipeline with default files."""
    from domain.ingestion import IngestionService

    typer.echo("Running full ingestion pipeline...")
    service = IngestionService()
    result = service.run_full_pipeline()

    if result.success:
        typer.secho(f"✓ Ingestion complete in {result.total_duration_seconds:.2f}s", fg="green")
    else:
        typer.secho("✗ Ingestion had failures", fg="red")

    for stage in result.stages:
        status = "✓" if stage.success else "✗"
        typer.echo(f"  {status} {stage.stage}: processed={stage.records_processed}, created={stage.records_created}")


# =============================================================================
# Scoring Commands
# =============================================================================


@app.command("score")
def score_leads(
    min_score: Optional[int] = typer.Option(None, help="Minimum score filter for stats"),
) -> None:
    """Run lead scoring engine."""
    from domain.scoring import ScoringService

    typer.echo("Running lead scoring...")
    with get_session() as session:
        service = ScoringService(session)
        result = service.score_all(min_score=min_score)

    typer.secho(f"✓ Scored {result.updated} leads", fg="green")
    typer.echo(f"  Average Score: {result.average_score:.1f}")
    typer.echo(f"  High Priority: {result.high_priority_count}")
    typer.echo(f"  Duration: {result.duration_seconds:.2f}s")


# =============================================================================
# Outreach Commands
# =============================================================================


@outreach_app.command("run")
def run_outreach(
    limit: int = typer.Option(50, help="Max messages to send"),
    min_score: Optional[int] = typer.Option(None, help="Minimum motivation score"),
) -> None:
    """Run outreach batch."""
    from domain.outreach import OutreachService

    typer.echo(f"Running outreach batch (limit={limit})...")
    typer.echo(f"Dry Run Mode: {SETTINGS.dry_run}")

    with get_session() as session:
        service = OutreachService(session)
        result = service.send_batch(limit=limit, min_score=min_score)

    if result.successful > 0:
        typer.secho(f"✓ Sent {result.successful}/{result.total_attempted} messages", fg="green")
    else:
        typer.echo(f"No messages sent (attempted: {result.total_attempted})")

    if result.failed > 0:
        typer.secho(f"  ✗ {result.failed} failures", fg="yellow")


@outreach_app.command("stats")
def outreach_stats(
    days: int = typer.Option(7, help="Number of days to show"),
) -> None:
    """Show outreach statistics."""
    from domain.outreach import OutreachService

    with get_session() as session:
        service = OutreachService(session)
        stats = service.get_daily_stats(days=days)

    typer.echo(f"Outreach Statistics (last {days} days):")
    typer.echo(f"  Total Sent: {stats['total_sent']}")
    typer.echo(f"  Total Dry Run: {stats['total_dry_run']}")
    typer.echo(f"  Max Per Day: {stats['max_per_day']}")


# =============================================================================
# Server Commands
# =============================================================================


@app.command("server")
def run_server(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to bind to"),
    reload: bool = typer.Option(False, help="Enable auto-reload for development"),
) -> None:
    """Start the API server."""
    typer.echo(f"Starting API server on {host}:{port}...")
    uvicorn.run("api.app:app", host=host, port=port, reload=reload)


@app.command("scheduler")
def run_scheduler_cmd() -> None:
    """Start the background scheduler."""
    from scheduler.runner import run_scheduler_blocking

    typer.echo("Starting scheduler...")
    run_scheduler_blocking()


@app.command("dashboard")
def run_dashboard(
    port: int = typer.Option(8501, help="Port for Streamlit dashboard"),
) -> None:
    """Start the Streamlit dashboard."""
    import subprocess

    typer.echo(f"Starting Streamlit dashboard on port {port}...")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "dashboard/streamlit_app.py",
        "--server.port", str(port),
        "--server.address", "0.0.0.0",
    ])


# =============================================================================
# Utility Commands
# =============================================================================


@app.command("bootstrap")
def bootstrap() -> None:
    """Run application bootstrap (migrations, extensions)."""
    from core.bootstrap import bootstrap_application

    typer.echo("Running application bootstrap...")
    try:
        bootstrap_application()
        typer.secho("✓ Bootstrap completed successfully", fg="green")
    except Exception as e:
        typer.secho(f"✗ Bootstrap failed: {e}", fg="red")
        raise typer.Exit(1)


@app.command("info")
def show_info() -> None:
    """Show application configuration info."""
    typer.echo("LA Land Wholesale Engine Configuration:")
    typer.echo(f"  Environment: {SETTINGS.environment}")
    typer.echo(f"  Dry Run: {SETTINGS.dry_run}")
    typer.echo(f"  Log Level: {SETTINGS.log_level}")
    typer.echo(f"  Max SMS/Day: {SETTINGS.max_sms_per_day}")
    typer.echo(f"  Min Score: {SETTINGS.min_motivation_score}")
    typer.echo(f"  Parish: {SETTINGS.default_parish}")
    typer.echo(f"  Twilio Configured: {bool(SETTINGS.twilio_account_sid)}")
    typer.echo(f"  OpenAI Configured: {bool(SETTINGS.openai_api_key)}")


if __name__ == "__main__":
    app()
