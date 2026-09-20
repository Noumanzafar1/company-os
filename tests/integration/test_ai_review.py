"""Independent-review regressions: immutable evaluation inputs and real-role RLS."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from company_os.application import ai_evaluations, ai_gateway
from company_os.application import runtime as commands
from company_os.persistence.ai import get, insert
from company_os.persistence.database import make_engine, rows, transaction
from company_os.persistence.runtime import clock, update
from company_os.workflow.runtime import execute_claim
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.integration.test_ai_gateway import dispatch_fixture_events as drain_fixture
from tests.integration.test_authority import PREFIX, post
from tests.integration.test_identity_review import offline_mfa as mfa_fixture
from tests.integration.test_runtime import WA, A, B
from tests.integration.test_runtime import engine as worker_fixture
from tests.phase6b_scope import AI_TABLES

engine = worker_fixture
offline_mfa = mfa_fixture
dispatch_fixture_events = drain_fixture


def completed_batch(runtime, engine, scope=A):
    worker_scope = (WA[0], scope[1], scope[2])
    with transaction(runtime, *scope) as conn:
        batch = ai_evaluations.request_evaluation(conn, "seed", uuid4())
        saved = get(conn, "ai_evaluation_batches", batch["id"])
    for identifier in sum(saved["body"]["runs"].values(), []):
        with transaction(engine, *worker_scope) as conn:
            run = get(conn, "agent_runs", identifier)
            job = rows(conn, "SELECT * FROM app.jobs WHERE id=:id", {"id": run["job_id"]})[0]
            update(
                conn,
                "jobs",
                job,
                priority="interactive",
                available_at=clock(conn) - timedelta(days=1),
            )
            claim = commands.claim(conn, "review-" + uuid4().hex)
            assert claim["id"] == job["id"]
        assert execute_claim(engine, worker_scope, "review", claim, None)
    return saved


def evaluation(runtime, engine, scope=A):
    batch = completed_batch(runtime, engine, scope)
    with transaction(engine, WA[0], scope[1], scope[2]) as conn:
        ai_evaluations.finalize(conn)
        result = rows(
            conn, "SELECT * FROM app.ai_evaluations WHERE batch_id=:id", {"id": batch["id"]}
        )[0]
        assert (
            result["body"]["decision"] == result["current_result"]["decision"] == "technical_pass"
        )
    return batch, result


def source(conn, batch, cohort="candidate"):
    run = get(conn, "agent_runs", batch["body"]["runs"][cohort][0])
    assert run["state"] == "accepted"
    return get(conn, "context_packs", run["context_id"])["source_id"]


def proposal(client, headers, value):
    return post(
        client,
        headers,
        "/ai-routes/propose",
        {
            "route_id": str(value["route_id"]),
            "evaluation_id": str(value["id"]),
            "rollback_route_id": str(value["current_route_id"]),
        },
    )


def approved(client, headers, value):
    response = proposal(client, headers, value)
    assert response.status_code == 200, response.text
    rid = response.json()["data"]["request_id"]
    detail = client.get(PREFIX + "/approvals/" + rid, headers=headers).json()["data"]
    response = post(
        client,
        headers,
        "/approvals/" + rid + "/decide",
        {
            "decision": "approve",
            "rationale": "Reviewed current synthetic contexts",
            "expected_scope_hash": detail["request"]["scope_hash"],
        },
        1,
    )
    assert response.status_code == 200, response.text
    return rid


def promote(client, headers, rid):
    return post(
        client, headers, "/ai-routes/" + rid + "/promote", {"rationale": "Synthetic review"}, 2
    )


@pytest.mark.parametrize("cohort", ["candidate", "current"])
def test_revocation_before_finalize_keeps_denominator(runtime, engine, cohort):
    batch = completed_batch(runtime, engine)
    with transaction(runtime, *A) as conn:
        ai_gateway.revoke(conn, source(conn, batch, cohort), 1)
    with transaction(engine, *WA) as conn:
        ai_evaluations.finalize(conn)
        saved = rows(
            conn, "SELECT * FROM app.ai_evaluations WHERE batch_id=:id", {"id": batch["id"]}
        )[0]
        assert saved["body"]["decision"] == "technical_fail"
        assert saved["body"]["sample_count"] == saved["current_result"]["sample_count"] == 2
        assert "STALE_EVALUATION_CONTEXT" in saved["body"]["hard_failure_examples"]
        invalid = saved["body"] if cohort == "candidate" else saved["current_result"]
        assert invalid["cost_per_useful_output"] is None


def test_revocation_before_proposal_is_typed(runtime, engine, client, offline_mfa):
    batch, value = evaluation(runtime, engine)
    with transaction(runtime, *A) as conn:
        ai_gateway.revoke(conn, source(conn, batch), 1)
    response = proposal(client, offline_mfa, value)
    assert response.status_code == 423 and "EVALUATION_STALE" in response.text


def assert_no_activation(conn, value, rid):
    assert ai_gateway.active_route(conn)["id"] == value["current_route_id"]
    assert not rows(
        conn,
        "SELECT u.id FROM app.approval_uses u JOIN app.approval_manifests m ON m.id=u.manifest_id WHERE m.request_id=:id",
        {"id": rid},
    )
    assert get(conn, "ai_evaluations", value["id"])["body"] == value["body"]


def test_revocation_after_approval_blocks_app_and_direct_use(runtime, engine, client, offline_mfa):
    batch, value = evaluation(runtime, engine)
    rid = approved(client, offline_mfa, value)
    with transaction(runtime, *A) as conn:
        ai_gateway.revoke(conn, source(conn, batch), 1)
    response = promote(client, offline_mfa, rid)
    assert response.status_code == 423 and "EVALUATION_STALE" in response.text
    with transaction(runtime, *A) as conn:
        assert_no_activation(conn, value, rid)
        manifest = rows(
            conn, "SELECT * FROM app.approval_manifests WHERE request_id=:id", {"id": rid}
        )[0]
        session = rows(
            conn,
            "SELECT d.session_id id FROM app.approval_decisions d JOIN app.approval_manifests m ON m.decision_id=d.id WHERE m.id=:id",
            {"id": manifest["id"]},
        )[0]["id"]
    # Use the actual approving session, without going through application checks.
    # The immutable decision stores the session even if scope format changes.
    from company_os.persistence.authority import insert as authority_insert

    with pytest.raises(DBAPIError, match="EVALUATION_STALE"), transaction(runtime, *A) as conn:
        authority_insert(
            conn,
            "approval_uses",
            {
                "manifest_id": manifest["id"],
                "activation_route_id": value["route_id"],
                "activation_session_id": session,
                "use_number": 1,
                "spend_reserved": 0,
                "volume": 1,
            },
        )


@pytest.mark.parametrize("winner", ["revocation", "promotion"])
def test_authoritative_freshness_lock_race(
    runtime, engine, admin, db_env, client, offline_mfa, winner
):
    batch, value = evaluation(runtime, engine)
    rid = approved(client, offline_mfa, value)
    with transaction(runtime, *A) as conn:
        sid = source(conn, batch)
    separate = make_engine(db_env["DATABASE_URL"], pool_size=3)
    entered, release = Event(), Event()

    def revoke_first():
        with transaction(separate, *A) as conn:
            ai_gateway.revoke(conn, sid, 1)
            entered.set()
            assert release.wait(15)

    def revoke_second():
        entered.set()
        with transaction(separate, *A) as conn:
            ai_gateway.revoke(conn, sid, 1)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            if winner == "revocation":
                revoking = pool.submit(revoke_first)
                assert entered.wait(10)
                promoting = pool.submit(promote, client, offline_mfa, rid)
                # Wait for a real PostgreSQL lock wait, never a timing assumption.
                wait_for_lock(admin)
                release.set()
                revoking.result(15)
                response = promoting.result(15)
                assert response.status_code == 423 and "EVALUATION_STALE" in response.text
            else:
                # Hold the exact helper's locks in the activation transaction;
                # inject a barrier immediately after application freshness check.
                original = ai_evaluations.require_current

                def barrier(conn, eid):
                    original(conn, eid)
                    entered.set()
                    assert release.wait(15)

                with pytest.MonkeyPatch.context() as patch:
                    patch.setattr(ai_evaluations, "require_current", barrier)
                    promoting = pool.submit(promote, client, offline_mfa, rid)
                    assert entered.wait(10)
                    revoking = pool.submit(revoke_second)
                    wait_for_lock(admin)
                    release.set()
                    response = promoting.result(15)
                    assert response.status_code == 200, response.text
                    revoking.result(15)
            with transaction(runtime, *A) as conn:
                assert get(conn, "ai_fixture_sources", sid)["state"] == "revoked"
                assert get(conn, "ai_evaluations", value["id"])["body"] == value["body"]
                if winner == "revocation":
                    assert_no_activation(conn, value, rid)
                else:
                    assert ai_gateway.active_route(conn)["id"] == value["route_id"]
                    assert rows(
                        conn,
                        "SELECT id FROM app.audit_entries WHERE action_type='ai.route_promoted' AND target_id=:id",
                        {"id": value["route_id"]},
                    )
    finally:
        release.set()
        separate.dispose()


def wait_for_lock(admin):
    import time

    for _ in range(150):
        with admin.connect() as conn:
            if conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND usename='company_api'"
                )
            ).scalar_one():
                return
        time.sleep(0.02)
    pytest.fail("Expected real blocked transaction")


@pytest.mark.parametrize("defect", ["age", "current_route", "route_hash", "dataset_hash"])
def test_existing_evaluation_release_guards(runtime, engine, client, offline_mfa, defect):
    batch, value = evaluation(runtime, engine)
    # Create separate immutable negative fixtures, never rewrite history or
    # disable a trigger. Runtime worker insert ownership is exercised here.
    with transaction(runtime, *A) as conn:
        clone = insert(conn, "ai_evaluation_batches", {"body": batch["body"]})
    fields = {
        k: value[k]
        for k in (
            "route_id",
            "dataset_id",
            "binding_hash",
            "body",
            "current_route_id",
            "current_result",
        )
    }
    fields["batch_id"] = clone["id"]
    if defect == "age":
        with transaction(engine, *WA) as conn:
            fields["created_at"] = clock(conn) - timedelta(days=31)
    elif defect == "current_route":
        fields["current_route_id"] = value["route_id"]
    elif defect == "route_hash":
        fields["binding_hash"] = "0" * 64
    else:
        with transaction(runtime, *A) as conn:
            fields["dataset_id"] = rows(
                conn,
                "SELECT id FROM app.ai_registry WHERE kind='dataset' AND id<>:id LIMIT 1",
                {"id": value["dataset_id"]},
            )[0]["id"]
    with transaction(engine, *WA) as conn:
        invalid = insert(conn, "ai_evaluations", fields)
    response = proposal(client, offline_mfa, invalid)
    assert response.status_code == 423 and "EVALUATION_REQUIRED" in response.text


def test_populated_freshness_downgrade_preserves_history(runtime, engine, db_env):
    import subprocess
    import sys

    _, value = evaluation(runtime, engine)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0025_ai_evaluation_freshness"],
        env=db_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "Preserve evaluation freshness history" in result.stderr
    with transaction(runtime, *A) as conn:
        assert get(conn, "ai_evaluations", value["id"])["body"] == value["body"]
        assert (
            rows(conn, "SELECT version_num FROM public.alembic_version")[0]["version_num"]
            == "0026_phase6b_review_fixes"
        )


def test_all_eleven_tables_populated_runtime_roles(runtime, engine):
    # Populate both workspaces using real application/worker commands, including
    # calls/results and immutable evaluations. No owner-created row substitutes.
    values = {}
    for scope in (A, B):
        _, values[scope[1]] = evaluation(runtime, engine, scope)
    for connection, principal in ((runtime, A[0]), (engine, WA[0])):
        for scope in (A, B):
            actor = scope[0] if connection is runtime else principal
            with transaction(connection, actor, scope[1], 1) as conn:
                role = rows(
                    conn,
                    "SELECT current_user name,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user",
                )[0]
                assert role["name"] == (
                    "company_api" if connection is runtime else "company_worker"
                )
                assert not role["rolsuper"] and not role["rolbypassrls"]
                for table in sorted(AI_TABLES):
                    found = rows(conn, f"SELECT workspace_id FROM app.{table}")
                    assert found and {r["workspace_id"] for r in found} == {scope[1]}, table
                    other = B[1] if scope == A else A[1]
                    assert not rows(
                        conn, f"SELECT id FROM app.{table} WHERE workspace_id=:w", {"w": other}
                    ), table
            with transaction(connection) as conn:
                for table in sorted(AI_TABLES):
                    assert not rows(conn, f"SELECT id FROM app.{table}"), table
        # Every table denies DELETE. UPDATE is confined to exact mutable state
        # operations; even there changing tenant identity is forbidden.
        own_scope = A if connection is runtime else WA
        for table in sorted(AI_TABLES):
            with pytest.raises(DBAPIError), transaction(connection, *own_scope) as conn:
                conn.execute(text(f"DELETE FROM app.{table}"))
            with pytest.raises(DBAPIError), transaction(connection, *own_scope) as conn:
                conn.execute(text(f"UPDATE app.{table} SET workspace_id=:w"), {"w": B[1]})
            allowed = (
                {"context_packs", "agent_runs", "ai_evaluation_batches", "ai_fixture_sources"}
                if connection is runtime
                else {"model_runs", "ai_results", "ai_evaluations"}
            )
            if table not in allowed:
                with (
                    pytest.raises(DBAPIError, match="permission denied"),
                    transaction(connection, *own_scope) as conn,
                ):
                    conn.execute(text(f"INSERT INTO app.{table} DEFAULT VALUES"))
    # Composite FKs on each reference-bearing table are asserted explicitly.
    with transaction(runtime, *B) as conn:
        bcontext = rows(conn, "SELECT * FROM app.context_packs LIMIT 1")[0]
        brun = rows(conn, "SELECT * FROM app.agent_runs LIMIT 1")[0]
    with pytest.raises(DBAPIError, match="foreign key"), transaction(runtime, *A) as conn:
        insert(
            conn,
            "context_packs",
            {
                "source_id": bcontext["source_id"],
                "body": bcontext["body"],
                "content_hash": bcontext["content_hash"],
                "requester_id": A[0],
            },
        )
    with pytest.raises(DBAPIError, match="foreign key"), transaction(engine, *WA) as conn:
        insert(conn, "ai_results", {"agent_run_id": brun["id"], "body": {}})
    with transaction(engine, *WA) as conn:
        assert not rows(
            conn, "SELECT app.ai_evaluation_current(:id) ok", {"id": values[B[1]]["id"]}
        )[0]["ok"]
    # Remaining runtime-owned composite references fail before any row persists.
    with pytest.raises(DBAPIError, match="foreign key"), transaction(runtime, *A) as conn:
        insert(
            conn,
            "agent_runs",
            {
                k: brun[k]
                for k in (
                    "evaluation",
                    "job_id",
                    "input_id",
                    "route_id",
                    "context_id",
                    "task",
                    "scenario",
                    "state",
                    "correlation_id",
                )
            },
        )
    with pytest.raises(DBAPIError, match="foreign key"), transaction(engine, *WA) as conn:
        insert(
            conn,
            "ai_evaluations",
            {
                k: values[B[1]][k]
                for k in (
                    "batch_id",
                    "route_id",
                    "dataset_id",
                    "binding_hash",
                    "body",
                    "current_route_id",
                    "current_result",
                )
            },
        )
    with transaction(runtime, *A) as conn:
        cross_batch = insert(
            conn,
            "ai_evaluation_batches",
            {
                "body": {
                    "candidate": str(values[B[1]]["route_id"]),
                    "current": str(values[B[1]]["current_route_id"]),
                    "dataset": str(values[B[1]]["dataset_id"]),
                    "runs": {"candidate": [str(brun["id"])], "current": [str(brun["id"])]},
                }
            },
        )
        assert rows(
            conn, "SELECT * FROM app.ai_evaluation_inputs(:id)", {"id": cross_batch["id"]}
        ) == [{"run_id": None, "context_current": False}]
    with transaction(engine, *WA) as conn:
        bcall = rows(conn, "SELECT * FROM app.model_runs LIMIT 1")[0]
    with pytest.raises(DBAPIError, match="Model call binding"), transaction(engine, *WA) as conn:
        insert(
            conn,
            "model_runs",
            {
                **{
                    k: bcall[k]
                    for k in (
                        "reservation_id",
                        "ordinal",
                        "provider",
                        "model_id",
                        "prompt_id",
                        "price_id",
                        "estimated_usd",
                    )
                },
                "agent_run_id": brun["id"],
                "request_key": uuid4().hex * 2,
                "status": "started",
            },
        )
