"""Private, allowlisted SQL helpers for the Phase 4 application boundary."""

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows

IMMUTABLE = {
    "runtime_completions",
    "reservation_budget_caps",
    "runtime_inputs",
    "events",
    "consumer_receipts",
    "job_attempts",
    "job_dependencies",
    "schedule_slots",
    "usage_entries",
    "fake_receipts",
    "incident_evidence",
}
TABLES = IMMUTABLE | {
    "fake_endpoints",
    "workflow_runs",
    "outbox",
    "jobs",
    "schedules",
    "external_effects",
    "budgets",
    "budget_reservations",
    "quota_buckets",
    "webhook_inbox",
    "fake_observations",
    "runtime_heartbeats",
    "incidents",
    "runtime_attention",
}


def get(conn: Connection, table: str, identifier: UUID, *, lock: bool = False) -> dict[str, Any]:
    if table not in TABLES:
        raise ValueError("Unknown runtime table")
    found = rows(
        conn,
        f"SELECT * FROM app.{table} WHERE id=:id" + (" FOR UPDATE" if lock else ""),
        {"id": identifier},
    )
    if not found:
        raise BusinessError("NOT_FOUND", 404)
    return found[0]


def insert(conn: Connection, table: str, data: dict[str, Any]) -> dict[str, Any]:
    if table not in TABLES or any(not k.replace("_", "").isalnum() for k in data):
        raise ValueError("Unknown runtime table/column")
    context = rows(conn, "SELECT app.current_workspace_id() AS w,app.current_principal_id() AS p")[
        0
    ]
    values = {"id": uuid4(), "workspace_id": context["w"], "created_by": context["p"], **data}
    if table not in IMMUTABLE:
        values["updated_by"] = context["p"]
    expressions = []
    for k in values:
        if isinstance(values[k], dict):
            values[k] = json.dumps(values[k], sort_keys=True, separators=(",", ":"), default=str)
            expressions.append(f"CAST(:{k} AS jsonb)")
        else:
            expressions.append(f":{k}")
    return rows(
        conn,
        f"INSERT INTO app.{table}({','.join(values)}) VALUES({','.join(expressions)}) RETURNING *",
        values,
    )[0]


def update(conn: Connection, table: str, item: dict[str, Any], **values: Any) -> dict[str, Any]:
    if table not in TABLES - IMMUTABLE or any(not k.replace("_", "").isalnum() for k in values):
        raise ValueError("Immutable/unknown runtime table")
    found = rows(
        conn,
        f"UPDATE app.{table} SET {','.join(k + '=:' + k for k in values)},record_version=record_version+1,updated_by=app.current_principal_id() WHERE id=:id AND record_version=:version RETURNING *",
        {**values, "id": item["id"], "version": item["record_version"]},
    )
    if not found:
        raise BusinessError("VERSION_CONFLICT")
    return found[0]


def clock(conn: Connection) -> Any:
    return conn.execute(text("SELECT clock_timestamp()")).scalar_one()
