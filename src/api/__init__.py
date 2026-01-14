"""FastAPI backend for LA Land Wholesale platform."""
from __future__ import annotations

from .app import create_app, app

__all__ = ["create_app", "app"]
