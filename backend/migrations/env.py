from alembic import context

from chatabae.db import Base

connection = context.config.attributes.get("connection")
if connection is None:
    from sqlalchemy import create_engine
    from chatabae.config import load_settings
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = create_engine(f"sqlite:///{settings.database_path.as_posix()}").connect()
context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
