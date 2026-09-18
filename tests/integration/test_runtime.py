"""Phase 4 adverse-path acceptance on real PostgreSQL runtime roles."""

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from company_os.application import runtime as commands
from company_os.application.scheduler import next_daily, tick
from company_os.application.webhooks import authenticate, receive
from company_os.persistence.business import BusinessError
from company_os.persistence.database import make_engine, rows, transaction
from company_os.persistence.runtime import TABLES, clock, get, insert, update
from company_os.runtime_contracts import SyntheticInput
from company_os.workflow.runtime import run_one
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.seeds.synthetic import key

A = (key("user-a"), key("workspace-a"), 1)
B = (key("user-b"), key("workspace-b"), 1)
WA = (key("worker"), key("workspace-a"), 1)


@pytest.fixture
def engine(db_env):
    value = make_engine(db_env["WORKER_DATABASE_URL"], pool_size=15)
    yield value
    value.dispose()


def new_job(runtime, scenario="success", scope=A, priority="normal"):
    with transaction(runtime, *scope) as conn:
        item = commands.submit(
            conn, SyntheticInput(scenario=scenario, logical_key="test-" + uuid4().hex), uuid4()
        )
        commands.dispatch_outbox(conn)
        job = rows(conn, "SELECT * FROM app.jobs WHERE input_ref=:id", {"id": item["id"]})[0]
        if priority != "normal":
            job = update(conn, "jobs", job, priority=priority)
    return job


def claim_exact(engine, job):
    # Isolate the target with a dedicated priority and temporary availability for
    # other fixtures; correctness assertions remain on the real claim boundary.
    with transaction(engine, *WA) as conn:
        target = get(conn, "jobs", job["id"], lock=True)
        update(
            conn,
            "jobs",
            target,
            priority="interactive",
            available_at=clock(conn) - timedelta(days=1),
        )
        claim = commands.claim(conn, "worker-" + uuid4().hex)
        assert claim["id"] == job["id"]
        return claim


def test_atomic_event_outbox_receipt_and_duplicate(runtime):
    request = SyntheticInput(scenario="success", logical_key="atomic-" + uuid4().hex)
    with pytest.raises(RuntimeError), transaction(runtime, *A) as conn:
        commands.submit(conn, request, uuid4())
        raise RuntimeError("Crash before commit")
    with transaction(runtime, *A) as conn:
        assert not rows(
            conn,
            "SELECT id FROM app.runtime_inputs WHERE logical_key=:key",
            {"key": request.logical_key},
        )
        item = commands.submit(conn, request, uuid4())
        assert commands.submit(conn, request, uuid4())["id"] == item["id"]
        event = rows(conn, "SELECT * FROM app.events WHERE aggregate_id=:id", {"id": item["id"]})[0]
        commands.consume(conn, event)
        commands.consume(conn, event)
        assert (
            len(rows(conn, "SELECT id FROM app.jobs WHERE input_ref=:id", {"id": item["id"]})) == 1
        )
        assert (
            len(
                rows(
                    conn,
                    "SELECT id FROM app.consumer_receipts WHERE event_id=:id",
                    {"id": event["id"]},
                )
            )
            == 1
        )
        assert (
            len(rows(conn, "SELECT id FROM app.outbox WHERE event_id=:id", {"id": event["id"]}))
            == 1
        )


def test_fence_rejects_expiry_and_replacement(runtime, engine, admin):
    job = new_job(runtime)
    claimed = claim_exact(engine, job)
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE app.jobs SET lease_expires_at=now()-interval '1 second',record_version=record_version+1 WHERE id=:id"
            ),
            {"id": job["id"]},
        )
    with pytest.raises(BusinessError, match="STALE_FENCE"), transaction(engine, *WA) as conn:
        commands.finish(conn, claimed, "succeeded")
    with transaction(engine, *WA) as conn:
        commands.recover(conn)
        current = get(conn, "jobs", job["id"])
        update(conn, "jobs", current, available_at=clock(conn) - timedelta(seconds=1))
    replacement = claim_exact(engine, job)
    assert replacement["fence"] > claimed["fence"]
    with pytest.raises(BusinessError, match="STALE_FENCE"), transaction(engine, *WA) as conn:
        commands.finish(conn, claimed, "succeeded")
    with transaction(engine, *WA) as conn:
        commands.finish(conn, replacement, "succeeded")
        assert (
            len(rows(conn, "SELECT id FROM app.job_attempts WHERE job_id=:id", {"id": job["id"]}))
            == 4
        )


def test_retry_history_wait_and_cancel(runtime, engine):
    job = new_job(runtime, "transient")
    claimed = claim_exact(engine, job)
    with transaction(engine, *WA) as conn:
        waiting = commands.failed(conn, claimed, "TRANSIENT", transient=True)
        assert waiting["state"] == "retry_wait" and waiting["lease_owner"] is None
        update(conn, "jobs", waiting, available_at=clock(conn) - timedelta(seconds=1))
    claimed = claim_exact(engine, job)
    with transaction(engine, *WA) as conn:
        commands.finish(conn, claimed, "waiting_approval")
        waiting = get(conn, "jobs", job["id"])
        assert waiting["lease_owner"] is None
    with transaction(runtime, *A) as conn:
        cancelled = commands.cancel(
            conn, job["id"], waiting["record_version"], "Synthetic cancellation"
        )
        assert cancelled["state"] == "cancelled"
        assert (
            len(rows(conn, "SELECT id FROM app.job_attempts WHERE job_id=:id", {"id": job["id"]}))
            == 4
        )


def test_dependency_cycle_and_blocked_claim(runtime, engine):
    first = new_job(runtime)
    second = new_job(runtime)
    with transaction(runtime, *A) as conn:
        insert(
            conn,
            "job_dependencies",
            {"job_id": second["id"], "depends_on_job_id": first["id"], "condition": "succeeded"},
        )
    with pytest.raises(DBAPIError), transaction(runtime, *A) as conn:
        insert(
            conn,
            "job_dependencies",
            {"job_id": first["id"], "depends_on_job_id": second["id"], "condition": "succeeded"},
        )
    claimed = claim_exact(engine, first)
    with transaction(engine, *WA) as conn:
        commands.finish(conn, claimed, "succeeded")
    claimed = claim_exact(engine, second)
    with transaction(engine, *WA) as conn:
        commands.finish(conn, claimed, "succeeded")


def test_fifty_reservations_ten_cap(runtime, engine):
    job = new_job(runtime)
    with transaction(runtime, *A) as conn:
        now = clock(conn)
        budget = insert(
            conn,
            "budgets",
            {
                "period_start": now,
                "period_end": now + timedelta(days=1),
                "category": "concurrency-" + uuid4().hex,
                "limit_usd": Decimal(10),
                "status": "active",
            },
        )

    def reserve(index):
        try:
            with transaction(engine, *WA) as conn:
                commands.reserve(
                    conn, budget["id"], job, "parallel-" + str(budget["id"]) + ":" + str(index)
                )
            return True
        except BusinessError as error:
            assert error.code == "BUDGET_EXHAUSTED"
            return False

    with ThreadPoolExecutor(max_workers=50) as pool:
        assert sum(pool.map(reserve, range(50))) == 10
    with transaction(engine, *WA) as conn:
        value = get(conn, "budgets", budget["id"])
        assert value["reserved_usd"] == 10 and value["spent_usd"] == 0
        reservations = rows(
            conn, "SELECT * FROM app.budget_reservations WHERE budget_id=:id", {"id": budget["id"]}
        )
        for reservation in reservations:
            commands.settle(conn, reservation["id"], Decimal(0))
            commands.settle(conn, reservation["id"], Decimal(0))
        assert get(conn, "budgets", budget["id"])["reserved_usd"] == 0


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("effect_success", "confirmed"),
        ("effect_rejected", "rejected"),
        ("effect_lost", "uncertain"),
    ],
)
def test_effect_intent_and_uncertainty(runtime, engine, admin, scenario, expected):
    job = new_job(runtime, scenario)
    with transaction(runtime, *A) as conn:
        update(conn, "jobs", job, priority="interactive")
    assert run_one(engine, WA, "effect-worker")
    with transaction(engine, *WA) as conn:
        current = get(conn, "jobs", job["id"])
        effect = get(conn, "external_effects", current["effect_id"])
        assert effect["state"] == expected
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
        reservation = get(conn, "budget_reservations", effect["reservation_id"])
        assert reservation["state"] == (
            "uncertain"
            if expected == "uncertain"
            else "released"
            if expected == "rejected"
            else "settled"
        )
    if expected == "uncertain":
        # Receipt visibility is fake remote configuration, never an uncertainty reset.
        with admin.begin() as conn:
            conn.execute(text("ALTER TABLE app.fake_receipts DISABLE TRIGGER runtime_guard"))
            conn.execute(
                text(
                    "UPDATE app.fake_receipts SET visible_after=now()-interval '1 second' WHERE effect_id=:id"
                ),
                {"id": effect["id"]},
            )
            conn.execute(text("ALTER TABLE app.fake_receipts ENABLE TRIGGER runtime_guard"))
        assert run_one(engine, WA, "reconciler", safety=True)
        with transaction(engine, *WA) as conn:
            assert get(conn, "external_effects", effect["id"])["state"] == "confirmed"
            assert get(conn, "jobs", job["id"])["state"] == "succeeded"
            assert get(conn, "workflow_runs", job["workflow_run_id"])["state"] == "succeeded"
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


def test_replay_namespace_cannot_dispatch(runtime, engine):
    job = new_job(runtime, "effect_success")
    with transaction(runtime, *A) as conn:
        job = update(conn, "jobs", job, replay_namespace="projection-test", priority="interactive")
    claimed = claim_exact(engine, job)
    with (
        pytest.raises(BusinessError, match="REPLAY_EFFECT_DISABLED"),
        transaction(engine, *WA) as conn,
    ):
        commands.prepare_effect(conn, claimed)
    with transaction(engine, *WA) as conn:
        commands.finish(conn, claimed, "dead_letter", code="REPLAY_EFFECT_DISABLED")


def test_webhook_auth_dedupe_spoof_order_and_quarantine(runtime):
    secret = "synthetic-only-" + uuid4().hex
    job = new_job(runtime, "wait")
    payload = {
        "event_key": uuid4().hex,
        "schema_version": 1,
        "external_id": str(job["input_ref"]),
        "version": 5,
        "observation": "stopped",
        "occurred_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
        "workspace_id": str(key("workspace-b")),
    }
    body = json.dumps(payload).encode()
    stamp = str(int(datetime.now(UTC).timestamp()))
    signature = hmac.new(secret.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    authenticate(secret, body, stamp, signature, datetime.now(UTC))
    with pytest.raises(BusinessError, match="AUTH_FAILED"):
        authenticate(secret, body, stamp, "bad", datetime.now(UTC))
    with pytest.raises(BusinessError, match="STALE_DELIVERY"):
        authenticate(secret, body, stamp, signature, datetime.now(UTC) + timedelta(minutes=6))
    with transaction(runtime, *A) as conn:
        receipt = receive(conn, key("fake-endpoint-a"), body, secret)
        assert receipt["state"] == "applied" and receipt["workspace_id"] == key("workspace-a")
        assert receive(conn, key("fake-endpoint-a"), body, secret)["id"] == receipt["id"]
        payload.update(event_key=uuid4().hex, version=1, observation="active")
        assert (
            receive(conn, key("fake-endpoint-a"), json.dumps(payload).encode(), secret)["state"]
            == "ignored"
        )
        payload.update(event_key=uuid4().hex, external_id=str(uuid4()))
        assert (
            receive(conn, key("fake-endpoint-a"), json.dumps(payload).encode(), secret)["state"]
            == "quarantined"
        )
        payload.update(event_key=uuid4().hex, schema_version=99)
        assert (
            receive(conn, key("fake-endpoint-a"), json.dumps(payload).encode(), secret)[
                "error_code"
            ]
            == "UNKNOWN_SCHEMA"
        )


def test_schedule_slots_and_timezone(runtime):
    # New York spring gap skips nonexistent 02:30; fall fold emits one local slot.
    assert next_daily(
        datetime(2026, 3, 8, 5, tzinfo=UTC), "America/New_York", "daily:02:30"
    ) == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)
    assert next_daily(
        datetime(2026, 11, 1, 4, tzinfo=UTC), "America/New_York", "daily:01:30"
    ) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    with transaction(runtime, *A) as conn:
        now = clock(conn)
        item = insert(
            conn,
            "runtime_inputs",
            {"scenario": "success", "logical_key": uuid4().hex, "content_hash": "0" * 64},
        )
        for policy in ("skip", "one_catchup"):
            schedule = insert(
                conn,
                "schedules",
                {
                    "name": uuid4().hex,
                    "timezone": "America/New_York",
                    "rule": "daily:08:00",
                    "next_due_at": now - timedelta(days=7),
                    "enabled": True,
                    "missed_policy": policy,
                    "input_ref": item["id"],
                },
            )
            tick(conn)
            tick(conn)
            assert len(
                rows(
                    conn,
                    "SELECT id FROM app.schedule_slots WHERE schedule_id=:id",
                    {"id": schedule["id"]},
                )
            ) == int(policy == "one_catchup")


def test_all_runtime_tables_scope_and_cross_tenant(runtime, engine):
    other = new_job(runtime, scope=B)
    for scope in (A, WA, (None, None, None)):
        with transaction(engine if scope == WA else runtime, *scope) as conn:
            for table in TABLES:
                assert not rows(
                    conn,
                    f"SELECT id FROM app.{table} WHERE workspace_id=:w",
                    {"w": key("workspace-b")},
                )
    with pytest.raises(BusinessError, match="NOT_FOUND"), transaction(engine, *WA) as conn:
        get(conn, "jobs", other["id"])
    job = new_job(runtime)
    with pytest.raises(DBAPIError), transaction(runtime, *A) as conn:
        insert(
            conn,
            "job_dependencies",
            {"job_id": job["id"], "depends_on_job_id": other["id"], "condition": "terminal"},
        )


def test_api_scope_and_explicit_command(client, login):
    headers = {**login(), "Idempotency-Key": uuid4().hex}
    w = key("workspace-a")
    result = client.post(
        f"/v1/workspaces/{w}/runtime/synthetic",
        headers=headers,
        json={"scenario": "success", "logical_key": uuid4().hex},
    )
    assert result.status_code == 200, result.text
    response = client.get(f"/v1/workspaces/{w}/jobs", headers=headers)
    assert response.status_code == 200, response.text
    assert (
        client.get(f"/v1/workspaces/{key('workspace-b')}/jobs", headers=headers).status_code == 404
    )
    assert (
        client.post(
            f"/v1/workspaces/{w}/runtime/synthetic",
            headers={"Authorization": headers["Authorization"], "Idempotency-Key": uuid4().hex},
            json={"scenario": "success", "logical_key": uuid4().hex},
        ).status_code
        == 403
    )


def test_completion_receipt_fence_and_no_lease(runtime, engine):
    job = new_job(runtime, "wait")
    claimed = claim_exact(engine, job)
    with transaction(engine, *WA) as conn:
        commands.finish(conn, claimed, "waiting_external")
    with pytest.raises(BusinessError, match="BAD_FENCE"), transaction(engine, *WA) as conn:
        commands.complete_callback(conn, job["id"], claimed["fence"] + 1, job["input_ref"])
    with transaction(engine, *WA) as conn:
        receipt = commands.complete_callback(conn, job["id"], claimed["fence"], job["input_ref"])
        assert (
            commands.complete_callback(conn, job["id"], claimed["fence"], job["input_ref"])["id"]
            == receipt["id"]
        )
        assert get(conn, "jobs", job["id"])["lease_owner"] is None
    assert run_one(engine, WA, "callback-resumed")
    with transaction(engine, *WA) as conn:
        assert get(conn, "jobs", job["id"])["state"] == "succeeded"


def test_health_and_critical_snooze(client, login, runtime, engine):
    job = new_job(runtime, "invalid")
    claimed = claim_exact(engine, job)
    with transaction(engine, *WA) as conn:
        commands.failed(conn, claimed, "INVALID_INPUT")
        incident = rows(
            conn,
            "SELECT * FROM app.incidents WHERE fingerprint=:k",
            {"k": "dead_letter:" + str(job["id"])},
        )[0]
        attention = rows(
            conn,
            "SELECT * FROM app.runtime_attention WHERE incident_id=:id",
            {"id": incident["id"]},
        )[0]
    headers = {
        **login(),
        "Idempotency-Key": uuid4().hex,
        "If-Match": str(attention["record_version"]),
    }
    response = client.get(f"/v1/workspaces/{key('workspace-a')}/runtime-health", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "RED"
    response = client.post(
        f"/v1/workspaces/{key('workspace-a')}/attention/{attention['id']}/snooze",
        headers=headers,
        json={
            "until": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "reason": "Cannot hide critical incident",
        },
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "CRITICAL_ITEM_CANNOT_HIDE"
    )


def test_signed_callback_api(client, settings, runtime):
    job = new_job(runtime, "wait")
    payload = {
        "event_key": uuid4().hex,
        "schema_version": 1,
        "external_id": str(job["input_ref"]),
        "version": 1,
        "observation": "active",
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    body = json.dumps(payload).encode()
    stamp = str(int(datetime.now(UTC).timestamp()))
    secret = settings.fake_webhook_secret.get_secret_value()
    signature = hmac.new(secret.encode(), stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    headers = {
        "X-Fake-Timestamp": stamp,
        "X-Fake-Signature": signature,
        "Content-Type": "application/json",
    }
    path = f"/webhooks/fake/{key('fake-endpoint-a')}"
    response = client.post(path, headers=headers, content=body)
    assert response.status_code == 202, response.text
    assert client.post(path, headers=headers, content=body).json() == response.json()
    assert (
        client.post(
            path, headers={**headers, "X-Fake-Signature": "invalid"}, content=body
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "point",
    [
        "after_claim",
        "during_internal",
        "after_commit",
        "before_call",
        "during_call",
        "after_remote_success",
    ],
)
def test_process_crash_durable_recovery(runtime, engine, admin, worker_env, point):
    import subprocess
    import sys

    scenario = (
        "effect_success"
        if point in {"before_call", "during_call", "after_remote_success"}
        else "success"
    )
    job = new_job(runtime, scenario)
    with transaction(runtime, *A) as conn:
        update(conn, "jobs", job, priority="interactive")
    code = (
        "from company_os.persistence.database import make_engine; from company_os.workflow.runtime import run_one; from database.seeds.synthetic import key; import os; e=make_engine(os.environ['WORKER_DATABASE_URL']); run_one(e,(key('worker'),key('workspace-a'),1),'crash-child',crash_at="
        + repr(point)
        + ")"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], env=worker_env, capture_output=True, text=True, timeout=20
    )
    assert result.returncode != 0 and "Synthetic crash" in result.stderr, result.stderr
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE app.jobs SET lease_expires_at=now()-interval '1 second',record_version=record_version+1 WHERE id=:id AND lease_owner IS NOT NULL"
            ),
            {"id": job["id"]},
        )
    with transaction(engine, *WA) as conn:
        commands.recover(conn)
        current = get(conn, "jobs", job["id"])
        if point == "after_commit":
            assert current["state"] == "succeeded"
        elif scenario == "effect_success":
            assert current["state"] == "waiting_external"
            effect = get(conn, "external_effects", current["effect_id"])
            assert effect["state"] == "uncertain"
            assert (
                get(conn, "budget_reservations", effect["reservation_id"])["state"] == "uncertain"
            )
        else:
            assert current["state"] == "retry_wait"
        # Leave restart fixtures isolated from subsequent ready-work ordering.
        if current["state"] == "retry_wait":
            update(conn, "jobs", current, available_at=clock(conn) + timedelta(hours=1))


def test_populated_tenant_tables_and_role_boundaries(runtime, engine):
    from company_os.persistence.runtime import IMMUTABLE
    from company_os.workflow.runtime import maintenance

    wb = (key("worker"), key("workspace-b"), 1)
    jobs = []
    for scenario in ("success", "wait", "invalid", "effect_success"):
        job = new_job(runtime, scenario, scope=B, priority="interactive")
        jobs.append(job)
        assert run_one(engine, wb, "tenant-b")
    wait = jobs[1]
    with transaction(engine, *wb) as conn:
        wait = get(conn, "jobs", wait["id"])
        commands.complete_callback(conn, wait["id"], wait["fence"], wait["input_ref"])
        insert(
            conn,
            "job_dependencies",
            {"job_id": wait["id"], "depends_on_job_id": jobs[0]["id"], "condition": "succeeded"},
        )
        secret = "synthetic-only-" + uuid4().hex
        receive(
            conn,
            key("fake-endpoint-b"),
            json.dumps(
                {
                    "event_key": uuid4().hex,
                    "schema_version": 1,
                    "external_id": str(wait["input_ref"]),
                    "version": 1,
                    "observation": "active",
                    "occurred_at": datetime.now(UTC).isoformat(),
                }
            ).encode(),
            secret,
        )
        schedule = rows(conn, "SELECT * FROM app.schedules LIMIT 1")[0]
        update(conn, "schedules", schedule, next_due_at=clock(conn) - timedelta(seconds=1))
    maintenance(engine, wb, "isolation-fixture")
    with transaction(engine, *wb) as conn:
        examples = {table: rows(conn, f"SELECT * FROM app.{table} LIMIT 1") for table in TABLES}
        assert all(examples.values()), [table for table, items in examples.items() if not items]
    for engine_role, scope in ((runtime, A), (engine, WA)):
        for table, example in examples.items():
            with transaction(engine_role, *scope) as conn:
                assert (
                    rows(conn, f"SELECT * FROM app.{table} WHERE id=:id", {"id": example[0]["id"]})
                    == []
                )
            if table not in IMMUTABLE:
                with transaction(engine_role, *scope) as conn:
                    changed = conn.execute(
                        text(
                            f"UPDATE app.{table} SET record_version=record_version+1 WHERE id=:id"
                        ),
                        {"id": example[0]["id"]},
                    )
                    assert changed.rowcount == 0
        with transaction(engine_role) as conn:
            for table in TABLES:
                assert rows(conn, f"SELECT * FROM app.{table}") == []
        with pytest.raises(DBAPIError), transaction(engine_role, *scope) as conn:
            conn.execute(text("SELECT * FROM app.company_runtime_caps"))


def test_ready_queue_load_and_reserved_safety_capacity(runtime, engine, admin):
    import time
    from concurrent.futures import ThreadPoolExecutor

    blocked = new_job(runtime, "effect_success", priority="interactive")
    with transaction(runtime, *A) as conn:
        budgets = rows(
            conn,
            "SELECT * FROM app.budgets WHERE category IN ('synthetic','synthetic_day','synthetic_month')",
        )
        for budget in budgets:
            update(conn, "budgets", budget, status="frozen")
    assert run_one(engine, WA, "discretionary-blocked")
    with transaction(engine, *WA) as conn:
        current = get(conn, "jobs", blocked["id"])
        assert (
            current["state"] == "waiting_external"
            and current["last_error_code"] == "BUDGET_EXHAUSTED"
        )
        assert current["effect_id"] is None
    job = new_job(runtime, "success")
    safety = new_job(runtime, "safety", scope=B, priority="safety")
    with transaction(runtime, *A) as conn:
        # 10,000/day equivalent fixture: 100 ready now, remaining arrivals spread
        # over the rest of the day. This is not a 10,000-at-once arrival claim.
        conn.execute(
            text("""INSERT INTO app.jobs(id,workspace_id,created_by,updated_by,job_type,job_version,subject_id,input_ref,input_hash,state,priority,available_at,deadline_at,idempotency_key,correlation_id)
        SELECT gen_random_uuid(),app.current_workspace_id(),app.current_principal_id(),app.current_principal_id(),'synthetic',1,:input,:input,:hash,'queued','bulk',now()+make_interval(secs=>CASE WHEN n<=100 THEN 0 ELSE n*8.64 END),now()+interval '2 days',:prefix||n::text,:correlation FROM generate_series(1,10000) n"""),
            {
                "input": job["input_ref"],
                "hash": job["input_hash"],
                "prefix": "load-" + uuid4().hex + ":",
                "correlation": job["correlation_id"],
            },
        )
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run_one, engine, WA, "bulk-" + str(n)) for n in range(40)]
        # The safety claim uses its own slot and does not reserve discretionary cost.
        with transaction(engine, key("worker"), key("workspace-b"), 1) as conn:
            claimed = commands.claim(conn, "reserved-safety", safety=True)
            assert claimed is not None and claimed["id"] == safety["id"]
            commands.finish(conn, claimed, "succeeded")
        safety_delay = time.monotonic() - started
        assert safety_delay < 5
        for future in futures:
            future.result()
    elapsed = time.monotonic() - started
    assert elapsed < 60
    with transaction(runtime, *A) as conn:
        count = conn.execute(
            text("SELECT count(*) FROM app.jobs WHERE correlation_id=:id"),
            {"id": job["correlation_id"]},
        ).scalar_one()
        assert count == 10001
        for budget in budgets:
            update(conn, "budgets", get(conn, "budgets", budget["id"]), status=budget["status"])
    with transaction(runtime, *B) as conn:
        safety_current = get(conn, "jobs", safety["id"])

        assert safety_current["state"] == "succeeded"
    print(
        json.dumps(
            {
                "fixture": "10000-jobs-per-day-equivalent",
                "normal_executions": 40,
                "elapsed_seconds": elapsed,
                "safety_claim_seconds": safety_delay,
            }
        )
    )


def test_initial_data_and_api_load_envelope(admin, runtime, client, settings):
    """OPS-002/TEST-029 local synthetic envelope, not a production capacity claim."""
    import secrets
    import time

    from company_os.application.identity import digest

    workspaces = [key("workspace-a"), key("workspace-b")] + [
        key("load-workspace-" + str(n)) for n in range(3)
    ]
    with admin.begin() as conn:
        for n, w in enumerate(workspaces):
            if n >= 2:
                conn.execute(
                    text(
                        "INSERT INTO app.workspaces(id,name,kind,status,timezone,retention_profile,region_policy,created_by,updated_by) SELECT :id,:name,kind,status,timezone,retention_profile,region_policy,created_by,updated_by FROM app.workspaces WHERE id=:source"
                    ),
                    {
                        "id": w,
                        "name": "Synthetic Load Workspace " + str(n),
                        "source": key("workspace-a"),
                    },
                )
            source = uuid4()
            conn.execute(
                text(
                    "INSERT INTO app.data_sources(id,workspace_id,created_by,updated_by,name,source_type,rights_status,permitted_purposes,allowed_fields) VALUES(:id,:w,:p,:p,'Synthetic load only','human','pending','{}','{}')"
                ),
                {"id": source, "w": w, "p": key("user-a")},
            )
            for kind, table, count in [("account", "accounts", 10000), ("person", "people", 20000)]:
                fields = ",identity_discriminator" if kind == "account" else ""
                value = ",'synthetic-load'" if kind == "account" else ""
                conn.execute(
                    text(
                        f"WITH registered AS (INSERT INTO app.resources(id,workspace_id,created_by,updated_by,resource_type) SELECT gen_random_uuid(),:w,:p,:p,:kind FROM generate_series(1,:count) RETURNING id) INSERT INTO app.{table}(id,workspace_id,created_by,updated_by,display_name,status,source_id{fields}) SELECT id,:w,:p,:p,'Synthetic Load Fixture','active',:source{value} FROM registered"
                    ),
                    {"w": w, "p": key("user-a"), "kind": kind, "count": count, "source": source},
                )
        for n in range(10):
            principal = key("load-user-" + str(n))
            w = workspaces[2 + n % 3]
            params = {
                "id": principal,
                "p": key("user-a"),
                "subject": "synthetic-load-user-" + str(n),
                "w": w,
                "role": key("system_administrator"),
                "membership": uuid4(),
            }
            conn.execute(
                text(
                    "INSERT INTO app.principals(id,kind,status,created_by,updated_by) VALUES(:id,'user','active',:p,:p)"
                ),
                params,
            )
            conn.execute(
                text(
                    "INSERT INTO app.users(id,principal_id,auth_subject,display_name,created_by,updated_by) VALUES(:id,:id,:subject,'Synthetic Load Operator',:p,:p)"
                ),
                params,
            )
            conn.execute(
                text(
                    "INSERT INTO app.memberships(id,workspace_id,principal_id,role_id,status,created_by,updated_by) VALUES(:membership,:w,:id,:role,'active',:p,:p)"
                ),
                params,
            )
    headers = []
    for n in range(10):
        csrf = secrets.token_hex(32)
        # This benchmarks authenticated API work, not the identity provider.
        # Provision fixture sessions through the existing mapping boundary;
        # production development JWT verification keeps its two-user allowlist.
        session = secrets.token_urlsafe(48)
        with transaction(runtime) as conn:
            principal = conn.execute(
                text("SELECT app.open_session(:subject,:id,:hash,:csrf,'aal1',NULL)"),
                {
                    "subject": "synthetic-load-user-" + str(n),
                    "id": uuid4(),
                    "hash": digest(session),
                    "csrf": digest(csrf),
                },
            ).scalar_one()
            assert principal == key("load-user-" + str(n))
        headers.append(
            {
                "Authorization": "Bearer " + session,
                "Origin": settings.console_origin,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": uuid4().hex,
            }
        )

    def measure(n):
        prefix = "/v1/workspaces/" + str(workspaces[2 + n % 3])
        start = time.monotonic()
        result = client.get(prefix + "/runtime-health", headers=headers[n])
        read = time.monotonic() - start
        assert result.status_code == 200, result.text
        start = time.monotonic()
        result = client.post(
            prefix + "/runtime/synthetic",
            headers=headers[n],
            json={"scenario": "success", "logical_key": "api-load-" + uuid4().hex},
        )
        command = time.monotonic() - start
        assert result.status_code == 200, result.text
        return read, command

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(measure, range(10)))
    read_p95 = sorted(v[0] for v in results)[-1]
    command_p95 = sorted(v[1] for v in results)[-1]
    assert read_p95 < 0.75
    assert command_p95 < 1
    metrics = {
        "synthetic_workspaces": 5,
        "additional_accounts": 50000,
        "additional_people": 100000,
        "concurrent_users": 10,
        "read_api_p95_seconds": read_p95,
        "command_p95_seconds": command_p95,
    }
    from pathlib import Path

    Path(".local/phase4-load-results.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics))


def test_active_lease_renewal_and_prepared_non_use_release(runtime, engine):
    import time

    from company_os.workflow.runtime import renew_lease

    job = new_job(runtime, "effect_success", scope=B, priority="safety")
    wb = (key("worker"), key("workspace-b"), 1)
    with transaction(engine, *wb) as conn:
        claimed = commands.claim(conn, "lease-renewal-test", safety=True)
        assert claimed["id"] == job["id"]
        before = claimed["heartbeat_at"]
    with renew_lease(engine, wb, claimed, interval=0.02):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with transaction(engine, *wb) as conn:
                current = get(conn, "jobs", job["id"])
            if current["heartbeat_at"] > before:
                break
            time.sleep(0.02)
        assert current["heartbeat_at"] > before
        assert current["fence"] == claimed["fence"]
    with transaction(engine, *wb) as conn:
        effect = commands.prepare_effect(conn, claimed)
    with transaction(engine, *wb) as conn:
        commands.finish(conn, claimed, "dead_letter", code="DISPATCH_CANCELLED")
        assert get(conn, "external_effects", effect["id"])["state"] == "cancelled"
        assert get(conn, "budget_reservations", effect["reservation_id"])["state"] == "released"
        assert not rows(
            conn, "SELECT id FROM app.fake_receipts WHERE effect_id=:id", {"id": effect["id"]}
        )
        assert get(conn, "workflow_runs", job["workflow_run_id"])["state"] == "failed"
