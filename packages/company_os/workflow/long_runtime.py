"""Child execution joins existing fenced commands and fake effect reconciliation."""

import threading
import time
from dataclasses import asdict
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from company_os.adapters import fake_effects
from company_os.application import authority
from company_os.application import runtime as command
from company_os.long_contracts import ExecutionEnvelope, LongSpec
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows, transaction
from company_os.persistence.runtime import clock, get, insert, update
from company_os.workflow.fake_network import FakeNetwork
from company_os.workflow.isolation import execute


def run_long(
    engine: Engine,
    scope: tuple[UUID, UUID, int],
    job: dict[str, Any],
    spec_row: dict[str, Any],
    shutdown: threading.Event | None = None,
) -> bool:
    spec = LongSpec.model_validate(spec_row["spec"])
    if command.digest(spec.model_dump()) != spec_row["spec_hash"]:
        raise BusinessError("LONG_INPUT_HASH")
    if spec.hard_timeout_seconds > job["timeout_seconds"]:
        raise BusinessError("LONG_TIMEOUT_MISMATCH")
    execution_id = uuid4()
    effect = None
    manifest = None
    with transaction(engine, *scope) as conn:
        current = command.fenced(conn, job)
        item = get(conn, "runtime_inputs", job["input_ref"])
        if item["content_hash"] != job["input_hash"]:
            command.failed(conn, job, "LONG_INPUT_HASH")
            return True
        if current["cancel_requested_at"]:
            command.finish(conn, current, "cancelled")
            return True
        attempt = rows(
            conn,
            "SELECT id FROM app.job_attempts WHERE job_id=:id AND fence=:f AND phase='start'",
            {"id": job["id"], "f": job["fence"]},
        )[0]
        bindings = rows(
            conn,
            "SELECT manifest_id FROM app.authority_bindings WHERE input_id=:id",
            {"id": item["id"]},
        )
        manifest = bindings[0]["manifest_id"] if bindings else None
        if manifest:
            denial = authority.validate(conn, manifest)
            if denial:
                authority.record_runtime_decision(conn, job, denial)
                command.failed(conn, job, denial)
                return True
        execution = insert(
            conn,
            "long_executions",
            {
                "id": execution_id,
                "job_id": job["id"],
                "attempt_id": attempt["id"],
                "fence": job["fence"],
                "input_hash": command.digest(
                    {"input": job["input_hash"], "spec": spec_row["spec_hash"]}
                ),
                "state": "active",
            },
        )
        command.audit(conn, "job.long_started", job["id"], execution_id)
    try:
        if item["scenario"].startswith("effect_"):
            with transaction(engine, *scope) as conn:
                effect = command.prepare_effect(conn, job)
                if effect["job_id"] != job["id"]:
                    state, code = command.coalesced_result(effect)
                    command.finish(conn, job, state, code=code)
                    close_execution(conn, execution, "COALESCED", {})
                    return True
                if effect["state"] != "prepared":
                    command.finish(
                        conn,
                        job,
                        "succeeded" if effect["state"] == "confirmed" else "waiting_external",
                        code="EFFECT_HELD",
                    )
                    close_execution(conn, execution, "EFFECT_HELD", {})
                    return True
            with transaction(engine, *scope) as conn:
                effect = command.begin_dispatch(conn, job, effect["id"])
    except BusinessError as error:
        with transaction(engine, *scope) as conn:
            command.fenced(conn, job)
            authority.record_runtime_decision(conn, job, error.code)
            command.failed(conn, job, error.code)
            close_execution(conn, execution, error.code, {})
        return True

    acceptance_deadline = time.monotonic() + spec.hard_timeout_seconds

    def accept() -> dict[str, Any]:
        if effect is None:
            return {"outcome": "confirmed", "receipt": None}
        # The synthetic service's acceptance transaction is independent of the
        # waiting child. Same Phase 5 final checks as the offline adapter.
        with transaction(engine, *scope) as conn:
            conn.execute(text("SET LOCAL statement_timeout='3s'"))
            current = command.fenced(conn, job)
            if (
                current["cancel_requested_at"]
                or current["deadline_at"] <= clock(conn)
                or (shutdown and shutdown.is_set())
            ):
                raise BusinessError("DISPATCH_CANCELLED")
            if not get(conn, "fake_endpoints", effect["connection_id"])["enabled"]:
                raise BusinessError("DISPATCH_CANCELLED")
            if manifest:
                denial = authority.validate(conn, manifest)
                if denial:
                    raise BusinessError(denial)
                authority.validate_budget(conn, effect)
                authority.final_temporal_check(conn, manifest)
            if time.monotonic() >= acceptance_deadline:
                raise BusinessError("DISPATCH_CANCELLED")
            receipt = fake_effects.accept(conn, effect, item["scenario"])
        return {"outcome": receipt["outcome"], "receipt": str(receipt["id"])}

    stopped = threading.Event()
    invalidation: list[str] = []

    def watch() -> None:
        while not stopped.is_set():
            try:
                with transaction(engine, *scope) as conn:
                    conn.execute(text("SET LOCAL statement_timeout='2s'"))
                    current = command.fenced(conn, job)
                    if current["cancel_requested_at"]:
                        invalidation.append("CANCELLED")
                    elif current["deadline_at"] <= clock(conn):
                        invalidation.append("HARD_TIMEOUT")
            except (BusinessError, SQLAlchemyError):
                invalidation.append("LEASE_LOST")
            if invalidation:
                return
            stopped.wait(0.1)

    network = None
    watcher = threading.Thread(target=watch, daemon=True, name="execution-fence-watch")
    watcher.start()
    events: list[dict[str, Any]] = []

    def observe(name: str, pid: int) -> None:
        events.append({"event": name, "pid": pid})
        if name == "child_started":
            with transaction(engine, *scope) as conn:
                conn.execute(text("SET LOCAL statement_timeout='2s'"))
                command.fenced(conn, job)
                command.audit(
                    conn,
                    "job.long_child_started",
                    job["id"],
                    execution_id,
                    outcome="pid:" + str(pid),
                )

    try:
        if (
            spec.handler.startswith(("fake_remote_", "network_"))
            or spec.handler == "transient_read_timeout"
        ):
            network = FakeNetwork(execution_id, spec, accept)
        envelope = ExecutionEnvelope(
            execution_id=execution_id,
            workspace_id=scope[1],
            job_id=job["id"],
            attempt_id=attempt["id"],
            fence=job["fence"],
            input_reference=job["input_ref"],
            input_hash=execution["input_hash"],
            correlation_id=job["correlation_id"],
            trace_id=execution_id,
            authority_reference=manifest,
            reservation_reference=effect["reservation_id"] if effect else None,
            spec=spec,
            loopback_port=network.port if network else None,
        )
        outcome = execute(
            envelope,
            lambda: (
                "SHUTDOWN"
                if shutdown and shutdown.is_set()
                else invalidation[0]
                if invalidation
                else None
            ),
            observe,
        )
    finally:
        stopped.set()
        watcher.join(timeout=6)
        if network:
            network.close()

    details = {k: v for k, v in asdict(outcome).items() if k != "result"}
    details["events"] = events
    try:
        with transaction(engine, *scope) as conn:
            current = command.fenced(conn, job)
            # Re-read immutable inputs and enforce result bindings at admission.
            if current["input_hash"] != item["content_hash"]:
                raise BusinessError("LONG_INPUT_HASH")
            if effect:
                pending = get(conn, "external_effects", effect["id"], lock=True)
                receipt = fake_effects.reconcile(conn, pending)
                # A late receipt is evidence for reconciliation, never success
                # from a timed-out/cancelled child or expired authority.
                denial = authority.validate(conn, manifest) if manifest else None
                if (
                    outcome.code != "RESULT"
                    or current["cancel_requested_at"]
                    or denial
                    or receipt is None
                    or outcome.result is None
                    or str(outcome.result.receipt_reference) != str(receipt["id"])
                ):
                    command.uncertain(conn, pending)
                    command.finish(conn, job, "waiting_external", code="UNCERTAIN_EFFECT")
                else:
                    command.resolve_effect(conn, pending, receipt)
                    command.finish(
                        conn,
                        job,
                        "succeeded" if receipt["outcome"] == "confirmed" else "dead_letter",
                        code=None if receipt["outcome"] == "confirmed" else "REJECTED",
                    )
            elif current["cancel_requested_at"] or outcome.code == "CANCELLED":
                command.finish(conn, job, "cancelled")
            elif manifest and (denial := authority.validate(conn, manifest)):
                authority.record_runtime_decision(conn, job, denial)
                command.failed(conn, job, denial)
            elif outcome.code in {"HARD_TIMEOUT", "SHUTDOWN", "LEASE_LOST"}:
                command.failed(conn, job, outcome.code, transient=True)
            elif outcome.code != "RESULT" or outcome.result is None:
                command.failed(conn, job, outcome.code)
            elif outcome.result.status == "succeeded":
                command.finish(conn, job, "succeeded")
            else:
                command.failed(
                    conn,
                    job,
                    outcome.result.error_code or "CHILD_REJECTED",
                    transient=outcome.result.status == "transient_failure",
                )
            close_execution(conn, execution, outcome.code, details)
    except BusinessError as error:
        if error.code != "STALE_FENCE":
            raise
        with transaction(engine, *scope) as conn:
            close_execution(conn, execution, "STALE_COMPLETION", details)
            command.audit(
                conn, "job.long_stale_completion", job["id"], execution_id, outcome="rejected"
            )
    return True


def close_execution(
    conn: Any, execution: dict[str, Any], code: str, details: dict[str, Any]
) -> None:
    current = get(conn, "long_executions", execution["id"], lock=True)
    if current["state"] == "active":
        update(
            conn,
            "long_executions",
            current,
            state="finished",
            ended_at=clock(conn),
            outcome=code,
            details=details,
        )
        command.audit(conn, "job.long_finished", execution["job_id"], execution["id"], outcome=code)
