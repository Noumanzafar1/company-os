from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, create_engine, text

EXPECTED_REVISION = "0005_phase3_review_fixes"


def make_engine(url: str, *, pool_size: int = 5) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=0,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


def check_runtime(connection: Connection, expected_role: str) -> None:
    role = (
        connection.execute(
            text("""
        SELECT rolname,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user
    """)
        )
        .mappings()
        .one()
    )
    owns = connection.execute(
        text("""
        SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='app' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user))
    """)
    ).scalar_one()
    if role["rolname"] != expected_role or role["rolsuper"] or role["rolbypassrls"] or owns:
        raise RuntimeError("Unsafe runtime database role")
    revision = connection.execute(
        text("SELECT version_num FROM public.alembic_version")
    ).scalar_one()
    if revision != EXPECTED_REVISION:
        raise RuntimeError("Incompatible database schema")


@contextmanager
def transaction(
    engine: Engine,
    principal_id: UUID | None = None,
    workspace_id: UUID | None = None,
    epoch: int | None = None,
) -> Iterator[Connection]:
    with engine.begin() as connection:
        # Explicit empty context also protects against accidental session-scoped settings.
        connection.execute(
            text("""
            SELECT set_config('app.principal_id',:p,true),
                   set_config('app.workspace_id',:w,true),set_config('app.authz_epoch',:e,true)
        """),
            {
                "p": str(principal_id) if principal_id else "",
                "w": str(workspace_id) if workspace_id else "",
                "e": str(epoch) if epoch else "",
            },
        )
        yield connection


def rows(
    connection: Connection, sql: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(text(sql), params or {}).mappings()]
