# fastapi_backend/scripts/migrate_taxonomy.py
"""One-off script to load taxonomy.yaml into intent_routing."""

from __future__ import annotations

import asyncio
import logging
import os

import yaml
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.db.session import AsyncSessionLocal
from app.models import IntentRouting

logger = logging.getLogger(__name__)

TAXONOMY_PATH = os.path.join(os.path.dirname(__file__), "..", "taxonomy.yaml")


async def migrate() -> None:
    """Upsert taxonomy entries into the intent_routing table."""
    logger.info("Reading taxonomy from %s...", TAXONOMY_PATH)
    if not os.path.exists(TAXONOMY_PATH):
        raise FileNotFoundError("taxonomy.yaml not found at " + TAXONOMY_PATH)

    with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    version = data.get("version", "1.0.0")
    intents = data.get("intents", [])

    logger.info("Found %d intents in version %s.", len(intents), version)

    async with AsyncSessionLocal() as session:
        for item in intents:
            stmt = (
                insert(IntentRouting)
                .values(
                    intent_name=item["label"],
                    service_id=item["service_id"],
                    taxonomy_version=version,
                    created_by="system-migration",
                    is_active=True,
                )
                .on_conflict_do_update(
                    index_elements=["intent_name"],
                    set_={
                        "service_id": item["service_id"],
                        "taxonomy_version": version,
                        "is_active": True,
                    },
                )
            )
            await session.execute(stmt)

        await session.commit()

    logger.info("Migration completed successfully.")


if __name__ == "__main__":
    asyncio.run(migrate())

