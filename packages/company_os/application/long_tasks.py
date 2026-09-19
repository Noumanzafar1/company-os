"""Synthetic task configuration and evidence through existing command boundaries."""

import math
from typing import Any
from uuid import UUID

from sqlalchemy import Connection

from company_os.application import runtime as command
from company_os.long_contracts import LongSpec, LongSubmission
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows
from company_os.persistence.runtime import get, insert, update
from company_os.runtime_contracts import SyntheticInput

EFFECT_SCENARIOS = {
    "fake_remote_success": "effect_success",
    "fake_remote_reject": "effect_rejected",
    "fake_remote_accept_then_hang": "effect_lost",
}


def bind(conn: Connection, input_id: UUID, spec: LongSpec) -> dict[str, Any]:
    """Only scheduling/fault behavior; cannot alter the approved effect payload."""
    item = get(conn, "runtime_inputs", input_id)
    expected = EFFECT_SCENARIOS.get(spec.handler, "success")
    if item["scenario"] != expected:
        raise BusinessError("LONG_SCENARIO_MISMATCH")
    prior = rows(conn, "SELECT * FROM app.long_task_specs WHERE input_id=:id", {"id": input_id})
    content_hash = command.digest(spec.model_dump())
    if prior:
        if prior[0]["spec_hash"] != content_hash:
            raise BusinessError("IDEMPOTENCY_CONFLICT")
        return prior[0]
    jobs = rows(
        conn, "SELECT * FROM app.jobs WHERE input_ref=:id ORDER BY id FOR UPDATE", {"id": input_id}
    )
    if any(job["attempt_count"] for job in jobs):
        raise BusinessError("LONG_ALREADY_ADMITTED")
    for job in jobs:
        update(conn, "jobs", job, timeout_seconds=math.ceil(spec.hard_timeout_seconds))
    return insert(
        conn,
        "long_task_specs",
        {"input_id": input_id, "spec": spec.model_dump(), "spec_hash": content_hash},
    )


def submit(conn: Connection, request: LongSubmission, correlation: UUID) -> dict[str, Any]:
    item = command.submit(
        conn,
        SyntheticInput(
            scenario=EFFECT_SCENARIOS.get(request.spec.handler, "success"),  # type: ignore[arg-type]
            logical_key="long:" + request.logical_key,
        ),
        correlation,
    )
    bind(conn, item["id"], request.spec)
    return item
