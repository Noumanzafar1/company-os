"""Shared durable runtime commands. Call only within a verified scoped transaction."""

import hashlib
import json
import math
import random
from datetime import UTC, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows
from company_os.persistence.runtime import clock, get, insert, update
from company_os.runtime_contracts import SyntheticInput

EVENTS = {
    "policy.activated",
    "approval.requested",
    "approval.granted",
    "approval.rejected",
    "approval.revoked",
    "approval.invalidated",
    "approval.expired",
    "test.aggregate_changed",
    "test.effect_requested",
    "job.started",
    "job.succeeded",
    "job.retry_scheduled",
    "job.waiting",
    "job.failed",
    "job.cancelled",
    "effect.uncertain",
    "effect.reconciled",
    "budget.warning",
    "budget.exhausted",
    "security.incident_opened",
    "security.incident_resolved",
}
TERMINAL = {"succeeded", "dead_letter", "cancelled"}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def audit(
    conn: Connection,
    action: str,
    identifier: UUID,
    correlation: UUID,
    *,
    outcome: str = "committed",
    event_id: UUID | None = None,
    causation_id: UUID | None = None,
    actor_type: str | None = None,
) -> None:
    effect = get(conn, "external_effects", identifier) if action.startswith("effect.") else None
    job_id = effect["job_id"] if effect else identifier if action.startswith("job.") else None
    attempts = (
        rows(
            conn,
            "SELECT id FROM app.job_attempts WHERE job_id=:id ORDER BY attempt_no DESC, CASE phase WHEN 'finish' THEN 0 ELSE 1 END LIMIT 1",
            {"id": job_id},
        )
        if job_id
        else []
    )
    conn.execute(
        text("""INSERT INTO app.audit_entries(id,workspace_id,created_by,actor_id,actor_type,action_type,target_type,target_id,request_id,correlation_id,command_id,decision,outcome,change_summary,payload_hash,policy_version,event_id,causation_id,job_id,effect_id,attempt_id,provider_request_id)
    VALUES(:id,app.current_workspace_id(),app.current_principal_id(),app.current_principal_id(),COALESCE(CAST(:actor_type AS text),CASE WHEN current_user='company_worker' THEN 'service' ELSE 'user' END),:action,'runtime',:target,:correlation,:correlation,:correlation,'allow',:outcome,:action,:hash,'phase-4-fake-v1',:event,:causation,:job,:effect,:attempt,:provider_request)"""),
        {
            "id": uuid4(),
            "action": action,
            "target": identifier,
            "correlation": correlation,
            "outcome": outcome,
            "hash": digest({"action": action, "target": identifier}),
            "event": event_id,
            "causation": causation_id,
            "job": job_id,
            "effect": effect["id"] if effect else None,
            "attempt": attempts[0]["id"] if attempts else None,
            "provider_request": effect["provider_request_id"] if effect else None,
            "actor_type": actor_type,
        },
    )


def emit(
    conn: Connection,
    kind: str,
    item: dict[str, Any],
    aggregate: str,
    *,
    causation: UUID | None = None,
) -> dict[str, Any]:
    if aggregate == "effect":
        item = {**item, "correlation_id": get(conn, "jobs", item["job_id"])["correlation_id"]}
    if kind not in EVENTS:
        raise BusinessError("UNKNOWN_EVENT_SCHEMA")
    event = insert(
        conn,
        "events",
        {
            "event_type": kind,
            "aggregate_type": aggregate,
            "aggregate_id": item["id"],
            "aggregate_version": item.get("record_version", 1),
            "actor_type": "service"
            if conn.execute(text("SELECT current_user")).scalar_one() == "company_worker"
            else "user",
            "actor_id": conn.execute(text("SELECT app.current_principal_id()")).scalar_one(),
            "causation_id": causation,
            "correlation_id": item.get("correlation_id", item["id"]),
            "origin": "company_os",
            "classification": "internal",
            "payload": event_payload(aggregate, item),
            "schema_version": 2,
            "trace_id": str(item.get("correlation_id", item["id"])),
        },
    )
    insert(conn, "outbox", {"event_id": event["id"]})
    audit(
        conn,
        kind,
        item["id"],
        event["correlation_id"],
        event_id=event["id"],
        causation_id=causation,
    )
    return event


def submit(conn: Connection, request: SyntheticInput, correlation: UUID) -> dict[str, Any]:
    # Serializes one logical command even with different HTTP request keys.
    conn.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended(app.current_workspace_id()::text||:key,4))"
        ),
        {"key": request.logical_key},
    )
    found = rows(
        conn,
        "SELECT * FROM app.runtime_inputs WHERE logical_key=:key",
        {"key": request.logical_key},
    )
    content_hash = digest(request.model_dump())
    if found:
        if found[0]["content_hash"] != content_hash:
            raise BusinessError("IDEMPOTENCY_CONFLICT")
        return found[0]
    item = insert(conn, "runtime_inputs", {**request.model_dump(), "content_hash": content_hash})
    item["correlation_id"] = correlation
    emit(
        conn,
        "test.effect_requested"
        if request.scenario.startswith("effect_")
        else "test.aggregate_changed",
        item,
        "runtime_input",
    )
    return item


def enqueue(
    conn: Connection,
    item: dict[str, Any],
    key: str,
    correlation: UUID,
    *,
    origin: UUID | None = None,
    priority: str = "normal",
    effect: UUID | None = None,
    replay: str = "",
    workflow: UUID | None = None,
) -> dict[str, Any]:
    found = rows(
        conn,
        "SELECT * FROM app.jobs WHERE job_type=:type AND idempotency_key=:key",
        {"type": "reconcile_effect" if effect else "synthetic", "key": key},
    )
    if found:
        return found[0]
    long_specs = (
        rows(conn, "SELECT spec FROM app.long_task_specs WHERE input_id=:id", {"id": item["id"]})
        if not effect
        else []
    )
    return insert(
        conn,
        "jobs",
        {
            "job_type": "reconcile_effect" if effect else "synthetic",
            "job_version": 1,
            "timeout_seconds": math.ceil(long_specs[0]["spec"]["hard_timeout_seconds"])
            if long_specs
            else 30,
            "workflow_run_id": workflow,
            "subject_id": item["id"],
            "input_ref": item["id"],
            "input_hash": item["content_hash"],
            "state": "queued",
            "priority": priority,
            "deadline_at": clock(conn) + (timedelta(minutes=30) if effect else timedelta(hours=24)),
            "max_attempts": 10 if effect else 3,
            "idempotency_key": key,
            "origin_event_id": origin,
            "correlation_id": correlation,
            "effect_id": effect,
            "replay_namespace": replay,
        },
    )


def consume(conn: Connection, event: dict[str, Any], *, replay: str = "") -> None:
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:id,2))"), {"id": str(event["id"])}
    )
    name = "runtime-v1" if not replay else "replay:" + replay
    if rows(
        conn,
        "SELECT id FROM app.consumer_receipts WHERE event_id=:id AND consumer_name=:name",
        {"id": event["id"], "name": name},
    ):
        return
    if event["schema_version"] not in (1, 2) or event["event_type"] not in EVENTS:
        raise BusinessError("UNKNOWN_EVENT_SCHEMA")
    if event["event_type"] in {"test.aggregate_changed", "test.effect_requested"}:
        item = get(conn, "runtime_inputs", event["aggregate_id"])
        workflow = insert(
            conn,
            "workflow_runs",
            {
                "type": "synthetic",
                "version": 1,
                "subject_id": item["id"],
                "state": "running",
                "correlation_id": event["correlation_id"],
            },
        )
        enqueue(
            conn,
            item,
            f"{name}:{item['id']}",
            event["correlation_id"],
            origin=event["id"],
            priority="safety" if item["scenario"] == "safety" else "normal",
            replay=replay,
            workflow=workflow["id"],
        )
    insert(
        conn,
        "consumer_receipts",
        {
            "event_id": event["id"],
            "consumer_name": name,
            "consumer_version": 1,
            "replay_namespace": replay,
        },
    )


def dispatch_outbox(conn: Connection, limit: int = 50) -> int:
    pending = rows(
        conn,
        "SELECT * FROM app.outbox WHERE dispatched_at IS NULL AND available_at<=now() ORDER BY created_at,id LIMIT :limit FOR UPDATE SKIP LOCKED",
        {"limit": limit},
    )
    for outbox in pending:
        event = get(conn, "events", outbox["event_id"])
        consume(conn, event)
        update(conn, "outbox", outbox, attempts=outbox["attempts"] + 1, dispatched_at=clock(conn))
    return len(pending)


def claim(conn: Connection, owner: str, *, safety: bool = False) -> dict[str, Any] | None:
    found = rows(
        conn,
        """SELECT j.* FROM app.jobs j WHERE j.state IN ('queued','retry_wait') AND j.available_at<=now() AND j.deadline_at>now() AND j.cancel_requested_at IS NULL AND ((j.priority='safety')=:safety)
    AND NOT EXISTS(SELECT 1 FROM app.job_dependencies d JOIN app.jobs p ON p.id=d.depends_on_job_id AND p.workspace_id=d.workspace_id WHERE d.job_id=j.id AND ((d.condition='succeeded' AND p.state<>'succeeded') OR (d.condition='terminal' AND p.state NOT IN ('succeeded','dead_letter','cancelled'))))
    ORDER BY CASE j.priority WHEN 'safety' THEN 0 WHEN 'interactive' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,j.created_at,j.id LIMIT 1 FOR UPDATE OF j SKIP LOCKED""",
        {"safety": safety},
    )
    if not found:
        return None
    job = found[0]
    job = update(
        conn,
        "jobs",
        job,
        state="leased",
        lease_owner=owner,
        lease_expires_at=clock(conn) + timedelta(seconds=60),
        heartbeat_at=clock(conn),
        fence=job["fence"] + 1,
        attempt_count=job["attempt_count"] + 1,
    )
    insert(
        conn,
        "job_attempts",
        {
            "job_id": job["id"],
            "attempt_no": job["attempt_count"],
            "worker_id": owner,
            "fence": job["fence"],
            "phase": "start",
            "started_at": clock(conn),
            "outcome": "claimed",
            "effect_id": job["effect_id"],
            "reservation_id": job["budget_reservation_id"],
        },
    )
    return job


def fenced(conn: Connection, claim: dict[str, Any]) -> dict[str, Any]:
    job = get(conn, "jobs", claim["id"], lock=True)
    if (
        job["fence"] != claim["fence"]
        or job["lease_owner"] != claim["lease_owner"]
        or job["state"] not in {"leased", "running", "cancel_requested"}
        or job["lease_expires_at"] <= clock(conn)
    ):
        raise BusinessError("STALE_FENCE")
    return job


def heartbeat(conn: Connection, claimed: dict[str, Any]) -> dict[str, Any]:
    job = fenced(conn, claimed)
    return update(
        conn,
        "jobs",
        job,
        heartbeat_at=clock(conn),
        lease_expires_at=clock(conn) + timedelta(seconds=60),
    )


def finish(
    conn: Connection,
    claimed: dict[str, Any],
    state: str,
    *,
    code: str | None = None,
    delay: float = 0,
) -> dict[str, Any]:
    job = fenced(conn, claimed)
    if job["cancel_requested_at"] and state == "succeeded":
        state = "cancelled"
    if state in {"dead_letter", "cancelled"} and job["effect_id"]:
        effect = get(conn, "external_effects", job["effect_id"], lock=True)
        if effect["job_id"] == job["id"] and effect["state"] == "prepared":
            # Dispatch never began, so non-use is proven. Ambiguous effects
            # retain their reservations and can only be reconciled.
            update(conn, "external_effects", effect, state="cancelled")
            settle(conn, effect["reservation_id"], Decimal(0))
            release_quota(conn, effect, consumed=False)
    start = rows(
        conn,
        "SELECT started_at FROM app.job_attempts WHERE job_id=:id AND attempt_no=:attempt AND phase='start'",
        {"id": job["id"], "attempt": job["attempt_count"]},
    )[0]
    insert(
        conn,
        "job_attempts",
        {
            "job_id": job["id"],
            "attempt_no": job["attempt_count"],
            "worker_id": job["lease_owner"],
            "fence": job["fence"],
            "phase": "finish",
            "started_at": start["started_at"],
            "ended_at": clock(conn),
            "outcome": state,
            "error_code": code,
            "effect_id": job["effect_id"],
            "reservation_id": job["budget_reservation_id"],
        },
    )
    job = update(
        conn,
        "jobs",
        job,
        state=state,
        lease_owner=None,
        lease_expires_at=None,
        heartbeat_at=None,
        last_error_code=code,
        available_at=clock(conn) + timedelta(seconds=delay),
    )
    kind = {
        "succeeded": "job.succeeded",
        "cancelled": "job.cancelled",
        "dead_letter": "job.failed",
        "retry_wait": "job.retry_scheduled",
    }.get(state, "job.waiting")
    emit(conn, kind, job, "job", causation=job["origin_event_id"])
    refresh_workflow(conn, job)
    if state == "dead_letter":
        incident(conn, "dead_letter", job)
    elif state == "succeeded":
        resolve_recovery(conn, job)
    return job


def resolve_recovery(conn: Connection, job: dict[str, Any]) -> None:
    """Resolve current incidents, never rewrite failed jobs or their attempts."""
    if job["state"] != "succeeded" or not job["recovery_of_id"]:
        return
    ancestors = rows(
        conn,
        """WITH RECURSIVE prior AS (
        SELECT id,recovery_of_id FROM app.jobs WHERE id=:id
        UNION SELECT j.id,j.recovery_of_id FROM app.jobs j JOIN prior p ON j.id=p.recovery_of_id
    ) SELECT id FROM prior""",
        {"id": job["recovery_of_id"]},
    )
    for ancestor in ancestors:
        for inc in rows(
            conn,
            "SELECT * FROM app.incidents WHERE fingerprint=:key AND kind='dead_letter' AND state<>'resolved' FOR UPDATE",
            {"key": "dead_letter:" + str(ancestor["id"])},
        ):
            inc = update(conn, "incidents", inc, state="resolved", resolved_at=clock(conn))
            for attention in rows(
                conn,
                "SELECT * FROM app.runtime_attention WHERE incident_id=:id AND state<>'resolved' FOR UPDATE",
                {"id": inc["id"]},
            ):
                update(conn, "runtime_attention", attention, state="resolved")
            emit(conn, "security.incident_resolved", inc, "incident")


def coalesced_result(effect: dict[str, Any]) -> tuple[str, str | None]:
    return {
        "confirmed": ("succeeded", None),
        "rejected": ("dead_letter", "REJECTED"),
        "cancelled": ("cancelled", "CANONICAL_EFFECT_CANCELLED"),
    }.get(effect["state"], ("waiting_external", "COALESCED_EFFECT"))


def refresh_coalesced(conn: Connection) -> None:
    """Read canonical results without taking ownership or locking their effect."""
    for job in rows(
        conn,
        """SELECT j.* FROM app.jobs j JOIN app.external_effects e
        ON e.workspace_id=j.workspace_id AND e.id=j.coalesced_effect_id
        WHERE j.state='waiting_external'
        AND e.state IN ('confirmed','rejected','cancelled')
        ORDER BY j.id LIMIT 100 FOR UPDATE OF j SKIP LOCKED""",
    ):
        effect = get(conn, "external_effects", job["coalesced_effect_id"])
        state, code = coalesced_result(effect)
        job = update(conn, "jobs", job, state=state, last_error_code=code)
        emit(
            conn,
            {
                "succeeded": "job.succeeded",
                "dead_letter": "job.failed",
                "cancelled": "job.cancelled",
            }[state],
            job,
            "job",
            causation=job["origin_event_id"],
        )
        refresh_workflow(conn, job)
        if state == "dead_letter":
            incident(conn, "dead_letter", job)
        elif state == "succeeded":
            resolve_recovery(conn, job)


def refresh_workflow(conn: Connection, job: dict[str, Any]) -> None:
    """Recompute the finite parent after every job transition, including recovery."""
    if job["workflow_run_id"]:
        workflow = get(conn, "workflow_runs", job["workflow_run_id"], lock=True)
        others = rows(
            conn, "SELECT state FROM app.jobs WHERE workflow_run_id=:id", {"id": workflow["id"]}
        )
        states = {j["state"] for j in others}
        wf = (
            "failed"
            if "dead_letter" in states
            else "succeeded"
            if states == {"succeeded"}
            else "cancelled"
            if states <= TERMINAL
            else "waiting"
            if states <= {"succeeded", "waiting_external", "waiting_approval"}
            else "running"
        )
        update(conn, "workflow_runs", workflow, state=wf)


def incident(conn: Connection, kind: str, item: dict[str, Any]) -> dict[str, Any]:
    fingerprint = f"{kind}:{item['id']}"
    found = rows(conn, "SELECT * FROM app.incidents WHERE fingerprint=:key", {"key": fingerprint})
    if found:
        return found[0]
    value = insert(
        conn,
        "incidents",
        {
            "severity": "P1",
            "kind": kind,
            "state": "open",
            "owner_id": item["created_by"],
            "fingerprint": fingerprint,
        },
    )
    insert(
        conn,
        "incident_evidence",
        {
            "incident_id": value["id"],
            "effect_id" if kind == "uncertain_effect" else "job_id": item["id"],
        },
    )
    insert(conn, "runtime_attention", {"incident_id": value["id"], "state": "open"})
    emit(conn, "security.incident_opened", value, "incident")
    return value


def failed(
    conn: Connection,
    claimed: dict[str, Any],
    code: str,
    *,
    transient: bool = False,
    retry_after: float = 0,
) -> dict[str, Any]:
    job = fenced(conn, claimed)
    cap = 30 if job["attempt_count"] == 1 else 120
    delay = max(retry_after, random.uniform(5 if cap == 30 else 30, cap))
    retry = (
        transient
        and job["attempt_count"] < job["max_attempts"]
        and clock(conn) + timedelta(seconds=delay) < job["deadline_at"]
    )
    return finish(
        conn, job, "retry_wait" if retry else "dead_letter", code=code, delay=delay if retry else 0
    )


def recover(conn: Connection) -> int:
    for expired_job in rows(
        conn,
        "SELECT * FROM app.jobs WHERE state IN ('queued','retry_wait','waiting_approval','waiting_external') AND deadline_at<=now() FOR UPDATE SKIP LOCKED",
    ):
        expired_job = update(
            conn, "jobs", expired_job, state="dead_letter", last_error_code="DEADLINE_EXPIRED"
        )
        emit(conn, "job.failed", expired_job, "job")
        refresh_workflow(conn, expired_job)
        incident(conn, "dead_letter", expired_job)
    expired = rows(
        conn,
        "SELECT * FROM app.jobs WHERE state IN ('leased','running','cancel_requested') AND lease_expires_at<=now() ORDER BY id FOR UPDATE SKIP LOCKED",
    )
    for job in expired:
        # Recovery becomes the next fencing authority; the old owner never completes.
        replacement = update(
            conn,
            "jobs",
            job,
            fence=job["fence"] + 1,
            lease_owner="recovery",
            lease_expires_at=clock(conn) + timedelta(seconds=60),
        )
        if job["effect_id"]:
            effect = get(conn, "external_effects", job["effect_id"], lock=True)
            if effect["state"] in {"dispatching", "uncertain"}:
                uncertain(conn, effect)
                finish(conn, replacement, "waiting_external", code="UNCERTAIN_EFFECT")
                continue
            if effect["state"] == "confirmed":
                finish(conn, replacement, "succeeded")
                continue
        if job["cancel_requested_at"]:
            finish(conn, replacement, "cancelled")
        else:
            failed(conn, replacement, "LEASE_EXPIRED", transient=True)
    return len(expired)


def reserve(
    conn: Connection, budget_id: UUID, job: dict[str, Any], key: str, amount: Decimal = Decimal("1")
) -> dict[str, Any]:
    conn.execute(text("SELECT pg_advisory_xact_lock(410053)"))
    budget = get(conn, "budgets", budget_id, lock=True)
    previous = rows(conn, "SELECT * FROM app.budget_reservations WHERE call_key=:key", {"key": key})
    if previous:
        if (
            previous[0]["budget_id"] != budget_id
            or previous[0]["job_id"] != job["id"]
            or previous[0]["maximum_usd"] != amount
        ):
            raise BusinessError("RESERVATION_CONFLICT")
        return previous[0]
    now = clock(conn)
    if (
        amount <= 0
        or budget["status"] != "active"
        or not budget["period_start"] <= now < budget["period_end"]
        or budget["spent_usd"] + budget["reserved_usd"] + amount > budget["limit_usd"]
    ):
        raise BusinessError("BUDGET_EXHAUSTED")
    budget = update(conn, "budgets", budget, reserved_usd=budget["reserved_usd"] + amount)
    reservation = insert(
        conn,
        "budget_reservations",
        {
            "budget_id": budget_id,
            "job_id": job["id"],
            "call_key": key,
            "maximum_usd": amount,
            "state": "reserved",
        },
    )
    if budget["reserved_usd"] + budget["spent_usd"] >= budget["limit_usd"]:
        emit(conn, "budget.exhausted", budget, "budget")
    elif budget["reserved_usd"] + budget["spent_usd"] >= budget["limit_usd"] * Decimal(".8"):
        emit(conn, "budget.warning", budget, "budget")
    if not conn.execute(text("SELECT app.runtime_company_cap_ok()")).scalar_one():
        raise BusinessError("COMPANY_BUDGET_EXHAUSTED")
    return reservation


def settle(
    conn: Connection,
    reservation_id: UUID,
    actual: Decimal,
    *,
    provider: str = "fake_local",
    task_type: str = "synthetic",
    rate_version: str = "phase-4-fake-v1",
    cost_status: str = "confirmed",
) -> None:
    # Lock budget before reservation for both reservation and settlement paths.
    seen = get(conn, "budget_reservations", reservation_id)
    cap_ids = [seen["budget_id"]] + [
        r["budget_id"]
        for r in rows(
            conn,
            "SELECT budget_id FROM app.reservation_budget_caps WHERE reservation_id=:id",
            {"id": reservation_id},
        )
    ]
    budgets = rows(
        conn,
        "SELECT * FROM app.budgets WHERE id=ANY(:ids) ORDER BY id FOR UPDATE",
        {"ids": cap_ids},
    )
    reservation = get(conn, "budget_reservations", reservation_id, lock=True)
    if reservation["state"] in {"settled", "released"}:
        if reservation["actual_usd"] != actual:
            raise BusinessError("SETTLEMENT_CONFLICT")
        return
    if not Decimal(0) <= actual <= reservation["maximum_usd"]:
        raise BusinessError("INVALID_USAGE")
    for budget in budgets:
        update(
            conn,
            "budgets",
            budget,
            reserved_usd=budget["reserved_usd"] - reservation["maximum_usd"],
            spent_usd=budget["spent_usd"] + actual,
        )
    update(
        conn,
        "budget_reservations",
        reservation,
        state="settled" if actual else "released",
        actual_usd=actual,
    )
    insert(
        conn,
        "usage_entries",
        {
            "reservation_id": reservation_id,
            "provider": provider,
            "task_type": task_type,
            "requests": 1,
            "units": actual,
            "workflow_executions": 1,
            "cost_usd": actual,
            "cost_status": cost_status,
            "rate_version": rate_version,
        },
    )


def prepare_effect(conn: Connection, claimed: dict[str, Any]) -> dict[str, Any]:
    from company_os.application import authority

    job = fenced(conn, claimed)
    bindings = rows(
        conn,
        "SELECT manifest_id FROM app.authority_bindings WHERE input_id=:id",
        {"id": job["input_ref"]},
    )
    if bindings:
        reason = authority.validate(conn, bindings[0]["manifest_id"])
        if reason:
            raise BusinessError(reason, 423)
    if job["replay_namespace"]:
        raise BusinessError("REPLAY_EFFECT_DISABLED")
    item = get(conn, "runtime_inputs", job["input_ref"])
    if not item["scenario"].startswith("effect_"):
        raise BusinessError("UNSUPPORTED_ACTION")
    if job["input_hash"] != item["content_hash"]:
        raise BusinessError("EFFECT_KEY_CONFLICT")
    endpoint = rows(
        conn, "SELECT * FROM app.fake_endpoints WHERE enabled ORDER BY id LIMIT 1 FOR SHARE"
    )
    if not endpoint:
        raise BusinessError("FAKE_ENDPOINT_DISABLED")
    # A missing effect cannot be row-locked. Serialize its scoped identity before
    # the lookup and hold through commit/rollback, including resource reservation.
    conn.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended(app.current_workspace_id()::text||':'||CAST(:connection AS text)||':'||:key,53))"
        ),
        {"connection": endpoint[0]["id"], "key": item["logical_key"]},
    )
    existing = rows(
        conn,
        "SELECT * FROM app.external_effects WHERE connection_id=:c AND effect_key=:key FOR UPDATE",
        {"c": endpoint[0]["id"], "key": item["logical_key"]},
    )
    if existing:
        effect = existing[0]
        if effect["request_hash"] != item["content_hash"]:
            raise BusinessError("EFFECT_KEY_CONFLICT")
        if effect["job_id"] == job["id"]:
            update(conn, "jobs", job, effect_id=effect["id"])
        else:
            update(conn, "jobs", job, coalesced_effect_id=effect["id"])
        return effect
    budgets = rows(
        conn,
        "SELECT id FROM app.budgets WHERE category='synthetic' ORDER BY period_start DESC LIMIT 1",
    )
    if not budgets:
        raise BusinessError("BUDGET_UNCONFIGURED")
    reservation = reserve_effect_caps(conn, job, "effect:" + item["logical_key"])
    quota = reserve_quota(conn, endpoint[0]["id"])
    effect = insert(
        conn,
        "external_effects",
        {
            "connection_id": endpoint[0]["id"],
            "action_type": "fake.execute",
            "target_id": item["id"],
            "effect_key": item["logical_key"],
            "request_hash": item["content_hash"],
            "request_ref": item["id"],
            "authority_version": "phase-4-fake-v1",
            "quota_bucket_id": quota["id"],
            "expected_version": 1,
            "state": "prepared",
            "job_id": job["id"],
            "reservation_id": reservation["id"],
        },
    )
    authority.reserve(conn, effect)
    update(conn, "jobs", job, effect_id=effect["id"], budget_reservation_id=reservation["id"])
    audit(conn, "effect.prepared", effect["id"], job["correlation_id"])
    return effect


def begin_dispatch(conn: Connection, claimed: dict[str, Any], effect_id: UUID) -> dict[str, Any]:
    from company_os.application import authority

    job = fenced(conn, claimed)
    effect = get(conn, "external_effects", effect_id, lock=True)
    if effect["job_id"] != job["id"] or job["effect_id"] != effect_id or job["replay_namespace"]:
        raise BusinessError("EFFECT_AUTHORITY")
    if (
        job["cancel_requested_at"]
        or job["deadline_at"] <= clock(conn)
        or not get(conn, "fake_endpoints", effect["connection_id"])["enabled"]
    ):
        raise BusinessError("DISPATCH_CANCELLED")
    if effect["state"] != "prepared":
        raise BusinessError("EFFECT_ALREADY_DISPATCHED")
    binding = rows(
        conn,
        "SELECT manifest_id FROM app.authority_bindings WHERE input_id=:id",
        {"id": effect["request_ref"]},
    )
    if binding:
        reason = authority.validate(conn, binding[0]["manifest_id"])
        if reason:
            raise BusinessError(reason, 423)
        authority.validate_budget(conn, effect)
        authority.record_runtime_decision(conn, job, None)
    effect = update(
        conn,
        "external_effects",
        effect,
        state="dispatching",
        dispatch_started_at=clock(conn),
        lease_fence=job["fence"],
        reconcile_after=clock(conn) + timedelta(seconds=60),
    )
    audit(conn, "effect.dispatching", effect_id, job["correlation_id"])
    return effect


def uncertain(conn: Connection, effect: dict[str, Any]) -> dict[str, Any]:
    if effect["state"] == "dispatching":
        effect = update(
            conn, "external_effects", effect, state="uncertain", reconcile_after=clock(conn)
        )
        reservation = get(conn, "budget_reservations", effect["reservation_id"], lock=True)
        update(conn, "budget_reservations", reservation, state="uncertain")
        emit(conn, "effect.uncertain", effect, "effect")
    item = get(conn, "runtime_inputs", effect["request_ref"])
    enqueue(
        conn,
        item,
        "reconcile:" + str(effect["id"]),
        effect["id"],
        priority="safety",
        effect=effect["id"],
    )
    incident(conn, "uncertain_effect", effect)
    return effect


def resolve_effect(
    conn: Connection, effect: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    if effect["state"] in {"confirmed", "rejected"}:
        return effect
    if effect["state"] not in {"dispatching", "uncertain"}:
        raise BusinessError("INVALID_EFFECT_TRANSITION")
    effect = update(
        conn,
        "external_effects",
        effect,
        state=receipt["outcome"],
        provider_request_id=receipt["provider_request_id"],
        receipt_hash=receipt["receipt_hash"],
        reconcile_after=None,
    )
    settle(
        conn,
        effect["reservation_id"],
        Decimal(1) if receipt["outcome"] == "confirmed" else Decimal(0),
    )
    release_quota(conn, effect, consumed=receipt["outcome"] == "confirmed")
    emit(conn, "effect.reconciled", effect, "effect")
    for inc in rows(
        conn,
        "SELECT * FROM app.incidents WHERE fingerprint=:key AND state<>'resolved' FOR UPDATE",
        {"key": "uncertain_effect:" + str(effect["id"])},
    ):
        update(conn, "incidents", inc, state="resolved", resolved_at=clock(conn))
        for attention in rows(
            conn,
            "SELECT * FROM app.runtime_attention WHERE incident_id=:id FOR UPDATE",
            {"id": inc["id"]},
        ):
            update(conn, "runtime_attention", attention, state="resolved")
    return effect


def cancel(conn: Connection, identifier: UUID, version: int, reason: str) -> dict[str, Any]:
    job = get(conn, "jobs", identifier, lock=True)
    if job["record_version"] != version:
        raise BusinessError("VERSION_CONFLICT")
    if job["state"] in TERMINAL:
        raise BusinessError("INVALID_TRANSITION")
    active = job["state"] in {"leased", "running", "cancel_requested"}
    job = update(
        conn,
        "jobs",
        job,
        state="cancel_requested" if active else "cancelled",
        cancel_requested_at=clock(conn),
    )
    if job["effect_id"]:
        effect = get(conn, "external_effects", job["effect_id"], lock=True)
        if effect["job_id"] == job["id"] and effect["state"] == "prepared":
            update(conn, "external_effects", effect, state="cancelled")
            settle(conn, effect["reservation_id"], Decimal(0))
            release_quota(conn, effect, consumed=False)
        elif effect["job_id"] == job["id"] and effect["state"] in {"dispatching", "uncertain"}:
            uncertain(conn, effect)
    emit(conn, "job.cancelled", job, "job")
    refresh_workflow(conn, job)
    audit(conn, "job.cancel", identifier, job["correlation_id"], outcome=digest(reason))
    return job


def retry(
    conn: Connection, identifier: UUID, version: int, reason: str, cause_changed: bool
) -> dict[str, Any]:
    job = get(conn, "jobs", identifier, lock=True)
    if job["record_version"] != version or job["state"] != "dead_letter":
        raise BusinessError("INVALID_TRANSITION")
    if not cause_changed or job["last_error_code"] not in {"TRANSIENT", "LEASE_EXPIRED"}:
        raise BusinessError("CAUSE_UNCHANGED")
    if job["effect_id"]:
        raise BusinessError("UNCERTAIN_EFFECT")
    item = get(conn, "runtime_inputs", job["input_ref"])
    if item["scenario"] == "exhausted":
        raise BusinessError("CAUSE_UNCHANGED")
    result = enqueue(
        conn,
        item,
        "recovery:" + str(job["id"]),
        job["correlation_id"],
        origin=job["origin_event_id"],
    )
    if result["recovery_of_id"] is None:
        result = update(conn, "jobs", result, recovery_of_id=job["id"])
    audit(conn, "job.retry", result["id"], job["correlation_id"], outcome=digest(reason))
    return result


def reserve_quota(conn: Connection, endpoint: UUID) -> dict[str, Any]:
    found = rows(
        conn,
        "SELECT * FROM app.quota_buckets WHERE connection_id=:id AND window_start<=now() AND window_end>now() ORDER BY window_start DESC LIMIT 1 FOR UPDATE",
        {"id": endpoint},
    )
    if (
        not found
        or found[0]["reserved_units"] + found[0]["consumed_units"]
        >= found[0]["limit_units"] - found[0]["safety_reserve"]
    ):
        raise BusinessError("QUOTA_EXHAUSTED")
    quota = found[0]
    return update(conn, "quota_buckets", quota, reserved_units=quota["reserved_units"] + 1)


def release_quota(conn: Connection, effect: dict[str, Any], *, consumed: bool) -> None:
    quota = get(conn, "quota_buckets", effect["quota_bucket_id"], lock=True)
    update(
        conn,
        "quota_buckets",
        quota,
        reserved_units=quota["reserved_units"] - 1,
        consumed_units=quota["consumed_units"] + int(consumed),
    )


def complete_callback(
    conn: Connection, job_id: UUID, fence: int, result_ref: UUID
) -> dict[str, Any]:
    job = get(conn, "jobs", job_id, lock=True)
    if job["fence"] != fence or job["input_ref"] != result_ref or job["effect_id"] is not None:
        raise BusinessError("BAD_FENCE_OR_RESULT")
    previous = rows(
        conn,
        "SELECT * FROM app.runtime_completions WHERE job_id=:id AND fence=:fence",
        {"id": job_id, "fence": fence},
    )
    if previous:
        return previous[0]
    if (
        job["state"] != "waiting_external"
        or job["cancel_requested_at"]
        or job["last_error_code"] is not None
        or get(conn, "runtime_inputs", job["input_ref"])["scenario"] != "wait"
    ):
        raise BusinessError("INVALID_TRANSITION")
    receipt = insert(
        conn, "runtime_completions", {"job_id": job_id, "fence": fence, "result_ref": result_ref}
    )
    update(conn, "jobs", job, state="queued")
    audit(conn, "job.callback_received", job_id, job["correlation_id"], actor_type="service")
    return receipt


def snooze(
    conn: Connection, identifier: UUID, version: int, until: Any, reason: str
) -> dict[str, Any]:
    item = get(conn, "runtime_attention", identifier, lock=True)
    inc = get(conn, "incidents", item["incident_id"])
    if inc["severity"] != "P2":
        raise BusinessError("CRITICAL_ITEM_CANNOT_HIDE")
    if item["record_version"] != version or item["state"] == "resolved":
        raise BusinessError("VERSION_CONFLICT")
    if until.tzinfo is None or not clock(conn) < until <= clock(conn) + timedelta(days=1):
        raise BusinessError("INVALID_SNOOZE")
    item = update(
        conn, "runtime_attention", item, state="snoozed", snooze_until=until, reason=reason
    )
    audit(conn, "attention.snooze", identifier, identifier)
    return item


def idempotent(
    conn: Connection,
    actor: UUID,
    key: str,
    action: str,
    payload: dict[str, Any],
    table: str,
    operation: Any,
) -> dict[str, Any]:
    """Reuse the existing API command receipt contract; worker has no grant here."""
    from company_os.persistence.business import insert as insert_receipt

    token = str(actor) + ":" + action + ":" + key
    conn.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended(app.current_workspace_id()::text||:key,52))"
        ),
        {"key": token},
    )
    expected = digest(payload)
    receipt = rows(
        conn,
        "SELECT * FROM app.command_receipts WHERE actor_id=:actor AND command_type=:action AND idempotency_key=:key",
        {"actor": actor, "action": action, "key": key},
    )
    if receipt:
        if receipt[0]["request_hash"] != expected:
            raise BusinessError("IDEMPOTENCY_CONFLICT")
        return get(conn, table, receipt[0]["result_id"])
    result = operation()
    insert_receipt(
        conn,
        "command_receipts",
        {
            "actor_id": actor,
            "command_type": action,
            "idempotency_key": key,
            "request_hash": expected,
            "result_id": result["id"],
            "result_version": result.get("record_version"),
        },
    )
    return result


def reserve_effect_caps(conn: Connection, job: dict[str, Any], call_key: str) -> dict[str, Any]:
    conn.execute(text("SELECT pg_advisory_xact_lock(410053)"))
    budgets = rows(
        conn,
        "SELECT * FROM app.budgets WHERE category IN ('synthetic','synthetic_day','synthetic_month') AND period_start<=now() AND period_end>now() ORDER BY id FOR UPDATE",
    )
    if not {"synthetic_day", "synthetic_month"} <= {b["category"] for b in budgets}:
        raise BusinessError("BUDGET_UNCONFIGURED")
    for budget in budgets:
        if (
            budget["status"] != "active"
            or budget["spent_usd"] + budget["reserved_usd"] + 1 > budget["limit_usd"]
        ):
            raise BusinessError("BUDGET_EXHAUSTED")
    reservation = reserve(conn, budgets[0]["id"], job, call_key)
    for budget in budgets[1:]:
        update(conn, "budgets", budget, reserved_usd=budget["reserved_usd"] + 1)
        insert(
            conn,
            "reservation_budget_caps",
            {"reservation_id": reservation["id"], "budget_id": budget["id"]},
        )
    return reservation


def event_payload(aggregate: str, item: dict[str, Any]) -> dict[str, Any]:
    if aggregate == "runtime_input":
        return {"input_id": str(item["id"])}
    if aggregate == "job":
        return {
            "job_id": str(item["id"]),
            "attempt_no": item["attempt_count"],
            "error_code": item["last_error_code"],
            "next_attempt_at": item["available_at"]
            .astimezone(UTC)
            .strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            if item["state"] == "retry_wait"
            else None,
        }
    if aggregate == "effect":
        return {
            "effect_id": str(item["id"]),
            "provider_request_id": item["provider_request_id"],
            "resolution": item["state"],
        }
    if aggregate == "budget":
        return {
            "budget_id": str(item["id"]),
            "spent": format(item["spent_usd"], ".8f"),
            "reserved": format(item["reserved_usd"], ".8f"),
            "limit": format(item["limit_usd"], ".8f"),
            "currency": "USD",
        }
    if aggregate == "incident":
        return {
            "incident_id": str(item["id"]),
            "severity": item["severity"],
            "affected_scopes": [str(item["workspace_id"])],
        }
    raise BusinessError("UNKNOWN_EVENT_SCHEMA")
