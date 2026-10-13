"""Add group chat members and the speaking character of a message."""
from alembic import op
from sqlalchemy import Column, JSON, String, inspect

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "conversations" in tables and "member_ids" not in {column["name"] for column in inspector.get_columns("conversations")}:
        op.add_column("conversations", Column("member_ids", JSON(none_as_null=True), nullable=True))
    if "messages" in tables and "character_id" not in {column["name"] for column in inspector.get_columns("messages")}:
        op.add_column("messages", Column("character_id", String, nullable=True))


def downgrade():
    # Keep group membership and speakers on an operator-controlled downgrade.
    pass
