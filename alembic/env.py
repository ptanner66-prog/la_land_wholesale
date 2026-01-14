"""Alembic migrations environment configuration."""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine

from alembic import context

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import get_settings
from core.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Get database URL from settings
settings = get_settings()
DATABASE_URL = settings.database_url

# Check if using SQLite
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=DATABASE_URL,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=IS_SQLITE,  # SQLite batch mode for ALTER operations
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Create engine with SQLite compatibility
    if IS_SQLITE:
        connectable = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
        )
    else:
        connectable = create_engine(DATABASE_URL)
    
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=IS_SQLITE,  # SQLite batch mode for ALTER operations
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
