# fastapi_backend/main.py
from __future__ import annotations
"""Compatibility entrypoint for Docker/uvicorn."""
from fastapi import FastAPI

from app.main import app as app

__all__ = ["app"]
