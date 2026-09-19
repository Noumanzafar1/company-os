"""Disposable browser-test database only. Never modifies the persistent fixture."""

import os
import re
import sys

import psycopg
from psycopg import sql


def main() -> None:
    operation, name = sys.argv[1:]
    if operation not in {"create", "drop"} or not re.fullmatch("company_os_e2e_[0-9a-f]{12}", name):
        raise ValueError("INVALID_DISPOSABLE_DATABASE")
    url = os.environ["MIGRATION_DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(
        url.replace("postgresql+psycopg:", "postgresql:"), autocommit=True
    ) as conn:
        command = "CREATE DATABASE {}" if operation == "create" else "DROP DATABASE {} WITH (FORCE)"
        conn.execute(sql.SQL(command).format(sql.Identifier(name)))


if __name__ == "__main__":
    main()
