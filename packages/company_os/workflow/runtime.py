"""Finite worker execution through shared application commands."""

import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from company_os.adapters import fake_effects
from company_os.application import authority
from company_os.application import runtime as command
from company_os.application.scheduler import tick
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows, transaction
from company_os.persistence.runtime import clock, get, insert, update


def pulse(conn: Any, component: str, instance: str) -> None:
    found = rows(
        conn,
        "SELECT * FROM app.runtime_heartbeats WHERE component=:c AND instance=:i FOR UPDATE",
        {"c": component, "i": instance},
    )
    if found:
        update(conn, "runtime_heartbeats", found[0], measured_at=clock(conn))
    else:
        insert(
            conn,
            "runtime_heartbeats",
            {"component": component, "instance": instance, "measured_at": clock(conn)},
        )


def maintenance(engine: Engine, scope: tuple[UUID, UUID, int], instance: str) -> None:
    with transaction(engine, *scope) as conn:
        pulse(conn, "worker", instance)
        command.refresh_coalesced(conn)
        command.recover(conn)
        for execution in rows(
            conn,
            """SELECT x.* FROM app.long_executions x JOIN app.jobs j ON j.workspace_id=x.workspace_id AND j.id=x.job_id
            WHERE x.state='active' AND (j.fence<>x.fence OR j.lease_expires_at IS NULL OR j.lease_expires_at<=clock_timestamp())
            ORDER BY x.id FOR UPDATE OF x SKIP LOCKED""",
        ):
            update(
                conn,
                "long_executions",
                execution,
                state="abandoned",
                ended_at=clock(conn),
                outcome="PARENT_OR_LEASE_LOST",
                details={"cleanup_confirmation": "unavailable"},
            )
            command.audit(
                conn,
                "job.long_abandoned",
                execution["job_id"],
                execution["id"],
                outcome="recovery_required",
            )
        command.dispatch_outbox(conn)
        tick(conn)
        pulse(conn, "scheduler", instance)
        # Unknown reconciliation yields without retaining a lease.
        for job in rows(
            conn,
            "SELECT * FROM app.jobs WHERE job_type='reconcile_effect' AND state='waiting_external' AND available_at<=now() FOR UPDATE SKIP LOCKED",
        ):
            update(conn, "jobs", job, state="queued")


def run_one(
    engine: Engine,
    scope: tuple[UUID, UUID, int],
    owner: str,
    *,
    safety: bool = False,
    crash_at: str | None = None,
    shutdown: threading.Event | None = None,
    stop_claim: Callable[[], bool] | None = None,
) -> bool:
    with transaction(engine, *scope) as conn:
        # Check after connection/context acquisition, immediately before claim.
        if (shutdown and shutdown.is_set()) or (stop_claim and stop_claim()):
            return False
        job = command.claim(conn, owner, safety=safety)
    if not job:
        return False
    if crash_at == "after_claim":
        raise SystemExit("Synthetic crash after claim")
    started = time.monotonic()
    with renew_lease(engine, scope, job):
        result = execute_claim(engine, scope, owner, job, crash_at, shutdown)
    with transaction(engine, *scope) as conn:
        current = get(conn, "jobs", job["id"])
    print(
        json.dumps(
            {
                "service": "worker",
                "handler": job["job_type"],
                "job_id": str(job["id"]),
                "event_id": str(job["origin_event_id"]) if job["origin_event_id"] else None,
                "correlation_id": str(job["correlation_id"]),
                "workspace": command.digest(str(scope[1]))[:16],
                "attempt": job["attempt_count"],
                "fence": job["fence"],
                "effect_id": str(current["effect_id"]) if current["effect_id"] else None,
                "outcome": current["state"],
                "error_code": current["last_error_code"],
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        ),
        flush=True,
    )
    return result


@contextmanager
def renew_lease(
    engine: Engine, scope: tuple[UUID, UUID, int], job: dict[str, Any], *, interval: float = 15
) -> Iterator[None]:
    stop = threading.Event()

    def renew() -> None:
        while not stop.wait(interval):
            try:
                with transaction(engine, *scope) as conn:
                    command.heartbeat(conn, job)
            except (BusinessError, SQLAlchemyError):
                # Never log database exceptions/parameters. Every subsequent
                # mutation still checks the current owner, expiry and fence.
                print(
                    json.dumps(
                        {
                            "service": "worker",
                            "job_id": str(job["id"]),
                            "error_code": "LEASE_RENEWAL_STOPPED",
                        }
                    ),
                    flush=True,
                )
                return

    thread = threading.Thread(target=renew, name="runtime-lease", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=6)


def execute_claim(
    engine: Engine,
    scope: tuple[UUID, UUID, int],
    owner: str,
    job: dict[str, Any],
    crash_at: str | None,
    shutdown: threading.Event | None = None,
) -> bool:
    with transaction(engine, *scope) as conn:
        current = command.fenced(conn, job)
        if current["cancel_requested_at"]:
            command.finish(conn, current, "cancelled")
            return True
        current = update(conn, "jobs", current, state="running")
        command.emit(conn, "job.started", current, "job")
        item = get(conn, "runtime_inputs", current["input_ref"])
    scenario = item["scenario"]
    if job["job_type"] != "reconcile_effect":
        with transaction(engine, *scope) as conn:
            specs = rows(
                conn, "SELECT * FROM app.long_task_specs WHERE input_id=:id", {"id": item["id"]}
            )
        if specs:
            from company_os.workflow.long_runtime import run_long

            return run_long(engine, scope, job, specs[0], shutdown)
    if crash_at == "during_internal":
        raise SystemExit("Synthetic crash during work")
    if job["job_type"] == "reconcile_effect":
        with transaction(engine, *scope) as conn:
            command.fenced(conn, job)
            effect = get(conn, "external_effects", job["effect_id"], lock=True)
            receipt = fake_effects.reconcile(conn, effect)
            if receipt:
                effect = command.resolve_effect(conn, effect, receipt)
                origin = get(conn, "jobs", effect["job_id"], lock=True)
                if origin["state"] == "waiting_external":
                    origin = update(
                        conn,
                        "jobs",
                        origin,
                        state="succeeded" if effect["state"] == "confirmed" else "dead_letter",
                        last_error_code=None if effect["state"] == "confirmed" else "REJECTED",
                    )
                    command.emit(
                        conn,
                        "job.succeeded" if effect["state"] == "confirmed" else "job.failed",
                        origin,
                        "job",
                    )
                    command.refresh_workflow(conn, origin)
                    if origin["state"] == "dead_letter":
                        command.incident(conn, "dead_letter", origin)
                    else:
                        command.resolve_recovery(conn, origin)
                command.finish(conn, job, "succeeded")
            else:
                command.finish(
                    conn,
                    job,
                    "dead_letter"
                    if job["attempt_count"] >= job["max_attempts"]
                    else "waiting_external",
                    code="STILL_UNKNOWN",
                    delay=30,
                )
        return True
    if scenario.startswith("effect_"):
        try:
            with transaction(engine, *scope) as conn:
                effect = command.prepare_effect(conn, job)
                if effect["job_id"] != job["id"]:
                    state, code = command.coalesced_result(effect)
                    command.finish(conn, job, state, code=code)
                    return True
                if effect["state"] in {"confirmed", "rejected", "uncertain", "dispatching"}:
                    command.finish(
                        conn,
                        job,
                        "succeeded"
                        if effect["state"] == "confirmed"
                        else "waiting_external"
                        if effect["state"] in {"uncertain", "dispatching"}
                        else "dead_letter",
                        code=None if effect["state"] == "confirmed" else "EFFECT_HELD",
                    )
                    return True
            with transaction(engine, *scope) as conn:
                effect = command.begin_dispatch(conn, job, effect["id"])
            if crash_at == "before_call":
                raise SystemExit("Synthetic crash before call")
            with transaction(engine, *scope) as conn:
                current = command.fenced(conn, job)
                authority_binding = rows(
                    conn,
                    "SELECT manifest_id FROM app.authority_bindings WHERE input_id=:id",
                    {"id": effect["request_ref"]},
                )
                if authority_binding:
                    denial = authority.validate(conn, authority_binding[0]["manifest_id"])
                    if denial:
                        raise BusinessError(denial, 423)
                    authority.validate_budget(conn, effect)
                if (
                    current["cancel_requested_at"]
                    or current["deadline_at"] <= clock(conn)
                    or not get(conn, "fake_endpoints", effect["connection_id"])["enabled"]
                ):
                    raise BusinessError("DISPATCH_CANCELLED")
                if authority_binding:
                    authority.final_temporal_check(conn, authority_binding[0]["manifest_id"])
                receipt = fake_effects.accept(conn, effect, scenario)
                pulse(conn, "fake_adapter", owner)
            if crash_at in {"during_call", "after_remote_success"}:
                raise SystemExit("Synthetic crash after remote acceptance")
            with transaction(engine, *scope) as conn:
                command.fenced(conn, job)
                effect = get(conn, "external_effects", effect["id"], lock=True)
                if scenario in {"effect_lost", "effect_unknown"}:
                    command.uncertain(conn, effect)
                    command.finish(conn, job, "waiting_external", code="UNCERTAIN_EFFECT")
                else:
                    command.resolve_effect(conn, effect, receipt)
                    command.finish(
                        conn,
                        job,
                        "succeeded" if receipt["outcome"] == "confirmed" else "dead_letter",
                        code=None if receipt["outcome"] == "confirmed" else "REJECTED",
                    )
        except BusinessError as error:
            if error.code == "STALE_FENCE":
                raise
            with transaction(engine, *scope) as conn:
                current = command.fenced(conn, job)
                authority.record_runtime_decision(conn, current, error.code)
                pending_effect = (
                    get(conn, "external_effects", current["effect_id"], lock=True)
                    if current["effect_id"]
                    else None
                )
                if pending_effect and pending_effect["state"] in {"dispatching", "uncertain"}:
                    command.uncertain(conn, pending_effect)
                    command.finish(conn, job, "waiting_external", code="UNCERTAIN_EFFECT")
                elif error.code in {
                    "BUDGET_EXHAUSTED",
                    "BUDGET_UNCONFIGURED",
                    "COMPANY_BUDGET_EXHAUSTED",
                }:
                    command.finish(conn, job, "waiting_external", code=error.code)
                else:
                    command.failed(conn, job, error.code)
        return True
    with transaction(engine, *scope) as conn:
        if scenario in {"invalid", "exhausted"} or (
            scenario == "transient" and job["attempt_count"] == 1
        ):
            command.failed(
                conn,
                job,
                "INVALID_INPUT" if scenario == "invalid" else "TRANSIENT",
                transient=scenario != "invalid",
            )
        elif scenario == "wait" and not rows(
            conn,
            "SELECT id FROM app.fake_observations WHERE input_ref=:id UNION ALL SELECT id FROM app.runtime_completions WHERE result_ref=:id",
            {"id": item["id"]},
        ):
            command.finish(conn, job, "waiting_external")
        else:
            command.finish(conn, job, "succeeded")
    if crash_at == "after_commit":
        raise SystemExit("Synthetic crash after local completion")
    return True
