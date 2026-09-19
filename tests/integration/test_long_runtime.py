"""Phase 6A fault acceptance against PostgreSQL with real runtime identities."""

import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from company_os.application import long_tasks
from company_os.application import runtime as commands
from company_os.long_contracts import LongSpec, LongSubmission
from company_os.persistence.business import BusinessError
from company_os.persistence.database import make_engine, rows, transaction
from company_os.persistence.runtime import clock, get, update
from company_os.reporting.runtime import health
from company_os.workflow.runtime import execute_claim, renew_lease, run_one
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import settings as settings_fixture
from tests.conftest import worker_env as worker_env_fixture
from tests.integration.test_authority import PREFIX, granted, post, proposal
from tests.integration.test_identity_review import offline_mfa as offline_mfa_fixture
from tests.integration.test_runtime import WA, A, B, claim_exact, new_job
from tests.unit.test_long_isolation import alive

offline_mfa = offline_mfa_fixture


@pytest.fixture(scope="module")
def long_db_env(db_env):
    # Separate funded synthetic fixture; never alter the older regression's
    # budgets or erase its history to accommodate these additional effects.
    name = "company_os_long_" + uuid4().hex[:12]
    url = db_env["MIGRATION_DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    env = {**db_env}
    for key in ("MIGRATION_DATABASE_URL", "DATABASE_URL", "WORKER_DATABASE_URL"):
        env[key] = env[key].rsplit("/", 1)[0] + "/" + name
    with psycopg.connect(
        url.replace("postgresql+psycopg:", "postgresql:"), autocommit=True
    ) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
            )
            subprocess.run([sys.executable, "-m", "database.seeds.synthetic"], env=env, check=True)
            yield env
        finally:
            assert name.startswith("company_os_long_")
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture(scope="module")
def runtime(long_db_env):
    value = make_engine(long_db_env["DATABASE_URL"], pool_size=5)
    yield value
    value.dispose()


@pytest.fixture(scope="module")
def admin(long_db_env):
    value = make_engine(long_db_env["MIGRATION_DATABASE_URL"], pool_size=5)
    yield value
    value.dispose()


@pytest.fixture(scope="module")
def settings(long_db_env):
    return settings_fixture.__wrapped__(long_db_env)


@pytest.fixture(scope="module")
def worker_env(long_db_env):
    return worker_env_fixture.__wrapped__(long_db_env)


@pytest.fixture
def engine(long_db_env):
    value = make_engine(long_db_env["WORKER_DATABASE_URL"], pool_size=15)
    yield value
    value.dispose()


@pytest.fixture(autouse=True)
def finish_fixture_jobs(runtime):
    # End only this test's new synthetic work through the cancellation command;
    # preserve attempts/effects/reservations and all pre-existing fixtures.
    with transaction(runtime, *A) as conn:
        previous = {r["id"] for r in rows(conn, "SELECT id FROM app.jobs")}
    yield
    with transaction(runtime, *A) as conn:
        for job in rows(
            conn,
            "SELECT * FROM app.jobs WHERE state NOT IN ('succeeded','dead_letter','cancelled') ORDER BY created_at",
        ):
            if job["id"] not in previous:
                current = get(conn, "jobs", job["id"])
                if current["state"] not in commands.TERMINAL:
                    commands.cancel(
                        conn,
                        current["id"],
                        current["record_version"],
                        "Synthetic test finished; preserve history",
                    )


def long_job(runtime, handler="immediate_success", **settings):
    with transaction(runtime, *A) as conn:
        item = long_tasks.submit(
            conn,
            LongSubmission(logical_key=uuid4().hex, spec=LongSpec(handler=handler, **settings)),
            uuid4(),
        )
        commands.dispatch_outbox(conn)
        job = rows(conn, "SELECT * FROM app.jobs WHERE input_ref=:id", {"id": item["id"]})[0]
    return job


def launch(engine, job, stop=None, renew=True):
    if renew:
        with renew_lease(engine, WA, job):
            return execute_claim(engine, WA, job["lease_owner"], job, None, stop)
    return execute_claim(engine, WA, job["lease_owner"], job, None, stop)


def inspect(engine, job):
    with transaction(engine, *WA) as conn:
        current = get(conn, "jobs", job["id"])
        executions = rows(
            conn,
            "SELECT * FROM app.long_executions WHERE job_id=:id ORDER BY created_at",
            {"id": job["id"]},
        )
    return current, executions


@pytest.mark.parametrize(
    "handler,state,code",
    [
        ("immediate_success", "succeeded", None),
        ("sleep_success", "succeeded", None),
        ("infinite_cpu", "retry_wait", "HARD_TIMEOUT"),
        ("child_crash", "dead_letter", "CHILD_CRASH"),
        ("malformed_result", "dead_letter", "MALFORMED_IPC"),
        ("transient_read_timeout", "retry_wait", "READ_TIMEOUT"),
        ("network_hang", "retry_wait", "HARD_TIMEOUT"),
        ("network_drop", "retry_wait", "CONNECTION_DROP"),
        ("network_malformed", "dead_letter", "INVALID_RESPONSE"),
        ("network_delayed", "succeeded", None),
    ],
)
def test_long_fault_states(runtime, engine, handler, state, code):
    job = long_job(
        runtime,
        handler,
        hard_timeout_seconds=1.5,
        read_timeout_seconds=0.3 if handler == "transient_read_timeout" else 10,
    )
    claimed = claim_exact(engine, job)
    launch(engine, claimed)
    current, evidence = inspect(engine, job)
    assert (current["state"], current["last_error_code"]) == (state, code)
    assert evidence[0]["state"] == "finished"
    assert evidence[0]["details"]["elapsed_ms"] < 5500
    with transaction(engine, *WA) as conn:
        assert (
            len(rows(conn, "SELECT * FROM app.job_attempts WHERE job_id=:id", {"id": job["id"]}))
            == 2
        )


@pytest.mark.parametrize("handler,forced", [("cooperative_cancel", False), ("ignore_cancel", True)])
def test_durable_cancel(runtime, engine, handler, forced):
    job = long_job(runtime, handler, duration_seconds=120, hard_timeout_seconds=10)
    claimed = claim_exact(engine, job)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(launch, engine, claimed)
        time.sleep(1)
        with transaction(runtime, *A) as conn:
            current = get(conn, "jobs", job["id"])
            commands.cancel(
                conn, current["id"], current["record_version"], "Synthetic cancel during execution"
            )
        future.result(timeout=8)
    current, executions = inspect(engine, job)
    assert current["state"] == "cancelled"
    assert executions[0]["details"]["forced"] == forced


def test_fence_loss_and_replacement(runtime, engine, admin):
    job = long_job(
        runtime, "delayed_result_after_lease_loss", duration_seconds=2, hard_timeout_seconds=8
    )
    claimed = claim_exact(engine, job)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(launch, engine, claimed, None, False)
        time.sleep(0.8)
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE app.jobs SET lease_expires_at=now()-interval '1 second',record_version=record_version+1 WHERE id=:id"
                ),
                {"id": job["id"]},
            )
        with transaction(engine, *WA) as conn:
            commands.recover(conn)
            current = get(conn, "jobs", job["id"])
            update(conn, "jobs", current, available_at=clock(conn) - timedelta(seconds=1))
        replacement = claim_exact(engine, job)
        assert replacement["fence"] > claimed["fence"]
        future.result(timeout=8)
    current, executions = inspect(engine, job)
    assert current["fence"] == replacement["fence"] and current["state"] == "leased"
    assert executions[0]["outcome"] == "STALE_COMPLETION"
    with pytest.raises(BusinessError, match="STALE_FENCE"), transaction(engine, *WA) as conn:
        commands.finish(conn, claimed, "succeeded")
    launch(engine, replacement)
    assert inspect(engine, job)[0]["state"] == "succeeded"


@pytest.mark.parametrize("abandon_before_delivery", [False, True])
def test_valid_child_result_cannot_commit_after_replacement(
    runtime, engine, admin, monkeypatch, abandon_before_delivery
):
    from company_os.workflow import long_runtime
    from company_os.workflow.runtime import maintenance

    original_execute = long_runtime.execute
    ready, release = threading.Event(), threading.Event()

    def delayed_delivery(*args, **kwargs):
        outcome = original_execute(*args, **kwargs)
        assert outcome.code == "RESULT" and outcome.result.status == "succeeded"
        ready.set()
        assert release.wait(8)
        return outcome

    monkeypatch.setattr(long_runtime, "execute", delayed_delivery)
    job = long_job(runtime)
    old = claim_exact(engine, job)
    with transaction(engine, *WA) as conn:
        stale_before = next(
            c["count"] for c in health(conn)["components"] if c["name"] == "long_stale_completions"
        )
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(launch, engine, old, None, False)
        try:
            assert ready.wait(8)
            with admin.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE app.jobs SET lease_expires_at=now()-interval '1 second',record_version=record_version+1 WHERE id=:id"
                    ),
                    {"id": job["id"]},
                )
            if abandon_before_delivery:
                maintenance(engine, WA, "late-result-recovery")
            with transaction(engine, *WA) as conn:
                commands.recover(conn)
                current = get(conn, "jobs", job["id"])
                update(conn, "jobs", current, available_at=clock(conn) - timedelta(seconds=1))
            replacement = claim_exact(engine, job)
        finally:
            release.set()
        future.result(timeout=8)
    current, evidence = inspect(engine, job)
    assert current["fence"] == replacement["fence"] and current["state"] == "leased"
    assert evidence[0]["outcome"] == (
        "PARENT_OR_LEASE_LOST" if abandon_before_delivery else "STALE_COMPLETION"
    )
    with transaction(engine, *WA) as conn:
        stale_after = next(
            c["count"] for c in health(conn)["components"] if c["name"] == "long_stale_completions"
        )
        assert stale_after == stale_before + 1
    monkeypatch.setattr(long_runtime, "execute", original_execute)
    launch(engine, replacement)
    assert inspect(engine, job)[0]["state"] == "succeeded"


def test_renewal_beyond_original_sixty_second_lease(runtime, engine):
    job = long_job(runtime, "sleep_success", duration_seconds=64, hard_timeout_seconds=75)
    claimed = claim_exact(engine, job)
    original = claimed["lease_expires_at"]
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(launch, engine, claimed)
        time.sleep(61)
        with transaction(engine, *WA) as conn:
            current = commands.fenced(conn, claimed)
            assert current["lease_expires_at"] > original
            assert current["lease_expires_at"] > clock(conn)
            commands.recover(conn)
            assert get(conn, "jobs", job["id"])["fence"] == claimed["fence"]
        future.result(timeout=15)
    assert inspect(engine, job)[0]["state"] == "succeeded"


def test_remote_uncertainty_and_reconciliation(runtime, engine, admin):
    job = long_job(
        runtime, "fake_remote_accept_then_hang", hard_timeout_seconds=1.5, read_timeout_seconds=10
    )
    claimed = claim_exact(engine, job)
    launch(engine, claimed)
    with transaction(engine, *WA) as conn:
        current = get(conn, "jobs", job["id"])
        effect = get(conn, "external_effects", current["effect_id"])
        assert current["state"] == "waiting_external" and effect["state"] == "uncertain"
        assert get(conn, "budget_reservations", effect["reservation_id"])["state"] == "uncertain"
        receipt = rows(
            conn, "SELECT * FROM app.fake_receipts WHERE effect_id=:id", {"id": effect["id"]}
        )
        assert len(receipt) == 1
        reconciliation = rows(
            conn,
            "SELECT * FROM app.jobs WHERE job_type='reconcile_effect' AND effect_id=:id",
            {"id": effect["id"]},
        )[0]
    time.sleep(max(0, (receipt[0]["visible_after"] - datetime.now(UTC)).total_seconds()) + 0.1)
    with transaction(engine, *WA) as conn:
        # Claim safety through the real lane without queue interference.
        update(conn, "jobs", get(conn, "jobs", reconciliation["id"]), priority="interactive")
    recovered = claim_exact(engine, reconciliation)
    launch(engine, recovered)
    with transaction(engine, *WA) as conn:
        assert get(conn, "external_effects", effect["id"])["state"] == "confirmed"
        assert get(conn, "budget_reservations", effect["reservation_id"])["state"] == "settled"
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


def test_safety_capacity_and_shutdown(runtime, engine):
    jobs = [
        claim_exact(
            engine,
            long_job(runtime, "ignore_cancel", duration_seconds=120, hard_timeout_seconds=15),
        )
        for _ in range(4)
    ]
    stop = threading.Event()
    with ThreadPoolExecutor(4) as normal, ThreadPoolExecutor(1) as safety:
        futures = [normal.submit(launch, engine, job, stop) for job in jobs]
        time.sleep(1)
        safe = new_job(runtime, "safety", priority="safety")
        assert safety.submit(run_one, engine, WA, "safety-capacity", safety=True).result(timeout=5)
        with transaction(engine, *WA) as conn:
            assert get(conn, "jobs", safe["id"])["state"] == "succeeded"
        stop.set()
        for future in futures:
            future.result(timeout=8)
    assert all(inspect(engine, job)[0]["state"] == "retry_wait" for job in jobs)


def test_long_spec_rls_immutability_and_closed_input(runtime, engine):
    job = long_job(runtime)
    with transaction(runtime, *B) as conn:
        assert not rows(
            conn, "SELECT * FROM app.long_task_specs WHERE input_id=:id", {"id": job["input_ref"]}
        )
    with pytest.raises(DBAPIError), transaction(engine, *WA) as conn:
        conn.execute(
            text("UPDATE app.long_task_specs SET spec='{}' WHERE input_id=:id"),
            {"id": job["input_ref"]},
        )
    claimed = claim_exact(engine, job)
    launch(engine, claimed)
    with transaction(engine, *WA) as conn:
        names = {item["name"] for item in health(conn)["components"]}
        assert {"long_active", "long_timeouts", "long_stale_completions"} <= names
    with pytest.raises(ValueError):
        LongSpec(handler="immediate_success", url="https://invalid.example")


@pytest.mark.parametrize(
    "handler,scenario,state",
    [
        ("fake_remote_success", "effect_success", "succeeded"),
        ("fake_remote_reject", "effect_rejected", "dead_letter"),
        ("fake_remote_accept_then_hang", "effect_lost", "waiting_external"),
    ],
)
def test_governed_long_effect(client, offline_mfa, runtime, engine, handler, scenario, state):
    body = proposal()
    body["payload"]["scenario"] = scenario
    if scenario == "effect_lost":
        body["expires_at"] = (datetime.now(UTC) + timedelta(seconds=4)).isoformat()
    identifier, body = granted(client, offline_mfa, body)
    response = post(
        client,
        offline_mfa,
        "/approvals/" + identifier + "/execute",
        {"payload": body["payload"], "targets": body["targets"], "logical_key": uuid4().hex},
    )
    input_id = response.json()["data"]["input_id"]
    from uuid import UUID

    with transaction(runtime, *A) as conn:
        long_tasks.bind(
            conn,
            UUID(input_id),
            LongSpec(handler=handler, hard_timeout_seconds=5, read_timeout_seconds=10),
        )
        commands.dispatch_outbox(conn)
        job = rows(conn, "SELECT * FROM app.jobs WHERE input_ref=:id", {"id": input_id})[0]
    launch(engine, claim_exact(engine, job))
    assert inspect(engine, job)[0]["state"] == state
    detail = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    assert len(detail["uses"]) == 1
    assert (
        detail["uses"][0]["state"]
        == {"succeeded": "consumed", "dead_letter": "released", "waiting_external": "reserved"}[
            state
        ]
    )


def test_parent_crash_durable_recovery(runtime, engine, admin, worker_env):
    job = long_job(runtime, "infinite_cpu", hard_timeout_seconds=120)
    claimed = claim_exact(engine, job)
    script = """
import os,sys
from uuid import UUID
from tests.integration.test_long_runtime import launch
from tests.integration.test_runtime import WA
from company_os.persistence.database import make_engine,transaction
from company_os.persistence.runtime import get
engine=make_engine(os.environ['WORKER_DATABASE_URL'],pool_size=3)
with transaction(engine,*WA) as conn: job=get(conn,'jobs',UUID(sys.argv[1]))
launch(engine,job)
"""
    parent = subprocess.Popen(
        [sys.executable, "-c", script, str(job["id"])],
        env=worker_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        end = time.monotonic() + 10
        pid = None
        while time.monotonic() < end:
            with transaction(engine, *WA) as conn:
                entries = rows(
                    conn,
                    "SELECT outcome FROM app.audit_entries WHERE job_id=:id AND action_type='job.long_child_started'",
                    {"id": job["id"]},
                )
            if entries:
                pid = int(entries[0]["outcome"].split(":")[1])
                break
            time.sleep(0.1)
        assert pid and alive(pid)
        parent.kill()
        parent.wait(timeout=5)
        end = time.monotonic() + 5
        while alive(pid) and time.monotonic() < end:
            time.sleep(0.05)
        assert not alive(pid)
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE app.jobs SET lease_expires_at=now()-interval '1 second',record_version=record_version+1 WHERE id=:id"
                ),
                {"id": job["id"]},
            )
        with transaction(engine, *WA) as conn:
            commands.recover(conn)
            current = get(conn, "jobs", job["id"])
            assert current["state"] == "retry_wait" and current["fence"] > claimed["fence"]
            commands.cancel(
                conn,
                current["id"],
                current["record_version"],
                "Bounded fixture ends after durable recovery",
            )
        with pytest.raises(BusinessError, match="STALE_FENCE"), transaction(engine, *WA) as conn:
            commands.finish(conn, claimed, "succeeded")
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)


def test_cancel_before_claim_has_no_execution_or_reservation(runtime, engine):
    job = long_job(runtime, "fake_remote_success")
    with transaction(runtime, *A) as conn:
        commands.cancel(conn, job["id"], job["record_version"], "Cancel before synthetic dispatch")
        assert not rows(
            conn, "SELECT id FROM app.external_effects WHERE job_id=:id", {"id": job["id"]}
        )
        assert not rows(
            conn, "SELECT id FROM app.long_executions WHERE job_id=:id", {"id": job["id"]}
        )


def test_cancel_after_remote_accept_retains_accounting(runtime, engine):
    job = long_job(
        runtime, "fake_remote_accept_then_hang", hard_timeout_seconds=10, read_timeout_seconds=10
    )
    claimed = claim_exact(engine, job)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(launch, engine, claimed)
        end = time.monotonic() + 6
        accepted = False
        while time.monotonic() < end:
            with transaction(engine, *WA) as conn:
                current = get(conn, "jobs", job["id"])
                accepted = bool(
                    rows(
                        conn,
                        "SELECT id FROM app.fake_receipts WHERE effect_id=:id",
                        {"id": current["effect_id"]},
                    )
                )
            if accepted:
                break
            time.sleep(0.1)
        assert accepted
        with transaction(runtime, *A) as conn:
            current = get(conn, "jobs", job["id"])
            commands.cancel(
                conn, job["id"], current["record_version"], "Cancellation after remote acceptance"
            )
        future.result(timeout=8)
    with transaction(engine, *WA) as conn:
        current = get(conn, "jobs", job["id"])
        effect = get(conn, "external_effects", current["effect_id"])
        assert current["state"] == "waiting_external" and effect["state"] == "uncertain"
        assert get(conn, "budget_reservations", effect["reservation_id"])["state"] == "uncertain"


def test_worker_stop_file_drains_and_stops_intake(runtime, engine, worker_env, tmp_path):
    first = long_job(runtime, "ignore_cancel", duration_seconds=120, hard_timeout_seconds=120)
    with transaction(runtime, *A) as conn:
        update(conn, "jobs", get(conn, "jobs", first["id"]), priority="interactive")
    stop_file = tmp_path / "worker.stop"
    process = subprocess.Popen(
        [sys.executable, "-m", "apps.worker.main", "--stop-file", str(stop_file)],
        env={**worker_env, "LONG_EXECUTION_CAPACITY": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        until = time.monotonic() + 20
        pid = None
        while time.monotonic() < until and process.poll() is None:
            with transaction(engine, *WA) as conn:
                audit = rows(
                    conn,
                    "SELECT outcome FROM app.audit_entries WHERE job_id=:id AND action_type='job.long_child_started'",
                    {"id": first["id"]},
                )
            if audit:
                pid = int(audit[0]["outcome"].split(":")[1])
                break
            time.sleep(0.1)
        assert pid and alive(pid)
        second = long_job(runtime)
        start = time.monotonic()
        stop_file.write_text("stop")
        process.wait(timeout=10)
        assert process.returncode == 0 and time.monotonic() - start < 10
        assert not alive(pid)
        assert inspect(engine, first)[0]["state"] == "retry_wait"
        assert inspect(engine, second)[0]["attempt_count"] == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize("safety", [False, True])
@pytest.mark.parametrize("during_connection", [False, True])
def test_stop_file_checked_at_claim(
    runtime, engine, worker_env, tmp_path, monkeypatch, safety, during_connection
):
    from contextlib import contextmanager

    from company_os.workflow import runtime as workflow

    from apps.worker.main import slot

    job = new_job(
        runtime, "safety" if safety else "success", priority="safety" if safety else "interactive"
    )
    stop_file = tmp_path / "claim.stop"
    stop = threading.Event()
    original = workflow.transaction

    @contextmanager
    def connection_barrier(*args, **kwargs):
        with original(*args, **kwargs) as conn:
            # The slot's first check has passed; stop arrives during acquisition
            # of the actual claim transaction, before any job can be claimed.
            stop_file.write_text("stop")
            yield conn

    monkeypatch.setenv("WORKER_DATABASE_URL", worker_env["WORKER_DATABASE_URL"])
    if during_connection:
        monkeypatch.setattr(workflow, "transaction", connection_barrier)
    else:
        stop_file.write_text("stop")
    assert not slot(WA, "stop-at-claim", safety, stop, stop_file)
    assert stop.is_set()
    with transaction(engine, *WA) as conn:
        assert get(conn, "jobs", job["id"])["attempt_count"] == 0


def test_worker_stop_during_maintenance_prevents_both_lanes(runtime, engine, worker_env, tmp_path):
    jobs = [new_job(runtime, priority="interactive"), new_job(runtime, "safety", priority="safety")]
    stop_file = tmp_path / "maintenance.stop"
    script = """
import sys
from pathlib import Path
from apps.worker import main as worker
stop_file=Path(sys.argv[1])
original=worker.maintenance
def maintenance(*args,**kwargs):
    original(*args,**kwargs)
    stop_file.write_text('stop')
worker.maintenance=maintenance
sys.argv=[sys.argv[0],'--stop-file',str(stop_file)]
worker.main()
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(stop_file)],
        env={**worker_env, "LONG_EXECUTION_CAPACITY": "3"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert process.returncode == 0 and stop_file.exists()
    with transaction(engine, *WA) as conn:
        assert all(get(conn, "jobs", job["id"])["attempt_count"] == 0 for job in jobs)


def test_worker_stop_with_spare_capacity(runtime, engine, worker_env, tmp_path):
    first = long_job(runtime, "ignore_cancel", duration_seconds=120, hard_timeout_seconds=120)
    with transaction(runtime, *A) as conn:
        update(conn, "jobs", get(conn, "jobs", first["id"]), priority="interactive")
    stop_file = tmp_path / "spare.stop"
    release = stop_file.with_suffix(".release")
    script = """
import sys,time,threading
from pathlib import Path
from apps.worker import main as worker
from database.seeds.synthetic import key
stop_file=Path(sys.argv[1]); release=stop_file.with_suffix('.release')
original=worker.run_one
lock=threading.Lock(); admitted=False
def barrier(*args,**kwargs):
    global admitted
    with lock:
        first=not admitted and not kwargs.get('safety') and args[1][1]==key('workspace-a')
        if first: admitted=True
    if not first:
        until=time.monotonic()+20
        while not release.exists():
            if time.monotonic()>until: raise RuntimeError('Fixture admission barrier expired')
            time.sleep(0.01)
    return original(*args,**kwargs)
worker.run_one=barrier
sys.argv=[sys.argv[0],'--stop-file',str(stop_file)]
worker.main()
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(stop_file)],
        env={**worker_env, "LONG_EXECUTION_CAPACITY": "3"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        until = time.monotonic() + 15
        pid = None
        while time.monotonic() < until and process.poll() is None:
            with transaction(engine, *WA) as conn:
                audit = rows(
                    conn,
                    "SELECT outcome FROM app.audit_entries WHERE job_id=:id AND action_type='job.long_child_started'",
                    {"id": first["id"]},
                )
            if audit:
                pid = int(audit[0]["outcome"].split(":")[1])
                break
            time.sleep(0.05)
        assert pid and alive(pid)
        queued = [new_job(runtime), new_job(runtime, "safety", priority="safety")]
        stop_file.write_text("stop")
        release.write_text("release paused intake")
        process.wait(timeout=10)
        assert process.returncode == 0 and not alive(pid)
        assert inspect(engine, first)[0]["state"] == "retry_wait"
        with transaction(engine, *WA) as conn:
            assert all(get(conn, "jobs", job["id"])["attempt_count"] == 0 for job in queued)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
