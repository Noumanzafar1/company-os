import subprocess
import sys
from uuid import uuid4

import pytest
from company_os.persistence.database import check_runtime, make_engine, transaction
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.seeds.synthetic import key


def test_real_runtime_role_and_force_rls(runtime, admin):
    with transaction(runtime) as conn:
        check_runtime(conn, "company_api")
        assert conn.execute(text("SELECT current_user")).scalar_one() == "company_api"
        with pytest.raises(DBAPIError):
            conn.execute(text("SET ROLE company_auth"))
    with admin.connect() as conn:
        tables = conn.execute(
            text(
                "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='app' AND c.relkind='r'"
            )
        ).all()
        assert len(tables) == 9
        assert all(enabled and forced for _, enabled, forced in tables)
        assert conn.execute(text("SHOW server_version_num")).scalar_one().startswith("18")


@pytest.mark.parametrize("letter,other", [("a", "b"), ("b", "a")])
def test_tenant_read_join_and_wrong_scope(runtime, letter, other):
    with transaction(runtime, key(f"user-{letter}"), key(f"workspace-{letter}"), 1) as conn:
        assert conn.execute(text("SELECT name FROM app.workspaces")).scalars().all() == [
            f"Workspace {letter.upper()}"
        ]
        result = (
            conn.execute(
                text(
                    "SELECT m.workspace_id FROM app.memberships m JOIN app.workspaces w ON w.id=m.workspace_id"
                )
            )
            .scalars()
            .all()
        )
        assert result == [key(f"workspace-{letter}")]
    with transaction(runtime, key(f"user-{letter}"), key(f"workspace-{other}"), 1) as conn:
        assert conn.execute(text("SELECT * FROM app.workspaces")).all() == []
        assert conn.execute(text("SELECT * FROM app.memberships")).all() == []


@pytest.mark.parametrize(
    "context",
    [(None, None, None), (key("user-a"), None, None), (key("user-a"), key("workspace-a"), 99)],
)
def test_missing_or_stale_context_denies(runtime, context):
    with transaction(runtime, *context) as conn:
        for table in ["workspaces", "memberships", "audit_entries"]:
            assert conn.execute(text(f"SELECT * FROM app.{table}")).all() == []


def test_pool_success_error_and_cancelled_query_do_not_leak(runtime):
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        pid = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert conn.execute(text("SELECT name FROM app.workspaces")).scalar_one() == "Workspace A"
    with runtime.connect() as raw:
        assert raw.execute(
            text(
                "SELECT nullif(current_setting('app.principal_id',true),''), nullif(current_setting('app.workspace_id',true),''), nullif(current_setting('app.authz_epoch',true),'')"
            )
        ).one() == (None, None, None)
    for query in ["SELECT 1/0", "SELECT pg_sleep(1)"]:
        with (
            pytest.raises(DBAPIError),
            transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn,
        ):
            conn.execute(text("SET LOCAL statement_timeout='20ms'"))
            conn.execute(text(query))
        with runtime.connect() as conn:
            assert conn.execute(text("SELECT pg_backend_pid()")).scalar_one() == pid
            assert (
                conn.execute(
                    text("SELECT nullif(current_setting('app.workspace_id',true),'')")
                ).scalar_one()
                is None
            )
            assert conn.execute(text("SELECT * FROM app.workspaces")).all() == []
        with transaction(runtime, key("user-b"), key("workspace-b"), 1) as conn:
            assert (
                conn.execute(text("SELECT name FROM app.workspaces")).scalar_one() == "Workspace B"
            )


def audit_insert(conn, workspace):
    conn.execute(
        text("""INSERT INTO app.audit_entries(id,workspace_id,created_by,actor_id,actor_type,
        action_type,target_type,target_id,request_id,correlation_id,command_id,decision,outcome,
        change_summary,payload_hash,policy_version) VALUES(:id,:w,:p,:p,'user','test','workspace',:w,
        :id,:id,:id,'allow','test','Synthetic test',:hash,'phase-2')"""),
        {"id": uuid4(), "w": workspace, "p": key("user-a"), "hash": "0" * 64},
    )


def test_tenant_writes_and_sql_grants(runtime):
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        audit_insert(conn, key("workspace-a"))
    for workspace in [key("workspace-b"), uuid4()]:
        with (
            pytest.raises(DBAPIError),
            transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn,
        ):
            audit_insert(conn, workspace)
    with pytest.raises(DBAPIError), transaction(runtime) as conn:
        audit_insert(conn, key("workspace-a"))
    for query in [
        "SELECT * FROM app.users",
        "SELECT * FROM app.auth_sessions",
        "UPDATE app.audit_entries SET outcome='altered'",
        "DELETE FROM app.audit_entries",
        "UPDATE app.memberships SET status='revoked'",
        "CREATE TABLE app.bad(id int)",
    ]:
        with (
            pytest.raises(DBAPIError),
            transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn,
        ):
            conn.execute(text(query))


def test_force_rls_applies_to_non_super_table_owner(admin):
    with admin.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("CREATE ROLE company_test_owner NOLOGIN NOSUPERUSER NOBYPASSRLS"))
            conn.execute(text("GRANT USAGE ON SCHEMA app TO company_test_owner"))
            conn.execute(text("ALTER TABLE app.workspaces OWNER TO company_test_owner"))
            conn.execute(text("SET LOCAL ROLE company_test_owner"))
            assert conn.execute(text("SELECT * FROM app.workspaces")).all() == []
        finally:
            tx.rollback()


def test_worker_is_least_privileged_and_starts(worker_env):
    assert "DATABASE_URL" not in worker_env
    engine = make_engine(worker_env["WORKER_DATABASE_URL"])
    try:
        with transaction(engine) as conn:
            check_runtime(conn, "company_worker")
            assert conn.execute(text("SELECT current_user")).scalar_one() == "company_worker"
        with pytest.raises(DBAPIError), transaction(engine) as conn:
            conn.execute(text("SELECT * FROM app.workspaces"))
        with pytest.raises(DBAPIError), transaction(engine) as conn:
            conn.execute(text("SELECT * FROM app.profile()"))
        result = subprocess.run(
            [sys.executable, "-m", "apps.worker.main", "--once"],
            env=worker_env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
        assert '"status": "healthy"' in result.stdout
        assert '"status":"stopped"' in result.stdout
    finally:
        engine.dispose()


@pytest.mark.parametrize("credential", ["DATABASE_URL", "MIGRATION_DATABASE_URL"])
def test_worker_rejects_wrong_or_unsafe_runtime_credential(db_env, worker_env, credential):
    result = subprocess.run(
        [sys.executable, "-m", "apps.worker.main", "--once"],
        env={**worker_env, "WORKER_DATABASE_URL": db_env[credential]},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "Unsafe runtime database role" in result.stderr
    assert "check_runtime" in result.stderr
    assert '"status": "healthy"' not in result.stdout


def test_worker_requires_its_explicit_credential_without_api_fallback(db_env, worker_env):
    # A legacy caller supplying only DATABASE_URL must fail closed, not use that URL.
    legacy_env = {k: v for k, v in worker_env.items() if k != "WORKER_DATABASE_URL"}
    legacy_env["DATABASE_URL"] = db_env["WORKER_DATABASE_URL"]
    result = subprocess.run(
        [sys.executable, "-m", "apps.worker.main", "--once"],
        env=legacy_env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "KeyError: 'WORKER_DATABASE_URL'" in result.stderr
    assert '"status": "healthy"' not in result.stdout


def test_unsafe_owner_role_rejected(admin):
    with admin.connect() as conn, pytest.raises(RuntimeError, match="Unsafe"):
        check_runtime(conn, "company_api")


def test_subtype_and_version_constraints(admin):
    with pytest.raises(DBAPIError), admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app.principals(id,kind,status,created_by,updated_by) VALUES(:id,'user','active',:p,:p)"
            ),
            {"id": uuid4(), "p": key("user-a")},
        )
    with pytest.raises(DBAPIError), admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE app.memberships SET workspace_id=:w,record_version=record_version+1 WHERE id=:id"
            ),
            {"w": key("workspace-b"), "id": key("membership-a")},
        )
    with pytest.raises(DBAPIError), admin.begin() as conn:
        conn.execute(
            text("UPDATE app.workspaces SET name='changed' WHERE id=:id"),
            {"id": key("workspace-a")},
        )
