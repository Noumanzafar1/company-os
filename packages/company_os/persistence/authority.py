"""Private authority storage; all callers supply verified transaction context."""

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection

from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows

MUTABLE = {"policies", "approval_requests", "authority_test_targets"}
TABLES = MUTABLE | {
    "authority_command_receipts",
    "policy_versions",
    "approval_targets",
    "approval_decisions",
    "approval_manifests",
    "authority_freezes",
    "policy_decisions",
    "authority_bindings",
    "approval_uses",
    "approval_use_results",
}


def get(conn: Connection, table: str, identifier: UUID, *, lock: bool = False) -> dict[str, Any]:
    if table not in TABLES:
        raise ValueError("Unknown authority table")
    result = rows(
        conn,
        f"SELECT * FROM app.{table} WHERE id=:id" + (" FOR UPDATE" if lock else ""),
        {"id": identifier},
    )
    if not result:
        raise BusinessError("NOT_FOUND", 404)
    return result[0]


def insert(conn: Connection, table: str, data: dict[str, Any]) -> dict[str, Any]:
    if table not in TABLES or any(not k.replace("_", "").isalnum() for k in data):
        raise ValueError("Unknown authority field")
    scope = rows(conn, "SELECT app.current_workspace_id() w,app.current_principal_id() p")[0]
    values = {"id": uuid4(), "workspace_id": scope["w"], "created_by": scope["p"], **data}
    if table in MUTABLE:
        values["updated_by"] = scope["p"]
    expressions = []
    for k, v in values.items():
        if isinstance(v, dict):
            values[k] = json.dumps(v, sort_keys=True, separators=(",", ":"), default=str)
            expressions.append(f"CAST(:{k} AS jsonb)")
        else:
            expressions.append(f":{k}")
    return rows(
        conn,
        f"INSERT INTO app.{table}({','.join(values)}) VALUES({','.join(expressions)}) RETURNING *",
        values,
    )[0]


def update(conn: Connection, table: str, item: dict[str, Any], **values: Any) -> dict[str, Any]:
    if table not in MUTABLE or any(not k.replace("_", "").isalnum() for k in values):
        raise ValueError("Unknown authority update")
    result = rows(
        conn,
        f"UPDATE app.{table} SET {','.join(k + '=:' + k for k in values)},record_version=record_version+1,updated_by=app.current_principal_id() WHERE id=:id AND record_version=:version RETURNING *",
        {**values, "id": item["id"], "version": item["record_version"]},
    )
    if not result:
        raise BusinessError("VERSION_CONFLICT")
    return result[0]
