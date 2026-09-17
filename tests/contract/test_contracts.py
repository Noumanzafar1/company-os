import json
from pathlib import Path

from scripts.contracts import snapshot
from tests.phase3_scope import CORE_SUFFIXES, CORE_TABLES, FOUNDATION_PATHS, FOUNDATION_TABLES


def test_openapi_snapshot_is_current():
    assert Path("packages/contracts/openapi.json").read_text(encoding="utf-8") == snapshot()


def test_only_authorized_phase_routes_exist():
    paths = json.loads(snapshot())["paths"]
    assert set(paths) == FOUNDATION_PATHS | {
        "/v1/workspaces/{workspace_id}" + suffix for suffix in CORE_SUFFIXES
    }


def test_migration_history_linear_and_only_authorized_tables(admin):
    from sqlalchemy import text

    with admin.connect() as conn:
        names = set(
            conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='app'")).scalars()
        )
        assert names == FOUNDATION_TABLES | CORE_TABLES
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0005_phase3_review_fixes"
        )
