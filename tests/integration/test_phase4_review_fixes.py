"""Independent Phase 4 review regressions on actual PostgreSQL runtime roles."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from company_os.adapters import fake_effects
from company_os.application import runtime as commands
from company_os.application.scheduler import next_daily, tick
from company_os.persistence.business import BusinessError
from company_os.persistence.database import make_engine, rows, transaction
from company_os.persistence.runtime import clock, get, insert, update
from company_os.reporting.runtime import health
from company_os.runtime_contracts import SyntheticInput
from company_os.workflow.runtime import execute_claim, maintenance
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from database.seeds.synthetic import key


@pytest.fixture
def review(admin, runtime, db_env):
    workspace, user_member, worker_member = uuid4(), uuid4(), uuid4()
    with admin.begin() as conn:
        conn.execute(
            text("""INSERT INTO app.workspaces(id,name,kind,status,timezone,retention_profile,region_policy,created_by,updated_by)
            SELECT :id,:name,kind,status,timezone,retention_profile,region_policy,created_by,updated_by FROM app.workspaces WHERE id=:source"""),
            {
                "id": workspace,
                "name": "Synthetic Review " + workspace.hex,
                "source": key("workspace-a"),
            },
        )
        for principal, membership, role in [
            (key("user-a"), user_member, key("founder")),
            (key("worker"), worker_member, key("system_administrator")),
        ]:
            conn.execute(
                text(
                    "INSERT INTO app.memberships(id,workspace_id,principal_id,role_id,status,created_by,updated_by) VALUES(:id,:w,:p,:r,'active',:a,:a)"
                ),
                {"id": membership, "w": workspace, "p": principal, "r": role, "a": key("user-a")},
            )
    scope = (key("worker"), workspace, 1)
    engine = make_engine(db_env["WORKER_DATABASE_URL"], pool_size=6)
    with transaction(engine, *scope) as conn:
        endpoint = insert(
            conn,
            "fake_endpoints",
            {"adapter": "fake_local_v1", "name": "Review only", "enabled": True},
        )
        now = clock(conn)
        for category in ("synthetic", "synthetic_day", "synthetic_month"):
            insert(
                conn,
                "budgets",
                {
                    "category": category,
                    "period_start": now - timedelta(days=1),
                    "period_end": now + timedelta(days=1),
                    "limit_usd": "10",
                    "status": "active",
                },
            )
        insert(
            conn,
            "quota_buckets",
            {
                "connection_id": endpoint["id"],
                "dimension": "requests",
                "window_start": now - timedelta(days=1),
                "window_end": now + timedelta(days=1),
                "limit_units": 10,
                "safety_reserve": 1,
            },
        )
    try:
        yield engine, scope
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE app.memberships SET status='revoked',record_version=record_version+1 WHERE id IN (:a,:b)"
                ),
                {"a": user_member, "b": worker_member},
            )


def job_for(engine, scope, scenario="effect_success", item=None):
    with transaction(engine, *scope) as conn:
        if item is None:
            item = commands.submit(
                conn,
                SyntheticInput(scenario=scenario, logical_key="review-" + uuid4().hex),
                uuid4(),
            )
        job = commands.enqueue(conn, item, uuid4().hex, uuid4())
        return item, job


def claim_job(engine, scope, job):
    with transaction(engine, *scope) as conn:
        job = update(conn, "jobs", get(conn, "jobs", job["id"]), priority="interactive")
        claimed = commands.claim(conn, "review-" + uuid4().hex)
        assert claimed["id"] == job["id"]
        return claimed


@pytest.mark.parametrize("contenders", [2, 5])
def test_review_effect_first_creation_race(review, contenders):
    engine, scope = review
    item, first = job_for(engine, scope)
    jobs = [claim_job(engine, scope, first)]
    for _ in range(contenders - 1):
        _, job = job_for(engine, scope, item=item)
        jobs.append(claim_job(engine, scope, job))
    start = Barrier(contenders)
    lock_checks = []

    def check_creation_lock(conn, cursor, statement, parameters, context, executemany):
        if "FROM app.external_effects WHERE connection_id=" in statement:
            # Inspect real PostgreSQL locks before the missing-row lookup. This
            # fails if creation relies only on a row lock or later budget lock.
            assert (
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory' AND granted"
                    )
                ).scalar_one()
                >= 1
            )
            lock_checks.append(conn.execute(text("SELECT pg_backend_pid()")).scalar_one())

    def prepare(job):
        with transaction(engine, *scope) as conn:
            pid = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
            assert not rows(conn, "SELECT id FROM app.external_effects")
            assert not rows(conn, "SELECT id FROM app.budget_reservations")
            start.wait(timeout=10)
            effect = commands.prepare_effect(conn, job)
            if effect["job_id"] != job["id"]:
                commands.finish(conn, job, "waiting_external", code="COALESCED_EFFECT")
            return pid, effect

    event.listen(engine, "before_cursor_execute", check_creation_lock)
    try:
        with ThreadPoolExecutor(max_workers=contenders) as pool:
            results = list(pool.map(prepare, jobs))
    finally:
        event.remove(engine, "before_cursor_execute", check_creation_lock)
    assert len({pid for pid, _ in results}) == contenders
    assert len(set(lock_checks)) == contenders
    assert len({effect["id"] for _, effect in results}) == 1
    effect = results[0][1]
    canonical = next(job for job in jobs if job["id"] == effect["job_id"])
    with transaction(engine, *scope) as conn:
        assert len(rows(conn, "SELECT id FROM app.external_effects")) == 1
        reservations = rows(conn, "SELECT * FROM app.budget_reservations")
        assert len(reservations) == 1 and reservations[0]["job_id"] == canonical["id"]
        assert reservations[0]["id"] == effect["reservation_id"]
        quota = get(conn, "quota_buckets", effect["quota_bucket_id"])
        assert quota["reserved_units"] == 1 and quota["consumed_units"] == 0
        assert not rows(conn, "SELECT id FROM app.fake_receipts")
        for job in jobs:
            current = get(conn, "jobs", job["id"])
            if job["id"] == canonical["id"]:
                assert current["effect_id"] == effect["id"]
                assert current["coalesced_effect_id"] is None
            else:
                assert current["state"] == "waiting_external"
                assert current["coalesced_effect_id"] == effect["id"]
                assert current["effect_id"] is None
                assert current["budget_reservation_id"] is None
    assert execute_claim(engine, scope, "canonical", canonical, None)
    with transaction(engine, *scope) as conn:
        commands.refresh_coalesced(conn)
        commands.refresh_coalesced(conn)
        assert all(get(conn, "jobs", job["id"])["state"] == "succeeded" for job in jobs)
        assert len(rows(conn, "SELECT id FROM app.fake_receipts")) == 1
        assert len(rows(conn, "SELECT id FROM app.usage_entries")) == 1
        assert get(conn, "budget_reservations", effect["reservation_id"])["state"] == "settled"
        quota = get(conn, "quota_buckets", effect["quota_bucket_id"])
        assert quota["reserved_units"] == 0 and quota["consumed_units"] == 1
        assert all(
            b["reserved_usd"] == 0 and b["spent_usd"] == 1
            for b in rows(conn, "SELECT * FROM app.budgets")
        )
        assert not rows(conn, "SELECT id FROM app.incidents WHERE kind='dead_letter'")
        dead = next(c for c in health(conn)["components"] if c["name"] == "dead_letters")
        assert dead["status"] == "GREEN" and dead["count"] == 0


@pytest.mark.parametrize("incompatible_index", [0, 1])
def test_review_effect_first_creation_hash_conflict(review, incompatible_index):
    engine, scope = review
    item, first = job_for(engine, scope)
    _, second = job_for(engine, scope, item=item)
    jobs = [claim_job(engine, scope, job) for job in (first, second)]
    # Immutable inputs are unique by logical key. An incompatible job request
    # therefore differs from that input's canonical hash; neither order may win.
    with transaction(engine, *scope) as conn:
        bad = get(conn, "jobs", jobs[incompatible_index]["id"])
        update(conn, "jobs", bad, input_hash="0" * 64)
    start = Barrier(2)

    def prepare(job):
        with transaction(engine, *scope) as conn:
            pid = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
            assert not rows(conn, "SELECT id FROM app.external_effects")
            start.wait(timeout=10)
            try:
                effect = commands.prepare_effect(conn, job)
            except BusinessError as error:
                assert error.code == "EFFECT_KEY_CONFLICT"
                return pid, error.code
            return pid, effect

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(prepare, jobs))
    assert results[0][0] != results[1][0]
    assert results[incompatible_index][1] == "EFFECT_KEY_CONFLICT"
    effect = results[1 - incompatible_index][1]
    canonical = jobs[1 - incompatible_index]
    with transaction(engine, *scope) as conn:
        assert effect["job_id"] == canonical["id"]
        assert len(rows(conn, "SELECT id FROM app.external_effects")) == 1
        assert len(rows(conn, "SELECT id FROM app.budget_reservations")) == 1
        bad = get(conn, "jobs", jobs[incompatible_index]["id"])
        assert bad["effect_id"] is None and bad["coalesced_effect_id"] is None
        assert bad["budget_reservation_id"] is None
        commands.finish(conn, bad, "cancelled", code="EFFECT_KEY_CONFLICT")
        assert get(conn, "external_effects", effect["id"]) == effect
        assert get(conn, "budget_reservations", effect["reservation_id"])["state"] == "reserved"
        assert get(conn, "quota_buckets", effect["quota_bucket_id"])["reserved_units"] == 1
    assert execute_claim(engine, scope, "canonical", canonical, None)
    with transaction(engine, *scope) as conn:
        assert get(conn, "external_effects", effect["id"])["state"] == "confirmed"
        assert len(rows(conn, "SELECT id FROM app.fake_receipts")) == 1
        assert len(rows(conn, "SELECT id FROM app.usage_entries")) == 1


@pytest.mark.parametrize(
    "scenario,terminal",
    [
        ("effect_success", "succeeded"),
        ("effect_rejected", "dead_letter"),
        ("effect_lost", "succeeded"),
    ],
)
def test_review_effect_concurrent_followers_never_own_reservations(
    review, runtime, client, login, admin, scenario, terminal
):
    engine, scope = review
    item, a = job_for(engine, scope, scenario)
    a = claim_job(engine, scope, a)
    with transaction(engine, *scope) as conn:
        effect = commands.prepare_effect(conn, a)
        before = get(conn, "budget_reservations", effect["reservation_id"])
        quota = get(conn, "quota_buckets", effect["quota_bucket_id"])
    followers = []
    for _ in range(3):
        _, b = job_for(engine, scope, item=item)
        followers.append(claim_job(engine, scope, b))
    barrier = Barrier(3)

    def coalesce(b):
        barrier.wait(timeout=5)
        with transaction(engine, *scope) as conn:
            found = commands.prepare_effect(conn, b)
            assert found["id"] == effect["id"] and found["job_id"] == a["id"]
            return commands.finish(conn, b, "waiting_external", code="COALESCED_EFFECT")

    with ThreadPoolExecutor(max_workers=3) as pool:
        followers = list(pool.map(coalesce, followers))
    with transaction(engine, *scope) as conn:
        for follower in followers:
            assert follower["effect_id"] is None and follower["budget_reservation_id"] is None
            assert follower["coalesced_effect_id"] == effect["id"]
        commands.cancel(
            conn, followers[0]["id"], followers[0]["record_version"], "Cancel only this follower"
        )
        assert get(conn, "external_effects", effect["id"]) == effect
        assert get(conn, "budget_reservations", effect["reservation_id"]) == before
        assert get(conn, "quota_buckets", effect["quota_bucket_id"]) == quota
    with pytest.raises(DBAPIError), transaction(runtime, *scope) as conn:
        update(
            conn,
            "external_effects",
            get(conn, "external_effects", effect["id"]),
            job_id=followers[1]["id"],
        )
    with pytest.raises(DBAPIError), transaction(engine, *scope) as conn:
        update(
            conn,
            "jobs",
            get(conn, "jobs", followers[1]["id"]),
            effect_id=effect["id"],
            coalesced_effect_id=None,
        )
    # Canonical worker can still dispatch after concurrent duplicate work and cancellation.
    assert execute_claim(engine, scope, "canonical", a, None)
    if scenario == "effect_lost":
        _, duplicate = job_for(engine, scope, item=item)
        duplicate = claim_job(engine, scope, duplicate)
        assert execute_claim(engine, scope, "late-duplicate", duplicate, None)
        followers.append(duplicate)
        with transaction(engine, *scope) as conn:
            assert get(conn, "external_effects", effect["id"])["state"] == "uncertain"
            assert (
                get(conn, "budget_reservations", effect["reservation_id"])["state"] == "uncertain"
            )
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
        with admin.begin() as conn:
            conn.execute(text("ALTER TABLE app.fake_receipts DISABLE TRIGGER runtime_guard"))
            conn.execute(
                text(
                    "UPDATE app.fake_receipts SET visible_after=now()-interval '1 second' WHERE effect_id=:id"
                ),
                {"id": effect["id"]},
            )
            conn.execute(text("ALTER TABLE app.fake_receipts ENABLE TRIGGER runtime_guard"))
        with transaction(engine, *scope) as conn:
            reconciliation = commands.claim(conn, "reconcile", safety=True)
        assert execute_claim(engine, scope, "reconcile", reconciliation, None)
    with transaction(engine, *scope) as conn:
        commands.refresh_coalesced(conn)
        commands.refresh_coalesced(conn)
        assert get(conn, "jobs", a["id"])["state"] == terminal
        assert get(conn, "jobs", followers[0]["id"])["state"] == "cancelled"
        for follower in followers[1:]:
            assert get(conn, "jobs", follower["id"])["state"] == terminal
        assert not rows(
            conn,
            "SELECT id FROM app.jobs WHERE coalesced_effect_id=:id AND state='waiting_external'",
            {"id": effect["id"]},
        )
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
        assert (
            len(
                rows(
                    conn,
                    "SELECT id FROM app.usage_entries WHERE reservation_id=:id",
                    {"id": effect["reservation_id"]},
                )
            )
            == 1
        )
        current_quota = get(conn, "quota_buckets", effect["quota_bucket_id"])
        assert current_quota["reserved_units"] == 0
        assert current_quota["consumed_units"] == (0 if terminal == "dead_letter" else 1)
        for budget in rows(conn, "SELECT * FROM app.budgets"):
            assert budget["reserved_usd"] == 0 and budget["spent_usd"] == (
                0 if terminal == "dead_letter" else 1
            )
    response = client.get(f"/v1/workspaces/{scope[1]}/jobs/{followers[1]['id']}", headers=login())
    assert response.status_code == 200, response.text
    assert response.json()["data"]["effect"]["job_id"] == str(a["id"])


def test_review_effect_dispatching_duplicate_reads_canonical_result(review):
    engine, scope = review
    item, a = job_for(engine, scope)
    a = claim_job(engine, scope, a)
    with transaction(engine, *scope) as conn:
        effect = commands.prepare_effect(conn, a)
        effect = commands.begin_dispatch(conn, a, effect["id"])
        reservation = get(conn, "budget_reservations", effect["reservation_id"])
    _, b = job_for(engine, scope, item=item)
    b = claim_job(engine, scope, b)
    assert execute_claim(engine, scope, "duplicate", b, None)
    with transaction(engine, *scope) as conn:
        assert get(conn, "external_effects", effect["id"]) == effect
        assert get(conn, "budget_reservations", effect["reservation_id"]) == reservation
        assert not rows(conn, "SELECT id FROM app.fake_receipts")
        b = get(conn, "jobs", b["id"])
        assert b["state"] == "waiting_external"
        # Legacy followers can retain an earlier wait code after the additive backfill.
        update(conn, "jobs", b, last_error_code="EFFECT_HELD")
    with transaction(engine, *scope) as conn:
        receipt = fake_effects.accept(conn, effect, "effect_success")
    with transaction(engine, *scope) as conn:
        commands.resolve_effect(conn, effect, receipt)
        commands.finish(conn, a, "succeeded")
        commands.refresh_coalesced(conn)
        assert get(conn, "jobs", b["id"])["state"] == "succeeded"
        assert len(rows(conn, "SELECT id FROM app.fake_receipts")) == 1
        assert len(rows(conn, "SELECT id FROM app.usage_entries")) == 1


def test_review_effect_hash_conflict_and_follower_failure(review):
    engine, scope = review
    item, a = job_for(engine, scope)
    a = claim_job(engine, scope, a)
    with transaction(engine, *scope) as conn:
        effect = commands.prepare_effect(conn, a)
    _, b = job_for(engine, scope, item=item)
    b = claim_job(engine, scope, b)
    with transaction(engine, *scope) as conn:
        update(conn, "jobs", get(conn, "jobs", b["id"]), input_hash="0" * 64)
    with (
        pytest.raises(BusinessError, match="EFFECT_KEY_CONFLICT"),
        transaction(engine, *scope) as conn,
    ):
        commands.prepare_effect(conn, b)
    with transaction(engine, *scope) as conn:
        update(conn, "jobs", get(conn, "jobs", b["id"]), input_hash=item["content_hash"])
        commands.prepare_effect(conn, b)
        commands.finish(conn, b, "dead_letter", code="TRANSIENT")
        assert get(conn, "external_effects", effect["id"]) == effect
        assert get(conn, "budget_reservations", effect["reservation_id"])["state"] == "reserved"
    assert execute_claim(engine, scope, "canonical", a, None)
    with transaction(engine, *scope) as conn:
        assert get(conn, "external_effects", effect["id"])["state"] == "confirmed"


@pytest.mark.parametrize("recovery_fails", [False, True])
def test_review_recovery_resolves_current_health_without_erasing_history(
    review, client, login, recovery_fails
):
    engine, scope = review
    _, a = job_for(engine, scope, "success")
    a = claim_job(engine, scope, a)
    with transaction(engine, *scope) as conn:
        a = commands.finish(conn, a, "dead_letter", code="LEASE_EXPIRED")
        attempts = rows(
            conn, "SELECT * FROM app.job_attempts WHERE job_id=:id ORDER BY id", {"id": a["id"]}
        )
        inc = rows(
            conn,
            "SELECT * FROM app.incidents WHERE fingerprint=:k",
            {"k": "dead_letter:" + str(a["id"])},
        )[0]
        assert inc["state"] == "open"
        assert (
            next(c for c in health(conn)["components"] if c["name"] == "dead_letters")["status"]
            == "RED"
        )
    headers = {**login(), "Idempotency-Key": uuid4().hex, "If-Match": str(a["record_version"])}
    url = f"/v1/workspaces/{scope[1]}/jobs/{a['id']}/retry"
    body = {
        "reason": "Worker process restored after synthetic lease failure",
        "cause_changed": True,
    }
    response = client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    recovery_id = response.json()["data"]["id"]
    assert client.post(url, headers=headers, json=body).json()["data"]["id"] == recovery_id
    with transaction(engine, *scope) as conn:
        b = get(conn, "jobs", recovery_id)
    b = claim_job(engine, scope, b)
    with transaction(engine, *scope) as conn:
        b = commands.finish(
            conn,
            b,
            "dead_letter" if recovery_fails else "succeeded",
            code="LEASE_EXPIRED" if recovery_fails else None,
        )
        commands.resolve_recovery(conn, b)
        commands.resolve_recovery(conn, b)
        assert get(conn, "jobs", a["id"]) == a
        assert (
            rows(
                conn, "SELECT * FROM app.job_attempts WHERE job_id=:id ORDER BY id", {"id": a["id"]}
            )
            == attempts
        )
        resolved = get(conn, "incidents", inc["id"])
        assert resolved["state"] == ("open" if recovery_fails else "resolved")
        assert resolved["opened_at"] == inc["opened_at"]
        attention = rows(
            conn, "SELECT * FROM app.runtime_attention WHERE incident_id=:id", {"id": inc["id"]}
        )[0]
        assert attention["state"] == ("open" if recovery_fails else "resolved")
        dead = next(c for c in health(conn)["components"] if c["name"] == "dead_letters")
        assert dead["status"] == ("RED" if recovery_fails else "GREEN")
        assert dead["count"] == (2 if recovery_fails else 0)
        events = rows(
            conn,
            "SELECT id FROM app.events WHERE aggregate_id=:id AND event_type='security.incident_resolved'",
            {"id": inc["id"]},
        )
        assert len(events) == (0 if recovery_fails else 1)


@pytest.mark.parametrize("role", ["api", "worker"])
@pytest.mark.parametrize("aggregate", ["runtime_input", "job", "effect", "budget", "incident"])
def test_review_event_versions_at_database_boundary(review, runtime, role, aggregate):
    engine, scope = review
    connection_engine = runtime if role == "api" else engine
    item, job = job_for(engine, scope)
    claimed = claim_job(engine, scope, job)
    with transaction(engine, *scope) as conn:
        effect = commands.prepare_effect(conn, claimed)
        inc = commands.incident(conn, "dead_letter", job)
        table = {
            "runtime_input": "runtime_inputs",
            "job": "jobs",
            "effect": "external_effects",
            "budget": "budgets",
            "incident": "incidents",
        }[aggregate]
        value = {
            "runtime_input": item,
            "job": get(conn, "jobs", job["id"]),
            "effect": effect,
            "budget": rows(conn, "SELECT * FROM app.budgets ORDER BY id")[0],
            "incident": inc,
        }[aggregate]
        if aggregate != "runtime_input":
            value = update(
                conn,
                table,
                value,
                **{
                    ("state" if aggregate in {"job", "effect", "incident"} else "status"): value[
                        "state" if aggregate in {"job", "effect", "incident"} else "status"
                    ]
                },
            )
        kind = {
            "runtime_input": "test.aggregate_changed",
            "job": "job.started",
            "effect": "effect.uncertain",
            "budget": "budget.warning",
            "incident": "security.incident_resolved",
        }[aggregate]
        version = value.get("record_version", 1)
        payload = commands.event_payload(aggregate, value)
    data = {
        "event_type": kind,
        "schema_version": 2,
        "aggregate_type": aggregate,
        "aggregate_id": value["id"],
        "aggregate_version": version,
        "actor_type": "service",
        "actor_id": scope[0],
        "correlation_id": uuid4(),
        "origin": "company_os",
        "classification": "internal",
        "payload": payload,
        "trace_id": uuid4().hex,
    }
    for bad in [version - 1, version + 1]:
        with pytest.raises(DBAPIError), transaction(connection_engine, *scope) as conn:
            insert(conn, "events", {**data, "aggregate_version": bad})
    with (
        pytest.raises(DBAPIError),
        transaction(connection_engine, key("worker"), key("workspace-b"), 1) as conn,
    ):
        insert(conn, "events", data)
    with transaction(connection_engine, *scope) as conn:
        event = insert(conn, "events", data)
        if aggregate != "runtime_input":
            value = get(conn, table, value["id"])
            field = "state" if aggregate in {"job", "effect", "incident"} else "status"
            value = update(conn, table, value, **{field: value[field]})
            commands.emit(conn, kind, value, aggregate)
        assert get(conn, "events", event["id"]) == event
    with pytest.raises(DBAPIError), transaction(connection_engine, *scope) as conn:
        conn.execute(
            text("UPDATE app.events SET aggregate_version=aggregate_version+1 WHERE id=:id"),
            {"id": event["id"]},
        )
    with transaction(engine, *scope) as conn:
        commands.cancel(
            conn,
            job["id"],
            get(conn, "jobs", job["id"])["record_version"],
            "Fixture cleanup before dispatch",
        )


@pytest.mark.parametrize(
    "zone,rule,valid",
    [
        ("Asia/Karachi", "daily:23:59", True),
        ("America/New_York", "daily:00:00", True),
        ("Invalid/Zone", "daily:12:00", False),
        ("Asia/Karachi", "daily:24:00", False),
        ("Asia/Karachi", "daily:27:30", False),
        ("Asia/Karachi", "daily:99:00", False),
        ("Asia/Karachi", "daily:23:60", False),
    ],
)
def test_review_schedule_database_inputs(review, runtime, zone, rule, valid):
    engine, scope = review
    item, _ = job_for(engine, scope, "success")
    data = {
        "name": uuid4().hex,
        "timezone": zone,
        "rule": rule,
        "next_due_at": datetime.now(UTC),
        "enabled": True,
        "missed_policy": "one_catchup",
        "input_ref": item["id"],
    }
    if valid:
        with transaction(runtime, *scope) as conn:
            schedule = insert(conn, "schedules", data)
        with pytest.raises(DBAPIError), transaction(engine, *scope) as conn:
            update(conn, "schedules", schedule, timezone="Invalid/Zone")
    else:
        with pytest.raises(DBAPIError), transaction(runtime, *scope) as conn:
            insert(conn, "schedules", data)


def test_review_schedule_corruption_isolated_from_maintenance(review, admin):
    engine, scope = review
    item, _ = job_for(engine, scope, "success")
    with transaction(engine, *scope) as conn:
        base = {
            "timezone": "Asia/Karachi",
            "rule": "daily:23:59",
            "next_due_at": clock(conn) - timedelta(minutes=2),
            "enabled": True,
            "missed_policy": "one_catchup",
            "input_ref": item["id"],
        }
        good = insert(conn, "schedules", {**base, "name": "valid"})
        bad = [insert(conn, "schedules", {**base, "name": "legacy-" + str(i)}) for i in range(2)]
    with admin.begin() as conn:
        conn.execute(text("ALTER TABLE app.schedules DISABLE TRIGGER runtime_schedule_validate"))
        conn.execute(
            text(
                "UPDATE app.schedules SET timezone='Invalid/Zone',record_version=record_version+1 WHERE id=:id"
            ),
            {"id": bad[0]["id"]},
        )
        conn.execute(
            text(
                "UPDATE app.schedules SET rule='daily:27:30',record_version=record_version+1 WHERE id=:id"
            ),
            {"id": bad[1]["id"]},
        )
        conn.execute(text("ALTER TABLE app.schedules ENABLE TRIGGER runtime_schedule_validate"))
    maintenance(engine, scope, "review-maintenance")
    with transaction(engine, *scope) as conn:
        for schedule in bad:
            value = get(conn, "schedules", schedule["id"])
            assert not value["enabled"] and value["last_error_code"] == "INVALID_SCHEDULE"
            assert not rows(
                conn, "SELECT id FROM app.schedule_slots WHERE schedule_id=:id", {"id": value["id"]}
            )
        assert (
            len(
                rows(
                    conn,
                    "SELECT id FROM app.schedule_slots WHERE schedule_id=:id",
                    {"id": good["id"]},
                )
            )
            == 1
        )
        assert tick(conn) == 0
        assert (
            len(
                rows(
                    conn,
                    "SELECT id FROM app.audit_entries WHERE action_type='schedule.quarantined'",
                )
            )
            == 2
        )
    assert next_daily(
        datetime(2026, 3, 8, 6, tzinfo=UTC), "America/New_York", "daily:02:30"
    ) == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)
    assert next_daily(
        datetime(2026, 11, 1, 4, tzinfo=UTC), "America/New_York", "daily:01:30"
    ) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert next_daily(
        datetime(2026, 11, 1, 5, 31, tzinfo=UTC), "America/New_York", "daily:01:30"
    ) == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)
