# app/models/base.py
"""Declarative SQLAlchemy Base used by ORM models."""

from __future__ import annotations

import logging
from sqlalchemy.orm import declarative_base

Base = declarative_base()

logger = logging.getLogger(__name__)

