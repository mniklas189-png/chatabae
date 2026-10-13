"""Persist image seed, quality and effective dimensions without altering existing assets."""
from alembic import op
from sqlalchemy import Column, JSON, inspect

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    if "generation_metadata" not in {column["name"] for column in inspect(op.get_bind()).get_columns("assets")}:
        op.add_column("assets", Column("generation_metadata", JSON, nullable=True))


def downgrade():
    # Retain reproducibility metadata on an operator-controlled downgrade.
    pass
