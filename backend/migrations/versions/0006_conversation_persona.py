"""Add the user's persona for each conversation."""
from alembic import op
from sqlalchemy import Column, JSON, inspect

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    if "conversations" in set(inspector.get_table_names()) and "persona" not in {column["name"] for column in inspector.get_columns("conversations")}:
        op.add_column("conversations", Column("persona", JSON(none_as_null=True), nullable=True))


def downgrade():
    # Keep stated personas on an operator-controlled downgrade.
    pass
