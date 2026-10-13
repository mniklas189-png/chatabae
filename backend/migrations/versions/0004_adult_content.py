"""Record an account's explicit 18+ confirmation for adult content."""
from alembic import op
from sqlalchemy import Column, Float, inspect

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    if "adult_confirmed_at" not in {column["name"] for column in inspect(op.get_bind()).get_columns("users")}:
        op.add_column("users", Column("adult_confirmed_at", Float, nullable=True))


def downgrade():
    # Keep the confirmation record on an operator-controlled downgrade.
    pass
