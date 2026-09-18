"""Exact one-use policy activation through the shared approval lifecycle."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Connection

from company_os.application import authority
from company_os.domain.identity import SessionIdentity
from company_os.domain.scoring import canonical_hash
from company_os.persistence.authority import get, insert, update
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows
from company_os.persistence.runtime import clock
from company_os.policy.engine import Evaluation, evaluate
from company_os.policy_contracts import (
    PolicyActivate,
    PolicyActivationPayload,
    PolicyInput,
    PolicyRules,
)


def propose(
    conn: Connection,
    body: PolicyInput,
    version: int,
    actor: SessionIdentity,
    roles: frozenset[str],
    correlation: UUID,
) -> dict[str, Any]:
    authority.gate(conn)
    authority.founder(conn, actor)
    policies = rows(
        conn, "SELECT * FROM app.policies WHERE action=:a FOR UPDATE", {"a": body.rules.action}
    )
    if not policies:
        raise BusinessError("NOT_FOUND", 404)
    policy = policies[0]
    if policy["record_version"] != version:
        raise BusinessError("VERSION_CONFLICT")
    now = clock(conn)
    if not body.effective_at <= now < body.expires_at:
        raise BusinessError("CANDIDATE_NOT_CURRENT", 423)
    governing = rows(
        conn,
        "SELECT v.* FROM app.policies p JOIN app.policy_versions v ON v.id=p.active_version_id WHERE p.action='policy.activate'",
    )
    if not governing:
        raise BusinessError("POLICY_UNCONFIGURED", 423)
    governance = governing[0]
    result = evaluate(
        Evaluation(
            action="policy.activate",
            roles=roles,
            now=now,
            expires_at=body.approval_expires_at,
            uses=1,
            spend=Decimal(0),
            volume=1,
            targets=1,
            versions_match=True,
            rights_valid=True,
            suppressed=False,
            frozen=bool(
                rows(
                    conn,
                    "SELECT id FROM app.authority_freezes WHERE action IS NULL OR action='policy.activate'",
                )
            ),
            policy_current=governance["effective_at"] <= now < governance["expires_at"],
        ),
        PolicyRules.model_validate(governance["rules"]),
    )
    rules = body.rules.model_dump(mode="json")
    number = rows(
        conn,
        "SELECT COALESCE(max(version),0)+1 AS n FROM app.policy_versions WHERE policy_id=:id",
        {"id": policy["id"]},
    )[0]["n"]
    candidate = insert(
        conn,
        "policy_versions",
        {
            "policy_id": policy["id"],
            "version": number,
            "rules": rules,
            "content_hash": canonical_hash(rules),
            "effective_at": body.effective_at,
            "expires_at": body.expires_at,
            "session_id": actor.session_id,
            "rationale": body.rationale,
        },
    )
    payload = PolicyActivationPayload(
        label=f"Activate {body.rules.action} version {number}",
        policy_id=policy["id"],
        policy_record_version=version,
        current_active_version_id=policy["active_version_id"],
        candidate_version_id=candidate["id"],
        candidate_version_number=number,
        candidate_content_hash=candidate["content_hash"],
        candidate_effective_at=body.effective_at.isoformat(),
        candidate_expires_at=body.expires_at.isoformat(),
        rules=body.rules,
        workspace_id=policy["workspace_id"],
    ).model_dump(mode="json")
    cohort = [{"id": str(policy["id"]), "version": version}]
    payload_hash, target_hash = canonical_hash(payload), authority.target_hash(cohort)
    decision = insert(
        conn,
        "policy_decisions",
        {
            "policy_version_id": governance["id"],
            "action": "policy.activate",
            "payload_hash": payload_hash,
            "target_set_hash": target_hash,
            "object_versions": {"objects": cohort},
            "assurance": actor.assurance,
            "result": result.result,
            "reasons": result.reasons,
            "correlation_id": correlation,
        },
    )
    if result.result != "REQUIRE_APPROVAL":
        return {
            "result": result.result,
            "reasons": result.reasons,
            "decision_id": str(decision["id"]),
        }
    request = insert(
        conn,
        "approval_requests",
        {
            "action": "policy.activate",
            "policy_version_id": governance["id"],
            "payload": payload,
            "payload_hash": payload_hash,
            "target_set_hash": target_hash,
            "scope_hash": canonical_hash(
                {
                    "payload": payload,
                    "policy_version_id": str(governance["id"]),
                    "approval_expires_at": body.approval_expires_at.isoformat(),
                    "maximum_uses": 1,
                }
            ),
            "maximum_uses": 1,
            "maximum_spend": Decimal(0),
            "maximum_volume": 1,
            "expires_at": body.approval_expires_at,
            "rationale": body.rationale,
            "correlation_id": correlation,
            "policy_id": policy["id"],
            "candidate_version_id": candidate["id"],
            "expected_policy_record_version": version,
            "expected_active_version_id": policy["active_version_id"],
        },
    )
    authority.emit(conn, request, "approval.requested", correlation)
    return {
        "result": result.result,
        "request_id": str(request["id"]),
        "decision_id": str(decision["id"]),
    }


def activate(
    conn: Connection, body: PolicyActivate, version: int, actor: SessionIdentity, correlation: UUID
) -> dict[str, Any]:
    authority.gate(conn)
    authority.founder(conn, actor)
    manifest = get(conn, "approval_manifests", body.manifest_id)
    request = get(conn, "approval_requests", manifest["request_id"], lock=True)
    if (
        request["action"] != "policy.activate"
        or request["candidate_version_id"] != body.policy_version_id
        or manifest["decision_id"] != body.decision_id
    ):
        raise BusinessError("ACTIVATION_SCOPE_MISMATCH", 423)
    reason = authority.validate(conn, manifest["id"])
    if reason:
        raise BusinessError(reason, 423)
    policy = get(conn, "policies", request["policy_id"], lock=True)
    if policy["record_version"] != version:
        raise BusinessError("VERSION_CONFLICT")
    if rows(conn, "SELECT id FROM app.approval_uses WHERE manifest_id=:id", {"id": manifest["id"]}):
        raise BusinessError("AUTHORITY_CONSUMED", 423)
    insert(
        conn,
        "approval_uses",
        {
            "manifest_id": manifest["id"],
            "activation_policy_id": policy["id"],
            "activation_session_id": actor.session_id,
            "use_number": 1,
            "spend_reserved": Decimal(0),
            "volume": 1,
        },
    )
    authority.final_temporal_check(conn, manifest["id"])
    changed = update(conn, "policies", policy, active_version_id=body.policy_version_id)
    # The database resolves the same authority use when the exact pointer changes.
    authority.emit(conn, request, "policy.activated", correlation)
    return changed
