# fastapi_backend/main.py
"""Compatibility entrypoint for Docker/uvicorn."""

from __future__ import annotations

from fastapi import FastAPI

from app.main import app as app

__all__ = ["app"]

