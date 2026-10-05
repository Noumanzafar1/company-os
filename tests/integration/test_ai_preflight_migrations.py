"""Measure grants on real 0026, then prove exact no-history 0027 rollback."""

import os
import subprocess
import sys
from urllib.parse import urlparse
from uuid import uuid4

import psycopg
from psycopg import sql


def test_preflight_downgrade_restores_all_company_auth_table_privileges():
    base = os.environ["MIGRATION_DATABASE_URL"]
    assert urlparse(base).hostname in {"127.0.0.1", "localhost", "::1"}
    database = "company_os_test_b1_privileges_" + uuid4().hex[:12]
    admin = base.rsplit("/", 1)[0] + "/postgres"
    env = {**os.environ, "COMPANY_ENV": "test"}
    for key in ("MIGRATION_DATABASE_URL", "DATABASE_URL", "WORKER_DATABASE_URL"):
        env[key] = os.environ[key].rsplit("/", 1)[0] + "/" + database

    def migrate(action, revision):
        subprocess.run(
            [sys.executable, "-m", "alembic", action, revision],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def grants():
        with psycopg.connect(
            env["MIGRATION_DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:")
        ) as db:
            # All app tables, including every existing table affected by 0027.
            # Compare privilege and grant-option, not only has_table_privilege.
            return set(
                db.execute(
                    "SELECT table_name,privilege_type,is_grantable FROM information_schema.table_privileges "
                    "WHERE table_schema='app' AND grantee='company_auth'"
                ).fetchall()
            )

    with psycopg.connect(
        admin.replace("postgresql+psycopg:", "postgresql:"), autocommit=True
    ) as owner:
        owner.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            migrate("upgrade", "0026_phase6b_review_fixes")
            before = grants()
            assert {p for t, p, _ in before if t == "authority_test_targets"} == {
                "SELECT",
                "UPDATE",
            }
            migrate("upgrade", "0027_phase6b_live_preflight")
            upgraded = grants()
            assert before <= upgraded
            expected_added = {
                "authority_test_targets": {"INSERT"},
                "budgets": {"SELECT", "INSERT", "UPDATE"},
                "ai_registry": {"INSERT"},
                "ai_routes": {"INSERT"},
                "ai_route_states": {"INSERT"},
                "model_runs": {"SELECT"},
                "ai_preflight_gates": {"SELECT", "INSERT"},
                "ai_preflight_routes": {"SELECT", "INSERT"},
            }
            assert upgraded - before == {
                (table, privilege, "NO")
                for table, privileges in expected_added.items()
                for privilege in privileges
            }
            migrate("downgrade", "0026_phase6b_review_fixes")
            assert grants() == before
            migrate("upgrade", "0027_phase6b_live_preflight")
            assert grants() == upgraded
            migrate("upgrade", "head")
            assert grants() == upgraded
        finally:
            # Only the empty disposable database created by this test is removed.
            assert database.startswith("company_os_test_b1_privileges_")
            owner.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
