"""Adversarial commitment, budget, canonical scope and safety regressions."""

import json
from time import perf_counter
from uuid import uuid4

import pytest
from company_os.application import authority
from company_os.application import runtime as commands
from company_os.domain.scoring import canonical_hash
from company_os.persistence.authority import insert as authority_insert
from company_os.persistence.authority import update as authority_update
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows, transaction
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.seeds.synthetic import key
from tests.integration.test_authority import PREFIX, granted, post, proposal
from tests.integration.test_identity_review import offline_mfa as signed_mfa_fixture
from tests.integration.test_runtime import WA, A, claim_exact
from tests.integration.test_runtime import engine as worker_engine_fixture

offline_mfa = signed_mfa_fixture
engine = worker_engine_fixture


def queue_claim(client, headers, runtime, worker, identifier, body):
    execution = {"payload": body["payload"], "targets": body["targets"], "logical_key": uuid4().hex}
    response = post(client, headers, "/approvals/" + identifier + "/execute", execution)
    assert response.status_code == 200, response.text
    with transaction(runtime, *A) as conn:
        commands.dispatch_outbox(conn, 500)
        job = rows(
            conn,
            "SELECT * FROM app.jobs WHERE input_ref=:id",
            {"id": response.json()["data"]["input_id"]},
        )[0]
    return claim_exact(worker, job)


def test_budget_and_approval_are_separate(client, offline_mfa, runtime, engine):
    identifier, body = granted(client, offline_mfa)
    claim = queue_claim(client, offline_mfa, runtime, engine, identifier, body)
    with transaction(engine, *WA) as conn:
        save = conn.begin_nested()
        conn.execute(
            text(
                "UPDATE app.budgets SET status='frozen',record_version=record_version+1,updated_by=app.current_principal_id() WHERE category='synthetic'"
            )
        )
        with pytest.raises(BusinessError, match="BUDGET_EXHAUSTED"):
            commands.prepare_effect(conn, claim)
        assert not rows(
            conn, "SELECT id FROM app.approval_uses WHERE job_id=:id", {"id": claim["id"]}
        )
        save.rollback()
        commands.finish(conn, claim, "cancelled")


def test_revocation_at_dispatch_and_uncertain_reconciliation(client, offline_mfa, runtime, engine):
    from company_os.adapters import fake_effects
    from company_os.persistence.runtime import get as runtime_get

    identifier, body = granted(client, offline_mfa)
    claim = queue_claim(client, offline_mfa, runtime, engine, identifier, body)
    with transaction(engine, *WA) as conn:
        effect = commands.prepare_effect(conn, claim)
    assert (
        post(
            client,
            offline_mfa,
            "/approvals/" + identifier + "/revoke",
            {"rationale": "Revoked immediately before dispatch"},
            2,
        ).status_code
        == 200
    )
    with transaction(engine, *WA) as conn:
        with pytest.raises(BusinessError, match="AUTHORITY_REVOKED"):
            commands.begin_dispatch(conn, claim, effect["id"])
        commands.finish(conn, claim, "cancelled")
    identifier, body = granted(client, offline_mfa)
    claim = queue_claim(client, offline_mfa, runtime, engine, identifier, body)
    with transaction(engine, *WA) as conn:
        effect = commands.prepare_effect(conn, claim)
        effect = commands.begin_dispatch(conn, claim, effect["id"])
    with transaction(engine, *WA) as conn:
        receipt = fake_effects.accept(conn, effect, "effect_success")
    with transaction(engine, *WA) as conn:
        effect = commands.uncertain(conn, effect)
    assert (
        post(
            client,
            offline_mfa,
            "/approvals/" + identifier + "/revoke",
            {"rationale": "Revoked after uncertain dispatch"},
            2,
        ).status_code
        == 200
    )
    with transaction(engine, *WA) as conn:
        assert runtime_get(conn, "external_effects", effect["id"])["state"] == "uncertain"
        uses = rows(
            conn, "SELECT id FROM app.approval_uses WHERE effect_id=:id", {"id": effect["id"]}
        )
        assert len(uses) == 1
        assert not rows(
            conn, "SELECT id FROM app.approval_use_results WHERE use_id=:id", {"id": uses[0]["id"]}
        )
        resolved = commands.resolve_effect(conn, effect, receipt)
        assert resolved["state"] == "confirmed"
        assert (
            len(
                rows(
                    conn,
                    "SELECT id FROM app.fake_receipts WHERE effect_id=:id",
                    {"id": effect["id"]},
                )
            )
            == 1
        )
        commands.finish(conn, claim, "succeeded")


def test_freeze_policy_change_and_hash_constraints(client, offline_mfa, runtime):
    identifier, _ = granted(client, offline_mfa)
    details = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    manifest = details["manifest"]["id"]
    with transaction(runtime, *A) as conn:
        save = conn.begin_nested()
        authority_insert(
            conn,
            "authority_freezes",
            {"action": None, "rationale": "Emergency protective test", "correlation_id": uuid4()},
        )
        assert authority.validate(conn, manifest) == "EMERGENCY_FREEZE"
        save.rollback()
        save = conn.begin_nested()
        policy = rows(
            conn,
            "SELECT * FROM app.policies WHERE active_version_id=:id",
            {"id": details["request"]["policy_version_id"]},
        )[0]
        authority_update(conn, "policies", policy, active_version_id=None)
        assert authority.validate(conn, manifest) == "POLICY_CHANGED"
        save.rollback()
        with pytest.raises(DBAPIError), conn.begin_nested():
            authority_insert(
                conn,
                "approval_targets",
                {
                    "request_id": identifier,
                    "target_id": key("a-authority-target-2"),
                    "expected_version": 1,
                },
            )
        with pytest.raises(DBAPIError), conn.begin_nested():
            conn.execute(
                text("UPDATE app.policy_versions SET content_hash=repeat('a',64) WHERE id=:id"),
                {"id": details["request"]["policy_version_id"]},
            )


def test_database_canonical_unicode_and_batch(client, offline_mfa, runtime):
    body = proposal()
    body["action"] = "runtime.synthetic_batch_action"
    body["payload"]["label"] = "Synthetic café approval"
    with transaction(runtime, *A) as conn:
        body["targets"] = [
            {
                "id": str(
                    authority_insert(
                        conn, "authority_test_targets", {"label": f"Synthetic scale target {i}"}
                    )["id"]
                ),
                "version": 1,
            }
            for i in range(200)
        ]
    body["maximum_volume"] = 200
    identifier, _ = granted(client, offline_mfa, body)
    details = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    scope = details["manifest"]["scope"]
    with transaction(runtime, *A) as conn:
        actual = conn.execute(
            text(
                "SELECT encode(sha256(convert_to(app.authority_canonical(CAST(:s AS jsonb)),'UTF8')),'hex')"
            ),
            {"s": json.dumps(scope)},
        ).scalar_one()
        assert actual == canonical_hash(scope) == details["manifest"]["manifest_hash"]
        start = perf_counter()
        for _ in range(100):
            assert authority.validate(conn, details["manifest"]["id"]) is None
        print(
            f"200-target validation: 100 calls, {(perf_counter() - start) * 10:.3f} ms mean (warm transaction)"
        )


def test_admin_forged_identity_and_denial_audit(client, login, offline_mfa, runtime):
    headers = login("b")
    result = client.post(
        f"/v1/workspaces/{key('workspace-b')}/approvals/request",
        headers={**headers, "Idempotency-Key": uuid4().hex},
        json=proposal(),
    )
    assert result.status_code == 403
    identifier = post(client, offline_mfa, "/approvals/request", proposal()).json()["data"][
        "request_id"
    ]
    detail = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    body = {
        "decision": "approve",
        "rationale": "Synthetic decision reason",
        "expected_scope_hash": detail["request"]["scope_hash"],
    }
    assert (
        post(
            client,
            offline_mfa,
            "/approvals/" + identifier + "/decide",
            {**body, "approver_id": str(key("user-a"))},
            1,
        ).status_code
        == 422
    )
    denied = post(client, login(), "/approvals/" + identifier + "/decide", body, 1)
    assert denied.status_code == 403
    with transaction(runtime, *A) as conn:
        assert rows(
            conn,
            "SELECT id FROM app.audit_entries WHERE action_type='authority.denied' AND request_id=:r",
            {"r": denied.headers["x-request-id"]},
        )


def test_l0_l1_do_not_create_material_grants(client, offline_mfa):
    for action in ("runtime.synthetic_calculation", "runtime.synthetic_internal_action"):
        response = post(client, offline_mfa, "/approvals/request", {**proposal(), "action": action})
        assert response.status_code == 200
        assert response.json()["data"]["result"] == "ALLOW"
        assert "request_id" not in response.json()["data"]


def test_budget_rechecked_by_sql_at_dispatch(client, offline_mfa, runtime, engine):
    from company_os.persistence.runtime import clock, update

    identifier, body = granted(client, offline_mfa)
    claim = queue_claim(client, offline_mfa, runtime, engine, identifier, body)
    with transaction(engine, *WA) as conn:
        effect = commands.prepare_effect(conn, claim)
        save = conn.begin_nested()
        conn.execute(
            text(
                "UPDATE app.budgets SET status='frozen',record_version=record_version+1,updated_by=app.current_principal_id() WHERE category='synthetic'"
            )
        )
        with pytest.raises(BusinessError, match="CURRENT_BUDGET_BLOCKED"):
            commands.begin_dispatch(conn, claim, effect["id"])
        with (
            pytest.raises(DBAPIError, match="Current dispatch budget blocked"),
            conn.begin_nested(),
        ):
            update(
                conn,
                "external_effects",
                effect,
                state="dispatching",
                dispatch_started_at=clock(conn),
                lease_fence=claim["fence"],
                reconcile_after=clock(conn),
            )
        save.rollback()
        commands.finish(conn, claim, "cancelled")


@pytest.mark.parametrize("bound", ["spend", "volume"])
def test_independent_authority_ceilings(client, offline_mfa, runtime, engine, bound):
    body = {
        **proposal(),
        "maximum_uses": 2,
        "maximum_spend": "1" if bound == "spend" else "2",
        "maximum_volume": 1 if bound == "volume" else 2,
    }
    identifier, body = granted(client, offline_mfa, body)
    claims = [queue_claim(client, offline_mfa, runtime, engine, identifier, body) for _ in range(2)]
    with transaction(engine, *WA) as conn:
        commands.prepare_effect(conn, claims[0])
    with transaction(engine, *WA) as conn:
        with pytest.raises(BusinessError, match="AUTHORITY_LIMIT"), conn.begin_nested():
            commands.prepare_effect(conn, claims[1])
        for claim in claims:
            commands.finish(conn, claim, "cancelled")


def test_policy_activation_invalidates_prior_grant(client, offline_mfa):
    from tests.integration.test_phase5_review import activate_policy, approve_policy

    identifier, _ = granted(client, offline_mfa)
    policies = client.get(PREFIX + "/policies", headers=offline_mfa).json()["data"]
    policy = next(p for p in policies if p["action"] == "runtime.synthetic_external_action")
    approved = approve_policy(client, offline_mfa)
    response = activate_policy(client, offline_mfa, approved)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["active_version_id"] != policy["active_version_id"]
    details = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    assert details["validation_reason"] == "POLICY_CHANGED"
