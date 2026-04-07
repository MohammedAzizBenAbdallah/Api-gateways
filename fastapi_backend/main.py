# fastapi_backend/main.py
from __future__ import annotations
"""Compatibility entrypoint for Docker/uvicorn."""
print("[DEBUG] Top-level main.py loaded!")

from fastapi import FastAPI

from app.main import app as app

__all__ = ["app"]
