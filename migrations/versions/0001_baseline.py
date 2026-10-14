"""Nexora v0.5 baseline.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-14
"""

from alembic import op

from app.db import Base
import app.models  # noqa: F401


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # checkfirst=True makes this safe for legacy v0.4 databases that already
    # contain the baseline tables while still creating a fresh schema.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Pilot baseline is intentionally non-destructive. Data removal requires
    # an explicit future migration rather than a broad drop_all.
    pass
