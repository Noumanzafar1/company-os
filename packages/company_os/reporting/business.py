"""Authorized, read-only projections. Current validity is derived at query time."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection

from company_os import business_contracts as dto
from company_os.application.scoring import current_input
from company_os.persistence.business import (
    BusinessError,
    document_allowed,
    fact_value,
    get,
    invalid_reasons,
    source_allowed,
)
from company_os.persistence.database import rows

VIEWS = {
    "accounts": dto.AccountView,
    "people": dto.PersonView,
    "leads": dto.LeadView,
    "data_sources": dto.SourceView,
    "evidence": dto.EvidenceView,
    "signals": dto.SignalView,
    "documents": dto.DocumentView,
}


def project(model: Any, data: dict[str, Any]) -> Any:
    return model.model_validate(
        {key: value for key, value in data.items() if key in model.model_fields}
    )


def source(conn: Connection, item: dict[str, Any]) -> dto.SourceView:
    return project(
        dto.SourceView, {**item, "current_use_allowed": source_allowed(conn, item, "research")}
    )


def evidence(conn: Connection, item: dict[str, Any]) -> dto.EvidenceView:
    reasons = invalid_reasons(conn, item)
    return project(
        dto.EvidenceView,
        {
            **item,
            "fact_value": fact_value(item),
            "current_support": not reasons,
            "invalid_reasons": reasons,
        },
    )


def score(conn: Connection, identifier: UUID) -> dto.ScoreView:
    item = get(conn, "scores", identifier)
    components = []
    current = True
    for component in rows(
        conn,
        "SELECT * FROM app.score_components WHERE score_id=:id ORDER BY component",
        {"id": identifier},
    ):
        refs = rows(
            conn,
            "SELECT e.* FROM app.evidence e JOIN app.score_evidence r ON r.workspace_id=e.workspace_id AND r.evidence_id=e.id WHERE r.score_component_id=:id ORDER BY e.id",
            {"id": component["id"]},
        )
        current = current and all(not invalid_reasons(conn, ref) for ref in refs)
        components.append(
            project(
                dto.ScoreComponentView, {**component, "evidence_ids": [ref["id"] for ref in refs]}
            )
        )
    resource = get(conn, "resources", item["subject_id"])
    subject = get(
        conn, "leads" if resource["resource_type"] == "lead" else "accounts", item["subject_id"]
    )
    account = (
        get(conn, "accounts", subject["account_id"])
        if resource["resource_type"] == "lead"
        else subject
    )
    current = (
        current
        and account["status"] == "active"
        and source_allowed(conn, get(conn, "data_sources", account["source_id"]), "research")
    )
    current = current and current_input(conn, item)
    return project(dto.ScoreView, {**item, "current_support": current, "components": components})


def view(conn: Connection, table: str, item: dict[str, Any]) -> Any:
    if table == "accounts":
        unknown = [
            key
            for key in [
                "legal_name",
                "primary_domain",
                "country_code",
                "industry_code",
                "size_min",
                "size_max",
            ]
            if item[key] is None
        ]
        facts = rows(conn, "SELECT * FROM app.evidence WHERE subject_id=:id", {"id": item["id"]})
        scores = rows(
            conn,
            "SELECT id FROM app.scores WHERE subject_id=:id ORDER BY computed_at DESC,id DESC LIMIT 1",
            {"id": item["id"]},
        )
        signals = rows(
            conn,
            "SELECT kind FROM app.signals WHERE subject_id=:id AND expires_at>now() AND status IN ('candidate','accepted') ORDER BY kind",
            {"id": item["id"]},
        )
        return project(
            dto.AccountView,
            {
                **item,
                "unknown_fields": unknown,
                "source_status": get(conn, "data_sources", item["source_id"])["rights_status"],
                "current_fact_count": sum(not invalid_reasons(conn, fact) for fact in facts),
                "signals": [signal["kind"] for signal in signals],
                "score_summary": score(conn, scores[0]["id"]) if scores else None,
            },
        )
    if table == "leads":
        icpv = get(conn, "icp_versions", item["icp_version_id"])
        offerv = get(conn, "offer_versions", item["offer_version_id"])
        return project(
            dto.LeadView,
            {
                **item,
                "account_name": get(conn, "accounts", item["account_id"])["display_name"],
                "person_name": get(conn, "people", item["person_id"])["display_name"]
                if item["person_id"]
                else None,
                "icp_name": get(conn, "icps", icpv["icp_id"])["name"],
                "icp_version": icpv["version"],
                "offer_name": get(conn, "offers", offerv["offer_id"])["name"],
                "offer_version": offerv["version"],
            },
        )
    if table == "data_sources":
        return source(conn, item)
    if table == "evidence":
        return evidence(conn, item)
    if table == "signals":
        current = (
            item["status"] in {"candidate", "accepted"}
            and item["expires_at"] > datetime.now(UTC)
            and not invalid_reasons(conn, get(conn, "evidence", item["evidence_id"]))
        )
        return project(dto.SignalView, {**item, "current_support": current})
    if table == "documents":
        if not document_allowed(conn, item["id"]):
            raise BusinessError("NOT_FOUND", 404)
        return project(
            dto.DocumentView,
            {
                **item,
                "versions": [
                    project(dto.DocumentVersionView, version)
                    for version in rows(
                        conn,
                        "SELECT * FROM app.document_versions WHERE document_id=:id ORDER BY version DESC LIMIT 200",
                        {"id": item["id"]},
                    )
                ],
            },
        )
    if table == "icp_versions":
        excluded = rows(
            conn,
            "SELECT account_id FROM app.icp_excluded_accounts WHERE icp_version_id=:id ORDER BY account_id",
            {"id": item["id"]},
        )
        return project(
            dto.ICPVersionView,
            {
                **item,
                "exclusions": {
                    **item["exclusions"],
                    "account_ids": [entry["account_id"] for entry in excluded],
                },
            },
        )
    if table == "offer_versions":
        proofs = rows(
            conn,
            "SELECT document_version_id FROM app.offer_proofs WHERE offer_version_id=:id ORDER BY document_version_id",
            {"id": item["id"]},
        )
        return project(
            dto.OfferVersionView,
            {
                **item,
                "proof_document_version_ids": [entry["document_version_id"] for entry in proofs],
            },
        )
    return project(VIEWS[table], item)


def account_detail(conn: Connection, identifier: UUID) -> dto.AccountDetail:
    account = get(conn, "accounts", identifier)
    return dto.AccountDetail(
        account=view(conn, "accounts", account),
        source=source(conn, get(conn, "data_sources", account["source_id"])),
        evidence=[
            evidence(conn, item)
            for item in rows(
                conn,
                "SELECT * FROM app.evidence WHERE subject_id=:id ORDER BY observed_at DESC,id LIMIT 200",
                {"id": identifier},
            )
        ],
        signals=[
            view(conn, "signals", item)
            for item in rows(
                conn,
                "SELECT * FROM app.signals WHERE subject_id=:id ORDER BY observed_at DESC,id LIMIT 200",
                {"id": identifier},
            )
        ],
        employments=[
            project(
                dto.EmploymentView,
                {
                    **item,
                    "current_support": not invalid_reasons(
                        conn, get(conn, "evidence", item["evidence_id"])
                    ),
                },
            )
            for item in rows(
                conn,
                "SELECT * FROM app.employments WHERE account_id=:id ORDER BY observed_at DESC,id LIMIT 200",
                {"id": identifier},
            )
        ],
        scores=[
            score(conn, item["id"])
            for item in rows(
                conn,
                "SELECT id FROM app.scores WHERE subject_id=:id ORDER BY computed_at DESC,id LIMIT 20",
                {"id": identifier},
            )
        ],
    )


def page(
    conn: Connection,
    table: str,
    cursor: str | None,
    limit: int,
    secret: str,
    principal: UUID,
    workspace: UUID,
) -> tuple[list[Any], str | None]:
    if table not in VIEWS:
        raise ValueError("Unknown projection")
    boundary = ""
    params: dict[str, Any] = {"limit": limit + 1}
    scope = {"table": table, "workspace": str(workspace), "principal": str(principal)}
    if cursor:
        try:
            payload, signature = cursor.split(".")
            raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            if not hmac.compare_digest(
                hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(), signature
            ):
                raise ValueError()
            parsed = json.loads(raw)
            if parsed["scope"] != scope:
                raise ValueError()
            params.update(
                {"stamp": datetime.fromisoformat(parsed["stamp"]), "last": UUID(parsed["id"])}
            )
            boundary = " AND (t.created_at,t.id)>(:stamp,:last)"
        except (ValueError, KeyError, TypeError):
            raise BusinessError("INVALID_CURSOR", 400) from None
    acl = ""
    if table == "documents":
        acl = " AND EXISTS(SELECT 1 FROM app.document_grants g WHERE g.workspace_id=t.workspace_id AND g.document_id=t.id AND g.principal_id=app.current_principal_id() AND (g.expires_at IS NULL OR g.expires_at>now())) AND t.state='active'"
    result = rows(
        conn,
        f"SELECT t.* FROM app.{table} t WHERE true{boundary}{acl} ORDER BY t.created_at,t.id LIMIT :limit",
        params,
    )
    next_cursor = None
    if len(result) > limit:
        last = result[limit - 1]
        raw = json.dumps(
            {"scope": scope, "stamp": last["created_at"].isoformat(), "id": str(last["id"])},
            sort_keys=True,
        ).encode()
        next_cursor = (
            base64.urlsafe_b64encode(raw).decode().rstrip("=")
            + "."
            + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        )
    return [view(conn, table, item) for item in result[:limit]], next_cursor


def search(conn: Connection, query: str, limit: int) -> list[dto.KnowledgeHit]:
    # RLS and ACL joins precede any returned text. Stale is explicitly labelled.
    found = rows(
        conn,
        """SELECT k.id AS knowledge_id,d.id AS document_id,v.id AS document_version_id,d.title,c.text AS excerpt,k.kind,CASE WHEN k.status='stale' OR k.review_due_at<=now() THEN 'stale' ELSE 'approved' END AS status,k.review_due_at,c.hash FROM app.knowledge_chunks c JOIN app.knowledge_items k ON k.workspace_id=c.workspace_id AND k.id=c.knowledge_id JOIN app.document_versions v ON v.workspace_id=k.workspace_id AND v.id=k.document_version_id JOIN app.documents d ON d.workspace_id=v.workspace_id AND d.id=v.document_id WHERE d.state='active' AND k.status<>'revoked' AND k.valid_from<=now() AND c.search_vector @@ plainto_tsquery('english',:q) AND EXISTS(SELECT 1 FROM app.document_grants g WHERE g.workspace_id=d.workspace_id AND g.document_id=d.id AND g.principal_id=app.current_principal_id() AND (g.expires_at IS NULL OR g.expires_at>now())) ORDER BY k.review_due_at DESC,k.id,c.ordinal LIMIT :limit""",
        {"q": query, "limit": limit},
    )
    return [dto.KnowledgeHit.model_validate(item) for item in found]
