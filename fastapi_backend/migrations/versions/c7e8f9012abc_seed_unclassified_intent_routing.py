"""Seed unclassified intent routing for classifier fallback.

Revision ID: c7e8f9012abc
Revises: fb609a2f3088
Create Date: 2026-05-05

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c7e8f9012abc"
down_revision: Union[str, Sequence[str], None] = "fb609a2f3088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO intent_routing (intent_name, service_id, taxonomy_version, created_by)
        VALUES ('unclassified', 'ollama-llama3', '1.0', 'admin')
        ON CONFLICT (intent_name) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM intent_routing WHERE intent_name = 'unclassified';
        """
    )
