"""Local/test cluster bootstrap only. Schema history belongs exclusively to Alembic."""

import os
from urllib.parse import urlparse

import psycopg
from psycopg import sql


def bootstrap() -> None:
    if os.environ.get("COMPANY_ENV") not in {"development", "test"}:
        raise RuntimeError("Bootstrap is local/test only")
    url = os.environ["MIGRATION_DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:")
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Local bootstrap requires loopback database")
    with psycopg.connect(url.rsplit("/", 1)[0] + "/postgres", autocommit=True) as conn:
        for name, env in [
            ("company_api", "DATABASE_URL"),
            ("company_worker", "WORKER_DATABASE_URL"),
        ]:
            password = urlparse(os.environ[env]).password
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone():
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}"
                    ).format(sql.Identifier(name), sql.Literal(password))
                )
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='company_auth'").fetchone():
            conn.execute(
                "CREATE ROLE company_auth NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
            )
        dbname = parsed.path[1:]
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (dbname,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        conn.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(dbname))
        )
        conn.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO company_api,company_worker").format(
                sql.Identifier(dbname)
            )
        )
    print("Local database and non-owner runtime roles ready")


if __name__ == "__main__":
    bootstrap()
