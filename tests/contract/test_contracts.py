import json
from pathlib import Path

from scripts.contracts import snapshot


def test_openapi_snapshot_is_current():
    assert Path("packages/contracts/openapi.json").read_text(encoding="utf-8") == snapshot()


def test_only_foundation_routes_exist():
    paths = json.loads(snapshot())["paths"]
    assert set(paths) == {
        "/v1/me",
        "/v1/auth/session",
        "/v1/auth/logout",
        "/health/live",
        "/health/ready",
        "/v1/workspaces/{workspace_id}",
        "/v1/workspaces/{workspace_id}/health",
    }


def test_migration_history_linear_and_only_foundation_tables(admin):
    from sqlalchemy import text

    with admin.connect() as conn:
        names = set(
            conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='app'")).scalars()
        )
        assert names == {
            "workspaces",
            "principals",
            "users",
            "service_identities",
            "roles",
            "role_permissions",
            "memberships",
            "audit_entries",
            "auth_sessions",
        }
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0002_identity_guards"
        )
