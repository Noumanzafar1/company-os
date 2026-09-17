import os

from alembic import context
from sqlalchemy import create_engine, pool


def run_migrations_online() -> None:
    engine = create_engine(os.environ["MIGRATION_DATABASE_URL"], poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
