"""Upgrade installations created before recovery and lineage were added."""
from alembic import op
from sqlalchemy import Boolean, Column, JSON, String, inspect
from chatabae.db import RecoveryCode, SpentRefresh

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    RecoveryCode.__table__.create(connection, checkfirst=True)
    SpentRefresh.__table__.create(connection, checkfirst=True)
    additions = {
        "auth_codes": [Column("session_id", String, nullable=True)],
        "characters": [Column("approved_internal", JSON, nullable=True)],
        "conversations": [Column("parent_id", String, nullable=True), Column("branch_message_id", String, nullable=True)],
        "memories": [Column("source_message_id", String, nullable=True), Column("automatic", Boolean, nullable=False, server_default="0")],
    }
    for table, columns in additions.items():
        existing = {column["name"] for column in inspect(connection).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)


def downgrade():
    # No automatic lossy downgrade of user data.
    pass
