"""Bounded independent-review regressions using actual restricted PostgreSQL roles."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from queue import Queue
from time import monotonic, sleep
from uuid import uuid4

import pytest
from company_os.application import authority
from company_os.application import runtime as commands
from company_os.domain.scoring import canonical_hash
from company_os.persistence.authority import get, update
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows, transaction
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.seeds.synthetic import key
from tests.integration.test_authority import PREFIX, granted, post, proposal
from tests.integration.test_authority_controls import queue_claim
from tests.integration.test_identity_review import offline_mfa as signed_mfa_fixture
from tests.integration.test_runtime import WA, A
from tests.integration.test_runtime import engine as worker_engine_fixture

offline_mfa = signed_mfa_fixture
engine = worker_engine_fixture


def detail(client, headers, identifier):
    response = client.get(PREFIX + "/approvals/" + identifier, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def policy_proposal(
    client,
    headers,
    *,
    action="runtime.synthetic_external_action",
    seconds=3600,
    policy_seconds=86400,
    rules=None,
):
    policy = next(
        p
        for p in client.get(PREFIX + "/policies", headers=headers).json()["data"]
        if p["action"] == action
    )
    now = datetime.now(UTC)
    body = {
        "rules": rules or policy["rules"],
        "rationale": "Synthetic exact policy correction review",
        "effective_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(seconds=policy_seconds)).isoformat(),
        "approval_expires_at": (now + timedelta(seconds=seconds)).isoformat(),
    }
    result = post(client, headers, "/policies/propose", body, policy["record_version"])
    assert result.status_code == 200, result.text
    assert result.json()["data"]["result"] == "REQUIRE_APPROVAL", result.text
    return detail(client, headers, result.json()["data"]["request_id"])


def approve_policy(client, headers, proposed=None, **kwargs):
    proposed = proposed or policy_proposal(client, headers, **kwargs)
    request = proposed["request"]
    result = post(
        client,
        headers,
        f"/approvals/{request['id']}/decide",
        {
            "decision": "approve",
            "expected_scope_hash": request["scope_hash"],
            "rationale": "Reviewed exact candidate rules and pointer",
        },
        request["record_version"],
    )
    assert result.status_code == 200, result.text
    return detail(client, headers, request["id"])


def activation_body(approved):
    return {
        "policy_version_id": approved["request"]["candidate_version_id"],
        "decision_id": approved["manifest"]["decision_id"],
        "manifest_id": approved["manifest"]["id"],
    }


def activate_policy(client, headers, approved):
    return post(
        client,
        headers,
        "/policies/activate",
        activation_body(approved),
        approved["request"]["expected_policy_record_version"],
    )


def test_exact_activation_mfa_alone_denied_and_chain_once(client, offline_mfa, runtime):
    proposed = policy_proposal(client, offline_mfa)
    candidate = proposed["request"]["candidate_version_id"]
    identity = client.app.state.identity.resolve(offline_mfa["Authorization"].split()[1])
    # Fresh, real MFA plus a candidate does not authorize a pointer mutation.
    with transaction(runtime, *A) as conn:
        assert conn.execute(
            text("SELECT app.authority_founder(:s,true)"), {"s": identity.session_id}
        ).scalar_one()
        policy = get(conn, "policies", proposed["request"]["policy_id"])
        with pytest.raises(DBAPIError), conn.begin_nested():
            update(conn, "policies", policy, active_version_id=candidate)
    absent = {
        "policy_version_id": candidate,
        "decision_id": str(uuid4()),
        "manifest_id": str(uuid4()),
    }
    assert (
        post(
            client, offline_mfa, "/policies/activate", absent, policy["record_version"]
        ).status_code
        == 404
    )
    assert (
        post(
            client,
            offline_mfa,
            "/policies/activate",
            {
                "rules": proposed["request"]["payload"]["rules"],
                "rationale": "Old privileged shortcut",
            },
            policy["record_version"],
        ).status_code
        == 422
    )
    approved = approve_policy(client, offline_mfa, proposed)
    assert approved["manifest"]["scope"]["policy_change"] == proposed["request"]["payload"]
    assert canonical_hash(approved["manifest"]["scope"]) == approved["manifest"]["manifest_hash"]
    headers = {
        **offline_mfa,
        "Idempotency-Key": uuid4().hex,
        "If-Match": str(policy["record_version"]),
    }
    body = activation_body(approved)
    wrong = {**body, "policy_version_id": str(policy["active_version_id"])}
    assert (
        post(client, offline_mfa, "/policies/activate", wrong, policy["record_version"]).status_code
        == 423
    )
    response = client.post(PREFIX + "/policies/activate", json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["active_version_id"] == candidate
    assert (
        client.post(PREFIX + "/policies/activate", json=body, headers=headers).json()
        == response.json()
    )
    assert activate_policy(client, offline_mfa, approved).status_code == 423
    after = detail(client, offline_mfa, proposed["request"]["id"])
    assert len(after["uses"]) == 1 and after["uses"][0]["state"] == "consumed"
    assert after["remaining_uses"] == 0
    with transaction(runtime, *A) as conn:
        decisions = rows(
            conn,
            "SELECT * FROM app.policy_decisions WHERE correlation_id=:c",
            {"c": proposed["request"]["correlation_id"]},
        )
        assert len(decisions) == 1 and decisions[0]["result"] == "REQUIRE_APPROVAL"
        assert decisions[0]["payload_hash"] == proposed["request"]["payload_hash"]
        events = rows(
            conn,
            "SELECT * FROM app.events WHERE aggregate_id=:id ORDER BY created_at",
            {"id": proposed["request"]["id"]},
        )
        assert [e["event_type"] for e in events] == [
            "approval.requested",
            "approval.granted",
            "policy.activated",
        ]
        for event in events:
            assert rows(
                conn, "SELECT id FROM app.audit_entries WHERE event_id=:id", {"id": event["id"]}
            )


@pytest.mark.parametrize("field", ["rules", "content_hash"])
def test_candidate_drift_is_immutable(client, offline_mfa, runtime, field):
    approved = approve_policy(client, offline_mfa)
    with transaction(runtime, *A) as conn:
        before = get(conn, "policy_versions", approved["request"]["candidate_version_id"])
        expression = (
            "jsonb_set(rules,'{maximum_uses}','99')" if field == "rules" else "repeat('a',64)"
        )
        with pytest.raises(DBAPIError), conn.begin_nested():
            conn.execute(
                text(f"UPDATE app.policy_versions SET {field}={expression} WHERE id=:id"),
                {"id": before["id"]},
            )
        assert get(conn, "policy_versions", before["id"]) == before
    assert activate_policy(client, offline_mfa, approved).status_code == 200


@pytest.mark.parametrize(
    "pointer,reason", [(False, "POLICY_RECORD_CHANGED"), (True, "ACTIVE_VERSION_CHANGED")]
)
def test_policy_drift_blocks_stale_grant(client, offline_mfa, runtime, pointer, reason):
    approved = approve_policy(client, offline_mfa)
    identity = client.app.state.identity.resolve(offline_mfa["Authorization"].split()[1])
    from company_os.application.policy_activation import activate
    from company_os.policy_contracts import PolicyActivate

    with transaction(runtime, *A) as conn:
        save = conn.begin_nested()
        p = get(conn, "policies", approved["request"]["policy_id"])
        update(conn, "policies", p, active_version_id=None if pointer else p["active_version_id"])
        assert authority.validate(conn, approved["manifest"]["id"]) == reason
        with pytest.raises(BusinessError, match=reason):
            activate(
                conn,
                PolicyActivate(**activation_body(approved)),
                p["record_version"] + 1,
                identity,
                uuid4(),
            )
        assert not rows(
            conn,
            "SELECT id FROM app.approval_uses WHERE manifest_id=:id",
            {"id": approved["manifest"]["id"]},
        )
        save.rollback()


@pytest.mark.parametrize("revoked", [False, True])
def test_expired_or_revoked_activation_blocks(client, offline_mfa, runtime, revoked):
    approved = approve_policy(client, offline_mfa, seconds=3600 if revoked else 4)
    if revoked:
        assert (
            post(
                client,
                offline_mfa,
                f"/approvals/{approved['request']['id']}/revoke",
                {"rationale": "Withdraw this activation authority"},
                2,
            ).status_code
            == 200
        )
    else:
        with transaction(runtime, *A) as conn:
            conn.execute(
                text("SELECT pg_sleep_until(CAST(:t AS timestamptz))"),
                {"t": approved["manifest"]["expires_at"]},
            )
    response = activate_policy(client, offline_mfa, approved)
    assert response.status_code == 423, response.text
    assert response.json()["error"]["code"] == ("AUTHORITY_REVOKED" if revoked else "EXPIRED")
    assert detail(client, offline_mfa, approved["request"]["id"])["uses"] == []


@pytest.fixture
def business_humans(admin, runtime, settings):
    # Two additional invited humans in the SAME workspace, with real server roles.
    with admin.begin() as conn:
        actor = key("user-a")
        role = key("review-researcher")
        conn.execute(
            text(
                "INSERT INTO app.roles(id,name,created_by,updated_by) VALUES(:id,'researcher',:a,:a) ON CONFLICT DO NOTHING"
            ),
            {"id": role, "a": actor},
        )
        for permission in ("workspace.read", "business.read", "business.write"):
            conn.execute(
                text(
                    "INSERT INTO app.role_permissions(id,role_id,permission,created_by,updated_by) VALUES(:id,:role,:p,:a,:a) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": key("review-researcher-" + permission),
                    "role": role,
                    "p": permission,
                    "a": actor,
                },
            )
        for name in ("review-one", "review-two"):
            p = key("user-" + name)
            conn.execute(
                text(
                    "INSERT INTO app.principals(id,kind,status,created_by,updated_by) VALUES(:id,'user','active',:a,:a) ON CONFLICT DO NOTHING"
                ),
                {"id": p, "a": actor},
            )
            conn.execute(
                text(
                    "INSERT INTO app.users(id,principal_id,auth_subject,display_name,created_by,updated_by) VALUES(:id,:id,:subject,'Synthetic review human',:a,:a) ON CONFLICT DO NOTHING"
                ),
                {"id": p, "a": actor, "subject": "synthetic-user-" + name},
            )
            conn.execute(
                text(
                    "INSERT INTO app.memberships(id,workspace_id,principal_id,role_id,status,created_by,updated_by) VALUES(:id,:w,:p,:r,'active',:a,:a) ON CONFLICT DO NOTHING"
                ),
                {"id": key("review-member-" + name), "w": A[1], "p": p, "r": role, "a": actor},
            )
    # Use the same offline asymmetric verifier as the MFA fixtures; keep the
    # development adapter's two-subject allowlist unchanged.
    from types import SimpleNamespace

    import jwt
    from company_os.adapters.auth import JWTIdentityProvider
    from company_os.application.identity import IdentityService
    from cryptography.hazmat.primitives.asymmetric import ec

    provider = JWTIdentityProvider(
        settings.model_copy(
            update={"auth_mode": "supabase", "supabase_url": "https://offline-identity.example"}
        )
    )
    private = ec.generate_private_key(ec.SECP256R1())
    provider.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    headers = []
    for name in ("review-one", "review-two"):
        now = int(datetime.now(UTC).timestamp())
        token = jwt.encode(
            {
                "sub": "synthetic-user-" + name,
                "iss": "https://offline-identity.example/auth/v1",
                "aud": "authenticated",
                "iat": now,
                "exp": now + 900,
            },
            private,
            algorithm="ES256",
        )
        csrf = uuid4().hex
        session = IdentityService(runtime, provider).start(token, csrf)
        headers.append(
            {
                "Authorization": "Bearer " + session,
                "Origin": settings.console_origin,
                "X-CSRF-Token": csrf,
            }
        )
    yield headers
    with admin.begin() as conn:
        conn.execute(
            text("DELETE FROM app.memberships WHERE principal_id=:p AND role_id=:r"),
            {"p": A[0], "r": role},
        )
        for name in ("review-one", "review-two"):
            conn.execute(
                text("DELETE FROM app.memberships WHERE id=:id"),
                {"id": key("review-member-" + name)},
            )


def test_read_visibility_and_complete_server_roles(
    client, offline_mfa, business_humans, admin, monkeypatch
):
    one, two = business_humans
    original = authority.evaluate
    captured = []

    def capture(facts, rules):
        captured.append(facts.roles)
        return original(facts, rules)

    monkeypatch.setattr(authority, "evaluate", capture)
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app.memberships(id,workspace_id,principal_id,role_id,status,created_by,updated_by) VALUES(:id,:w,:p,:r,'active',:p,:p)"
            ),
            {"id": uuid4(), "w": A[1], "p": A[0], "r": key("review-researcher")},
        )
    founder_id, _ = granted(client, offline_mfa)
    assert captured[-1] == frozenset({"founder", "researcher"})
    # Authorize researchers through the real reviewed policy path.
    rules = next(
        p["rules"]
        for p in client.get(PREFIX + "/policies", headers=offline_mfa).json()["data"]
        if p["action"] == proposal()["action"]
    )
    approved = approve_policy(
        client, offline_mfa, rules={**rules, "permitted_roles": ["founder", "researcher"]}
    )
    assert activate_policy(client, offline_mfa, approved).status_code == 200
    own = post(client, one, "/approvals/request", proposal()).json()["data"]["request_id"]
    assert captured[-1] == frozenset({"researcher"})
    assert detail(client, one, own)["request"]["created_by"] == str(key("user-review-one"))
    own_ids = {a["id"] for a in client.get(PREFIX + "/approvals", headers=one).json()["data"]}
    assert own in own_ids and founder_id not in own_ids
    all_ids = {
        a["id"] for a in client.get(PREFIX + "/approvals", headers=offline_mfa).json()["data"]
    }
    assert {own, founder_id} <= all_ids
    assert client.get(PREFIX + "/approvals", headers=two).json()["data"] == []
    for headers, identifier in ((one, founder_id), (two, own), (two, founder_id)):
        assert client.get(PREFIX + "/approvals/" + identifier, headers=headers).status_code == 404
    assert (
        client.get(f"/v1/workspaces/{key('workspace-b')}/approvals/{own}", headers=one).status_code
        == 404
    )


@pytest.fixture
def administrator_in_a(admin, login):
    membership = uuid4()
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app.memberships(id,workspace_id,principal_id,role_id,status,created_by,updated_by) VALUES(:id,:w,:p,:r,'active',:a,:a)"
            ),
            {
                "id": membership,
                "w": A[1],
                "p": key("user-b"),
                "r": key("system_administrator"),
                "a": A[0],
            },
        )
    yield login("b")
    with admin.begin() as conn:
        conn.execute(text("DELETE FROM app.memberships WHERE id=:id"), {"id": membership})


def test_service_and_system_admin_cannot_activate_or_review(
    client, offline_mfa, administrator_in_a, admin, engine
):
    approved = approve_policy(client, offline_mfa)
    administrator = administrator_in_a
    assert activate_policy(client, administrator, approved).status_code == 403
    assert client.get(PREFIX + "/approvals", headers=administrator).status_code == 403
    assert (
        client.get(
            PREFIX + "/approvals/" + approved["request"]["id"], headers=administrator
        ).status_code
        == 403
    )
    # A service session cannot enter the human profile boundary, even if it has
    # a session token and workspace membership. Fixture creates no human subtype.
    from company_os.application.identity import digest

    token, csrf = uuid4().hex, uuid4().hex
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app.auth_sessions(id,principal_id,token_hash,csrf_hash,assurance,mfa_at,expires_at) VALUES(:id,:p,:t,:c,'aal2',clock_timestamp(),clock_timestamp()+interval '5 minutes')"
            ),
            {"id": uuid4(), "p": key("worker"), "t": digest(token), "c": digest(csrf)},
        )
    service = {**offline_mfa, "Authorization": "Bearer " + token, "X-CSRF-Token": csrf}
    assert activate_policy(client, service, approved).status_code == 401
    assert client.get(PREFIX + "/approvals", headers=service).status_code == 401
    assert (
        client.get(PREFIX + "/approvals/" + approved["request"]["id"], headers=service).status_code
        == 401
    )
    with transaction(engine, *WA) as conn:
        assert authority.validate(conn, approved["manifest"]["id"]) == "EXECUTOR_ROLE_DENIED"
        with pytest.raises(DBAPIError), conn.begin_nested():
            p = get(conn, "policies", approved["request"]["policy_id"])
            update(
                conn, "policies", p, active_version_id=approved["request"]["candidate_version_id"]
            )


def wait_for_block(admin, pid, blocker):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        with admin.connect() as conn:
            if conn.execute(
                text("SELECT :blocker=ANY(pg_blocking_pids(:pid))"),
                {"pid": pid, "blocker": blocker},
            ).scalar_one():
                return
        sleep(0.01)
    raise AssertionError("Validator did not reach the held PostgreSQL row lock")


@pytest.mark.parametrize("policy_expiry", [False, True])
def test_validation_blocked_on_target_must_recheck_final_clock(
    client, offline_mfa, runtime, engine, admin, policy_expiry
):
    if policy_expiry:
        short = approve_policy(client, offline_mfa, policy_seconds=8)
        assert activate_policy(client, offline_mfa, short).status_code == 200
        expires = short["request"]["payload"]["candidate_expires_at"]
    body = proposal()
    if not policy_expiry:
        body["expires_at"] = (datetime.now(UTC) + timedelta(seconds=8)).isoformat()
        expires = body["expires_at"]
    identifier, body = granted(client, offline_mfa, body)
    approved = detail(client, offline_mfa, identifier)
    claim = queue_claim(client, offline_mfa, runtime, engine, identifier, body)
    pid_queue = Queue()

    def validate_and_reserve():
        with transaction(engine, *WA) as conn:
            pid_queue.put(conn.execute(text("SELECT pg_backend_pid()")).scalar_one())
            code = authority.validate(conn, approved["manifest"]["id"])
            with pytest.raises(
                BusinessError, match="POLICY_CHANGED" if policy_expiry else "EXPIRED"
            ):
                commands.prepare_effect(conn, claim)
            assert not rows(
                conn,
                "SELECT id FROM app.approval_uses WHERE manifest_id=:m",
                {"m": approved["manifest"]["id"]},
            )
            assert not rows(
                conn,
                "SELECT f.id FROM app.fake_receipts f JOIN app.external_effects e ON e.id=f.effect_id WHERE e.job_id=:id",
                {"id": claim["id"]},
            )
            commands.finish(conn, claim, "cancelled")
            return code

    try:
        with admin.connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            held = blocker.begin()
            blocker_pid = blocker.execute(text("SELECT pg_backend_pid()")).scalar_one()
            blocker.execute(
                text("SELECT id FROM app.authority_test_targets WHERE id=:id FOR UPDATE"),
                {"id": key("a-authority-target-1")},
            )
            future = pool.submit(validate_and_reserve)
            try:
                wait_for_block(admin, pid_queue.get(timeout=5), blocker_pid)
                assert blocker.execute(
                    text("SELECT clock_timestamp()<CAST(:t AS timestamptz)"), {"t": expires}
                ).scalar_one(), "Must prove the early check passed before expiry"
                blocker.execute(
                    text("SELECT pg_sleep_until(CAST(:t AS timestamptz))"), {"t": expires}
                )
            finally:
                held.rollback()
            assert future.result(timeout=10) == ("POLICY_CHANGED" if policy_expiry else "EXPIRED")
    finally:
        if policy_expiry:
            restore = approve_policy(client, offline_mfa)
            assert activate_policy(client, offline_mfa, restore).status_code == 200


def test_receipt_final_boundary_has_no_expiry_grace(client, offline_mfa, runtime, engine):
    from company_os.adapters import fake_effects

    body = proposal()
    body["expires_at"] = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    identifier, body = granted(client, offline_mfa, body)
    approved = detail(client, offline_mfa, identifier)
    claim = queue_claim(client, offline_mfa, runtime, engine, identifier, body)
    with transaction(engine, *WA) as conn:
        effect = commands.prepare_effect(conn, claim)
        effect = commands.begin_dispatch(conn, claim, effect["id"])
        assert authority.validate(conn, approved["manifest"]["id"]) is None
        conn.execute(
            text("SELECT pg_sleep_until(CAST(:t AS timestamptz))"), {"t": body["expires_at"]}
        )
        with pytest.raises(BusinessError, match="EXPIRED"):
            authority.final_temporal_check(conn, approved["manifest"]["id"])
        with pytest.raises(DBAPIError, match="EXPIRED"), conn.begin_nested():
            fake_effects.accept(conn, effect, "effect_success")
        assert not rows(
            conn, "SELECT id FROM app.fake_receipts WHERE effect_id=:id", {"id": effect["id"]}
        )
        commands.finish(conn, claim, "cancelled")


def test_use_reservation_final_clock_after_accounting(client, offline_mfa, runtime, engine, admin):
    body = proposal()
    body["expires_at"] = (datetime.now(UTC) + timedelta(seconds=8)).isoformat()
    identifier, body = granted(client, offline_mfa, body)
    approved = detail(client, offline_mfa, identifier)
    claim = queue_claim(client, offline_mfa, runtime, engine, identifier, body)
    barrier_key = int(uuid4().hex[:12], 16)
    # Test-only barrier runs after bounded_use has completed its full validation
    # and accounting, but before the production final clock trigger. It lives
    # only in this disposable database and is removed even on assertion failure.
    with admin.begin() as conn:
        conn.execute(
            text(
                f"CREATE FUNCTION app.review_use_barrier() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_advisory_xact_lock({barrier_key}); RETURN NEW; END $$"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER zzz_review_barrier BEFORE INSERT ON app.approval_uses FOR EACH ROW EXECUTE FUNCTION app.review_use_barrier()"
            )
        )
    pid_queue = Queue()

    def reserve():
        with transaction(engine, *WA) as conn:
            pid_queue.put(conn.execute(text("SELECT pg_backend_pid()")).scalar_one())
            with pytest.raises(DBAPIError, match="EXPIRED"), conn.begin_nested():
                commands.prepare_effect(conn, claim)
            assert not rows(
                conn,
                "SELECT id FROM app.approval_uses WHERE manifest_id=:id",
                {"id": approved["manifest"]["id"]},
            )
            assert not rows(
                conn, "SELECT id FROM app.external_effects WHERE job_id=:id", {"id": claim["id"]}
            )
            commands.finish(conn, claim, "cancelled")

    try:
        with admin.connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            held = blocker.begin()
            blocker_pid = blocker.execute(text("SELECT pg_backend_pid()")).scalar_one()
            blocker.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": barrier_key})
            future = pool.submit(reserve)
            try:
                wait_for_block(admin, pid_queue.get(timeout=5), blocker_pid)
                assert blocker.execute(
                    text("SELECT clock_timestamp()<CAST(:t AS timestamptz)"),
                    {"t": body["expires_at"]},
                ).scalar_one()
                blocker.execute(
                    text("SELECT pg_sleep_until(CAST(:t AS timestamptz))"),
                    {"t": body["expires_at"]},
                )
            finally:
                held.rollback()
            future.result(timeout=10)
    finally:
        with admin.begin() as conn:
            conn.execute(text("DROP TRIGGER zzz_review_barrier ON app.approval_uses"))
            conn.execute(text("DROP FUNCTION app.review_use_barrier()"))


def test_disabled_policy_requires_exact_replacement_grant(client, offline_mfa, runtime):
    proposed = policy_proposal(client, offline_mfa)
    rules = proposed["request"]["payload"]["rules"]
    with transaction(runtime, *A) as conn:
        p = get(conn, "policies", proposed["request"]["policy_id"])
        update(conn, "policies", p, active_version_id=None)
    replacement = approve_policy(client, offline_mfa, rules=rules)
    assert replacement["manifest"]["scope"]["policy_change"]["current_active_version_id"] is None
    assert (
        canonical_hash(replacement["manifest"]["scope"]) == replacement["manifest"]["manifest_hash"]
    )
    assert activate_policy(client, offline_mfa, replacement).status_code == 200


def test_worker_checks_time_after_budget_before_adapter(
    client, offline_mfa, runtime, engine, monkeypatch
):
    from company_os.adapters import fake_effects
    from company_os.workflow.runtime import execute_claim

    body = proposal()
    body["expires_at"] = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    identifier, body = granted(client, offline_mfa, body)
    approved = detail(client, offline_mfa, identifier)
    claim = queue_claim(client, offline_mfa, runtime, engine, identifier, body)
    original = authority.validate_budget
    reached = []

    def slow_budget(conn, effect):
        original(conn, effect)
        if effect["state"] != "dispatching":
            return
        # The real full validation and budget check have succeeded. Advance to
        # the exact DB expiry before returning to the final application boundary.
        reached.append(True)
        conn.execute(
            text("SELECT pg_sleep_until(CAST(:t AS timestamptz))"), {"t": body["expires_at"]}
        )

    def forbidden_accept(*args):
        pytest.fail("Adapter must not be called after temporal authority expires")

    monkeypatch.setattr(authority, "validate_budget", slow_budget)
    monkeypatch.setattr(fake_effects, "accept", forbidden_accept)
    assert execute_claim(engine, WA, "review-expiry", claim, None)
    assert reached == [True]
    with transaction(engine, *WA) as conn:
        assert not rows(
            conn,
            "SELECT f.id FROM app.fake_receipts f JOIN app.external_effects e ON e.id=f.effect_id WHERE e.job_id=:id",
            {"id": claim["id"]},
        )
        assert authority.validate(conn, approved["manifest"]["id"]) == "EXPIRED"
