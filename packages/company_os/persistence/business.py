"""Closed internal table helpers and synchronous provenance queries."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from company_os.business_contracts import FactValue
from company_os.persistence.database import rows

TABLES = frozenset(
    {
        "resources",
        "documents",
        "document_versions",
        "document_grants",
        "data_sources",
        "accounts",
        "people",
        "evidence",
        "evidence_retractions",
        "employments",
        "contact_points",
        "signals",
        "icps",
        "icp_versions",
        "icp_excluded_accounts",
        "offers",
        "offer_versions",
        "offer_proofs",
        "leads",
        "scores",
        "score_components",
        "score_evidence",
        "score_input_evidence",
        "score_signals",
        "decisions",
        "decision_evidence",
        "identity_conflicts",
        "identity_conflict_evidence",
        "identity_merges",
        "identity_merge_reversals",
        "permission_assessments",
        "suppressions",
        "knowledge_items",
        "knowledge_chunks",
        "command_receipts",
    }
)
MUTABLE = frozenset(
    {
        "resources",
        "documents",
        "document_grants",
        "data_sources",
        "accounts",
        "people",
        "employments",
        "contact_points",
        "signals",
        "icps",
        "offers",
        "leads",
        "knowledge_items",
    }
)
JSON_FIELDS = frozenset({"criteria", "exclusions", "score_policy", "proposed_changes"})
RESOURCE_TYPES = {
    "accounts": "account",
    "people": "person",
    "leads": "lead",
    "documents": "document",
}


class BusinessError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


def get(conn: Connection, table: str, identifier: UUID, *, lock: bool = False) -> dict[str, Any]:
    if table not in TABLES:
        raise ValueError("Unknown table")
    found = rows(
        conn,
        f"SELECT * FROM app.{table} WHERE id=:id" + (" FOR UPDATE" if lock else ""),
        {"id": identifier},
    )
    if not found:
        raise BusinessError("NOT_FOUND", 404)
    return found[0]


def insert(
    conn: Connection, table: str, values: dict[str, Any], *, identifier: UUID | None = None
) -> dict[str, Any]:
    if table not in TABLES or any(not key.replace("_", "").isalnum() for key in values):
        raise ValueError("Unknown internal table/column")
    context = rows(conn, "SELECT app.current_workspace_id() AS w, app.current_principal_id() AS p")[
        0
    ]
    data = {
        "id": identifier or uuid4(),
        "workspace_id": context["w"],
        "created_by": context["p"],
        **values,
    }
    if table in MUTABLE:
        data["updated_by"] = context["p"]
    if table in RESOURCE_TYPES:
        insert(conn, "resources", {"resource_type": RESOURCE_TYPES[table]}, identifier=data["id"])
    columns = list(data)
    placeholders = [
        f"CAST(:{column} AS jsonb)"
        if column in JSON_FIELDS and isinstance(data[column], dict)
        else f":{column}"
        for column in columns
    ]
    params = {
        key: json.dumps(value) if key in JSON_FIELDS and isinstance(value, dict) else value
        for key, value in data.items()
    }
    return rows(
        conn,
        f"INSERT INTO app.{table} ({','.join(columns)}) VALUES ({','.join(placeholders)}) RETURNING *",
        params,
    )[0]


def update(
    conn: Connection, table: str, identifier: UUID, version: int, changes: dict[str, Any]
) -> dict[str, Any]:
    if table not in MUTABLE or any(not key.replace("_", "").isalnum() for key in changes):
        raise ValueError("Immutable or unknown target")
    params = {**changes, "target": identifier, "expected": version}
    assignments = [f"{key}=:{key}" for key in changes]
    found = rows(
        conn,
        f"UPDATE app.{table} SET {','.join(assignments)},record_version=record_version+1,updated_by=app.current_principal_id() WHERE id=:target AND record_version=:expected RETURNING *",
        params,
    )
    if not found:
        get(conn, table, identifier)
        raise BusinessError("VERSION_CONFLICT")
    return found[0]


def document_allowed(conn: Connection, document_id: UUID) -> bool:
    return bool(
        conn.execute(
            text(
                """SELECT EXISTS(SELECT 1 FROM app.documents d JOIN app.document_grants g ON g.workspace_id=d.workspace_id AND g.document_id=d.id WHERE d.id=:id AND d.state='active' AND g.principal_id=app.current_principal_id() AND (g.expires_at IS NULL OR g.expires_at>now()))"""
            ),
            {"id": document_id},
        ).scalar_one()
    )


def source_allowed(
    conn: Connection, source: dict[str, Any], purpose: str, field: str | None = None
) -> bool:
    now = datetime.now(UTC)
    if (
        source["rights_status"] != "approved"
        or (source["expires_at"] is not None and source["expires_at"] <= now)
        or purpose not in source["permitted_purposes"]
    ):
        return False
    if field is not None and field not in source["allowed_fields"]:
        return False
    version = get(conn, "document_versions", source["rights_document_version_id"])
    document = get(conn, "documents", version["document_id"])
    return document["state"] == "active"


def require_source(conn: Connection, source_id: UUID, fields: list[str]) -> dict[str, Any]:
    source = get(conn, "data_sources", source_id)
    if not all(source_allowed(conn, source, "research", field) for field in fields):
        raise BusinessError("SOURCE_NOT_ALLOWED", 423)
    return source


def invalid_reasons(conn: Connection, evidence: dict[str, Any]) -> list[str]:
    reasons = []
    now = datetime.now(UTC)
    if evidence["expires_at"] <= now:
        reasons.append("evidence_expired")
    if evidence["observed_at"] > now:
        reasons.append("future_observation")
    if evidence["entity_match"] != "confirmed":
        reasons.append("entity_match_unconfirmed")
    if evidence["fact_kind"] == "inferred":
        reasons.append("inference_is_not_observation")
    if evidence["fact_type"] == "unknown":
        reasons.append("unknown_value")
    source = get(conn, "data_sources", evidence["source_id"])
    if not source_allowed(conn, source, "research", evidence["fact_key"]):
        reasons.append("source_not_allowed")
    if (
        source["retention_days"]
        and (now - evidence["observed_at"]).total_seconds() >= source["retention_days"] * 86400
    ):
        reasons.append("source_retention_expired")
    if rows(
        conn,
        "SELECT id FROM app.evidence_retractions WHERE evidence_id=:id",
        {"id": evidence["id"]},
    ):
        reasons.append("retracted")
    if rows(conn, "SELECT id FROM app.evidence WHERE supersedes_id=:id", {"id": evidence["id"]}):
        reasons.append("superseded")
    if evidence["document_version_id"]:
        version = get(conn, "document_versions", evidence["document_version_id"])
        if not document_allowed(conn, version["document_id"]):
            reasons.append("document_unavailable")
    return reasons


def fact_value(evidence: dict[str, Any]) -> FactValue:
    kind = evidence["fact_type"]
    value = None if kind == "unknown" else evidence[f"{kind}_value"]
    if kind in {"decimal", "date"}:
        value = str(value)
    return FactValue(type=kind, value=value, unit=evidence["unit"])
