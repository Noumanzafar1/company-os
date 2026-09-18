"""Phase 5 real-role authority tests; asymmetric MFA fixture is offline only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from time import perf_counter
from uuid import uuid4

import pytest
from company_os.application import authority
from company_os.application import runtime as commands
from company_os.persistence.authority import TABLES
from company_os.persistence.authority import get as authority_get
from company_os.persistence.authority import update as authority_update
from company_os.persistence.business import BusinessError
from company_os.persistence.database import make_engine, rows, transaction
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.seeds.synthetic import key
from tests.integration.test_identity_review import offline_mfa as signed_mfa_fixture
from tests.integration.test_runtime import WA, A, claim_exact
from tests.integration.test_runtime import engine as worker_engine_fixture

offline_mfa = signed_mfa_fixture
engine = worker_engine_fixture

PREFIX = f"/v1/workspaces/{key('workspace-a')}"


def proposal():
    return {
        "action": "runtime.synthetic_external_action",
        "targets": [{"id": str(key("a-authority-target-1")), "version": 1}],
        "payload": {"label": "Synthetic exact action", "scenario": "effect_success"},
        "maximum_uses": 1,
        "maximum_spend": "1",
        "maximum_volume": 1,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "rationale": "Synthetic founder review",
    }


def post(client, headers, path, body, version=None):
    return client.post(
        PREFIX + path,
        json=body,
        headers={
            **headers,
            "Idempotency-Key": str(uuid4()),
            **({"If-Match": str(version)} if version else {}),
        },
    )


def granted(client, headers, body=None):
    body = body or proposal()
    response = post(client, headers, "/approvals/request", body)
    assert response.status_code == 200, response.text
    identifier = response.json()["data"]["request_id"]
    detail = client.get(PREFIX + "/approvals/" + identifier, headers=headers).json()["data"]
    decision = {
        "decision": "approve",
        "rationale": "Reviewed exact synthetic scope",
        "expected_scope_hash": detail["request"]["scope_hash"],
    }
    response = post(client, headers, "/approvals/" + identifier + "/decide", decision, 1)
    assert response.status_code == 200, response.text
    return identifier, body


def test_mfa_role_and_rejected_request(client, login, offline_mfa):
    body = proposal()
    plain = login()
    created = post(client, plain, "/approvals/request", body).json()["data"]
    identifier = created["request_id"]
    detail = client.get(PREFIX + "/approvals/" + identifier, headers=plain).json()["data"]
    decision = {
        "decision": "approve",
        "rationale": "No fabricated MFA",
        "expected_scope_hash": detail["request"]["scope_hash"],
    }
    assert (
        post(client, plain, "/approvals/" + identifier + "/decide", decision, 1).status_code == 403
    )
    assert (
        post(client, login("b"), "/approvals/" + identifier + "/decide", decision, 1).status_code
        == 404
    )
    decision["decision"] = "reject"
    assert (
        post(client, offline_mfa, "/approvals/" + identifier + "/decide", decision, 1).status_code
        == 200
    )
    execute = {"payload": body["payload"], "targets": body["targets"], "logical_key": uuid4().hex}
    assert (
        post(client, offline_mfa, "/approvals/" + identifier + "/execute", execute).status_code
        == 423
    )


def test_payload_target_drift_and_valid_execution(client, offline_mfa, runtime, engine):
    identifier, body = granted(client, offline_mfa)
    execution = {"payload": body["payload"], "targets": body["targets"], "logical_key": uuid4().hex}
    altered = {**execution, "payload": {**body["payload"], "label": "Changed"}}
    response = post(client, offline_mfa, "/approvals/" + identifier + "/execute", altered)
    assert response.json()["data"]["reasons"] == ["PAYLOAD_CHANGED"]
    altered = {**execution, "targets": [{"id": str(key("a-authority-target-2")), "version": 1}]}
    assert post(client, offline_mfa, "/approvals/" + identifier + "/execute", altered).json()[
        "data"
    ]["reasons"] == ["TARGET_SET_CHANGED"]
    response = post(client, offline_mfa, "/approvals/" + identifier + "/execute", execution)
    assert response.status_code == 200, response.text
    input_id = response.json()["data"]["input_id"]
    with transaction(runtime, *A) as conn:
        commands.dispatch_outbox(conn)
        job = rows(conn, "SELECT * FROM app.jobs WHERE input_ref=:id", {"id": input_id})[0]
    claim = claim_exact(engine, job)
    from company_os.workflow.runtime import execute_claim

    assert execute_claim(engine, WA, "authority-test", claim, None)
    detail = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    assert detail["remaining_uses"] == 0
    assert detail["uses"][0]["state"] == "consumed"
    assert (
        post(client, offline_mfa, "/approvals/" + identifier + "/execute", execution).json()[
            "data"
        ]["input_id"]
        == input_id
    )
    with transaction(engine, *WA) as conn:
        assert (
            len(
                rows(
                    conn,
                    "SELECT * FROM app.approval_uses WHERE manifest_id=:m",
                    {"m": detail["manifest"]["id"]},
                )
            )
            == 1
        )
        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE app.approval_manifests SET manifest_hash=repeat('a',64) WHERE id=:id"),
                {"id": detail["manifest"]["id"]},
            )


def test_revocation_blocks_new_work(client, offline_mfa):
    identifier, body = granted(client, offline_mfa)
    assert (
        post(
            client,
            offline_mfa,
            "/approvals/" + identifier + "/revoke",
            {"rationale": "Withdraw unused authority"},
            2,
        ).status_code
        == 200
    )
    execution = {"payload": body["payload"], "targets": body["targets"], "logical_key": uuid4().hex}
    result = post(client, offline_mfa, "/approvals/" + identifier + "/execute", execution)
    assert result.json()["data"]["reasons"] == ["AUTHORITY_REVOKED"]


@pytest.mark.parametrize(
    "mutation,code",
    [
        ({"label": "Materially changed"}, "OBJECT_VERSION_CHANGED"),
        ({"suppressed": True}, "SUPPRESSED"),
        ({"rights_valid": False}, "RIGHTS_REVOKED"),
    ],
)
def test_current_target_state_overrides_authority(client, offline_mfa, runtime, mutation, code):
    identifier, _ = granted(client, offline_mfa)
    detail = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    with transaction(runtime, *A) as conn:
        save = conn.begin_nested()
        target = authority_get(conn, "authority_test_targets", key("a-authority-target-1"))
        authority_update(conn, "authority_test_targets", target, **mutation)
        assert authority.validate(conn, detail["manifest"]["id"]) == code
        save.rollback()


def test_database_clock_expiry(client, offline_mfa, runtime):
    body = proposal()
    body["expires_at"] = (datetime.now(UTC) + timedelta(seconds=3)).isoformat()
    identifier, _ = granted(client, offline_mfa, body)
    detail = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    with transaction(runtime, *A) as conn:
        conn.execute(
            text("SELECT pg_sleep_until(CAST(:t AS timestamptz))"), {"t": body["expires_at"]}
        )
        assert authority.validate(conn, detail["manifest"]["id"]) == "EXPIRED"


def test_request_and_decision_idempotency(client, offline_mfa):
    headers = {**offline_mfa, "Idempotency-Key": uuid4().hex}
    body = proposal()
    first = client.post(PREFIX + "/approvals/request", json=body, headers=headers)
    assert first.status_code == 200
    assert (
        client.post(PREFIX + "/approvals/request", json=body, headers=headers).json()
        == first.json()
    )
    assert (
        client.post(
            PREFIX + "/approvals/request", json={**body, "maximum_uses": 2}, headers=headers
        ).status_code
        == 409
    )
    identifier = first.json()["data"]["request_id"]
    detail = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    headers = {**offline_mfa, "Idempotency-Key": uuid4().hex, "If-Match": "1"}
    decision = {
        "decision": "approve",
        "rationale": "Exact scope reviewed",
        "expected_scope_hash": detail["request"]["scope_hash"],
    }
    first = client.post(
        PREFIX + "/approvals/" + identifier + "/decide", json=decision, headers=headers
    )
    assert first.status_code == 200, first.text
    assert (
        client.post(
            PREFIX + "/approvals/" + identifier + "/decide", json=decision, headers=headers
        ).json()
        == first.json()
    )


def test_supersession_and_l4_no_execution(client, offline_mfa):
    identifier, body = granted(client, offline_mfa)
    revised = {
        **body,
        "supersedes_id": identifier,
        "payload": {**body["payload"], "label": "Revised exact payload"},
    }
    assert post(client, offline_mfa, "/approvals/request", revised).status_code == 200
    execution = {"payload": body["payload"], "targets": body["targets"], "logical_key": uuid4().hex}
    assert post(client, offline_mfa, "/approvals/" + identifier + "/execute", execution).json()[
        "data"
    ]["reasons"] == ["AUTHORITY_SUPERSEDED"]
    result = post(
        client,
        offline_mfa,
        "/approvals/request",
        {**proposal(), "action": "runtime.synthetic_binding_decision"},
    )
    assert result.json()["data"]["result"] == "DENY"
    assert "HUMAN_ONLY" in result.json()["data"]["reasons"]


def test_fifty_contenders_ten_uses(client, offline_mfa, runtime, db_env, admin):
    body = {**proposal(), "maximum_uses": 10, "maximum_spend": "100", "maximum_volume": 100}
    identifier, body = granted(client, offline_mfa, body)
    details = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    with admin.begin() as conn:
        old = rows(conn, "SELECT id,limit_usd FROM app.budgets WHERE workspace_id=:w", {"w": A[1]})
        conn.execute(
            text(
                "UPDATE app.budgets SET limit_usd=100,record_version=record_version+1 WHERE workspace_id=:w"
            ),
            {"w": A[1]},
        )
        company = rows(conn, "SELECT id,limit_usd FROM app.company_runtime_caps")
        conn.execute(text("UPDATE app.company_runtime_caps SET limit_usd=1000"))
    worker = make_engine(db_env["WORKER_DATABASE_URL"], pool_size=15)
    claimed = []
    try:
        for _ in range(50):
            execution = {
                "payload": body["payload"],
                "targets": body["targets"],
                "logical_key": uuid4().hex,
            }
            result = post(
                client, offline_mfa, "/approvals/" + identifier + "/execute", execution
            ).json()["data"]
            with transaction(runtime, *A) as conn:
                commands.dispatch_outbox(conn, 500)
                job = rows(
                    conn, "SELECT * FROM app.jobs WHERE input_ref=:id", {"id": result["input_id"]}
                )[0]
            claimed.append(claim_exact(worker, job))
        barrier = Barrier(50)

        def contender(job):
            barrier.wait(timeout=30)
            with transaction(worker, *WA) as conn:
                start = perf_counter()
                try:
                    with conn.begin_nested():
                        effect = commands.prepare_effect(conn, job)
                    return effect["id"], perf_counter() - start
                except BusinessError as exc:
                    assert exc.code == "AUTHORITY_LIMIT"
                    return None, perf_counter() - start

        start = perf_counter()
        with ThreadPoolExecutor(max_workers=50) as pool:
            results = list(pool.map(contender, claimed))
        assert sum(identifier is not None for identifier, _ in results) == 10
        print(
            f"authority contention: 50 simultaneous attempts, 15-connection pool, 10 accepted, total {perf_counter() - start:.3f}s, max {max(t for _, t in results):.3f}s"
        )
        with transaction(worker, *WA) as conn:
            assert (
                len(
                    rows(
                        conn,
                        "SELECT id FROM app.approval_uses WHERE manifest_id=:m",
                        {"m": details["manifest"]["id"]},
                    )
                )
                == 10
            )
            for job in claimed:
                commands.finish(conn, job, "cancelled")
    finally:
        worker.dispose()
        with admin.begin() as conn:
            for cap in old:
                conn.execute(
                    text(
                        "UPDATE app.budgets SET limit_usd=:limit_usd,record_version=record_version+1 WHERE id=:id"
                    ),
                    cap,
                )
            for cap in company:
                conn.execute(
                    text("UPDATE app.company_runtime_caps SET limit_usd=:limit_usd WHERE id=:id"),
                    cap,
                )


def test_worker_cannot_grant_and_populated_tenant_isolation(client, offline_mfa, runtime, engine):
    identifier, _ = granted(client, offline_mfa)
    assert (
        post(
            client,
            offline_mfa,
            "/authority/freeze",
            {
                "action": "runtime.synthetic_calculation",
                "rationale": "Protective fixture for populated isolation",
            },
        ).status_code
        == 200
    )
    with transaction(engine, *WA) as conn:
        assert rows(
            conn, "SELECT id FROM app.approval_manifests WHERE request_id=:id", {"id": identifier}
        )
        for table in (
            "approval_decisions",
            "approval_manifests",
            "policy_versions",
            "approval_requests",
            "authority_bindings",
        ):
            assert not conn.execute(
                text("SELECT has_table_privilege(current_user,:table,'INSERT')"),
                {"table": "app." + table},
            ).scalar_one()
    # Every populated authority table is tested with both actual restricted roles;
    # no missing-context read can recover any row.
    for engine_value in (runtime, engine):
        principal_a = key("worker") if engine_value is engine else A[0]
        with transaction(engine_value, principal_a, A[1], 1) as conn:
            for table in TABLES:
                assert rows(conn, f"SELECT id FROM app.{table} LIMIT 1"), table
        with transaction(engine_value) as conn:
            for table in TABLES:
                assert rows(conn, f"SELECT id FROM app.{table}") == []
        principal = key("worker") if engine_value is engine else key("user-b")
        with transaction(engine_value, principal, key("workspace-b"), 1) as conn:
            for table in TABLES:
                assert not rows(
                    conn, f"SELECT id FROM app.{table} WHERE workspace_id=:w", {"w": A[1]}
                )
