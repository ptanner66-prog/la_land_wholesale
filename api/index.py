"""
Vercel serverless function entrypoint for FastAPI.

This file serves as the entry point for Vercel's Python runtime.
Vercel looks for an `app` variable that is a FastAPI/Starlette application.
"""
from __future__ import annotations

import os
import sys

# Add the project root to Python path so we can import from src/
# In Vercel's environment, the working directory is the project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_path = os.path.join(project_root, "src")

# Add both paths to ensure imports work correctly
if src_path not in sys.path:
    sys.path.insert(0, src_path)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now import the FastAPI app from src/api/app.py
# The app is created via create_app() and exported as `app`
from api.app import app

# Vercel Python runtime looks for this `app` variable
# It should be a ASGI application (FastAPI is ASGI-compatible)
__all__ = ["app"]
