"""Exact authority commands shared by API and fake runtime. No provider calls."""

from collections.abc import Callable
from datetime import UTC
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from company_os.application import runtime
from company_os.domain.identity import AccessDenied, SessionIdentity
from company_os.domain.scoring import canonical_hash
from company_os.persistence.authority import get, insert, update
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows
from company_os.persistence.runtime import clock
from company_os.policy.engine import Evaluation, evaluate
from company_os.policy_contracts import (
    DecideAuthority,
    ExecuteAuthority,
    PolicyRules,
    RequestAuthority,
)
from company_os.runtime_contracts import SyntheticInput


def gate(conn: Connection) -> None:
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(app.current_workspace_id()::text,55))")
    )


def idempotent(
    conn: Connection,
    action: str,
    key: str,
    payload: dict[str, Any],
    operation: Callable[[], dict[str, Any]],
    *,
    recheck: bool = False,
) -> dict[str, Any]:
    gate(conn)
    existing = rows(
        conn,
        "SELECT * FROM app.authority_command_receipts WHERE created_by=app.current_principal_id() AND command_type=:a AND idempotency_key=:k",
        {"a": action, "k": key},
    )
    expected = runtime.digest(payload)
    if existing:
        if existing[0]["request_hash"] != expected:
            raise BusinessError("IDEMPOTENCY_CONFLICT")
        return operation() if recheck else existing[0]["response"]  # type: ignore[no-any-return]
    result = operation()
    # JSON receipt retains a bounded response; scope and grant history are separate.
    saved = insert(
        conn,
        "authority_command_receipts",
        {
            "command_type": action,
            "idempotency_key": key,
            "request_hash": expected,
            "response": result,
        },
    )
    return saved["response"]  # type: ignore[no-any-return]


def founder(conn: Connection, identity: SessionIdentity, *, mfa: bool = True) -> None:
    if not conn.execute(
        text("SELECT app.authority_founder(:id,:mfa)"), {"id": identity.session_id, "mfa": mfa}
    ).scalar_one():
        raise AccessDenied("Current founder assurance required")


def emit(conn: Connection, item: dict[str, Any], kind: str, correlation: UUID) -> None:
    from uuid import uuid4

    from company_os.persistence.runtime import insert as runtime_insert

    event = runtime_insert(
        conn,
        "events",
        {
            "event_type": kind,
            "aggregate_type": "approval",
            "aggregate_id": item["id"],
            "aggregate_version": item["record_version"],
            "actor_type": "user",
            "actor_id": conn.execute(text("SELECT app.current_principal_id()")).scalar_one(),
            "correlation_id": correlation,
            "origin": "company_os",
            "classification": "internal",
            "schema_version": 2,
            "trace_id": str(correlation),
            "payload": {
                "approval_id": str(item["id"]),
                "payload_hash": item["payload_hash"],
                "scope_hash": item["scope_hash"],
                "state": item["state"],
            },
        },
    )
    runtime_insert(conn, "outbox", {"event_id": event["id"]})
    conn.execute(
        text(
            "INSERT INTO app.audit_entries(id,workspace_id,created_by,actor_id,actor_type,action_type,target_type,target_id,request_id,correlation_id,command_id,decision,outcome,change_summary,payload_hash,policy_version,event_id) VALUES(:id,app.current_workspace_id(),app.current_principal_id(),app.current_principal_id(),'user',:kind,'approval',:target,:c,:c,:c,'allow','committed',:kind,:hash,:policy,:event)"
        ),
        {
            "id": uuid4(),
            "kind": kind,
            "target": item["id"],
            "c": correlation,
            "hash": item["payload_hash"],
            "policy": str(item["policy_version_id"]),
            "event": event["id"],
        },
    )


def targets(conn: Connection, identifier: UUID) -> list[dict[str, Any]]:
    request = get(conn, "approval_requests", identifier)
    if request["action"] == "policy.activate":
        return [{"id": request["policy_id"], "version": request["expected_policy_record_version"]}]
    return rows(
        conn,
        "SELECT target_id AS id,expected_version AS version FROM app.approval_targets WHERE request_id=:id ORDER BY target_id",
        {"id": identifier},
    )


def target_hash(values: list[dict[str, Any]]) -> str:
    return runtime.digest(
        sorted(
            [{"id": str(x["id"]), "version": x["version"]} for x in values], key=lambda x: x["id"]
        )
    )


def request_authority(
    conn: Connection,
    body: RequestAuthority,
    roles: frozenset[str],
    assurance: str,
    correlation: UUID,
) -> dict[str, Any]:
    gate(conn)
    policies = rows(
        conn,
        "SELECT v.* FROM app.policies p JOIN app.policy_versions v ON v.id=p.active_version_id WHERE p.action=:action",
        {"action": body.action},
    )
    if not policies:
        raise BusinessError("POLICY_UNCONFIGURED", 423)
    policy = policies[0]
    rules = PolicyRules.model_validate(policy["rules"])
    chosen = [
        get(conn, "authority_test_targets", x.id, lock=True)
        for x in sorted(body.targets, key=lambda x: x.id)
    ]
    versions = {x.id: x.version for x in body.targets}
    now = clock(conn)
    result = evaluate(
        Evaluation(
            action=body.action,
            roles=roles,
            now=now,
            expires_at=body.expires_at,
            uses=body.maximum_uses,
            spend=body.maximum_spend,
            volume=body.maximum_volume,
            targets=len(chosen),
            versions_match=all(x["record_version"] == versions[x["id"]] for x in chosen),
            rights_valid=all(x["rights_valid"] for x in chosen),
            suppressed=any(x["suppressed"] for x in chosen),
            frozen=bool(
                rows(
                    conn,
                    "SELECT id FROM app.authority_freezes WHERE action IS NULL OR action=:a",
                    {"a": body.action},
                )
            ),
            policy_current=policy["effective_at"] <= now < policy["expires_at"],
        ),
        rules,
    )
    payload_hash = canonical_hash(body.payload.model_dump(mode="json"))
    target_set_hash = target_hash([x.model_dump() for x in body.targets])
    snapshot = {
        **body.model_dump(mode="json", exclude={"rationale", "supersedes_id"}),
        "targets": sorted([x.model_dump(mode="json") for x in body.targets], key=lambda x: x["id"]),
        "workspace_id": str(chosen[0]["workspace_id"]),
        "policy_version_id": str(policy["id"]),
    }
    decision = insert(
        conn,
        "policy_decisions",
        {
            "policy_version_id": policy["id"],
            "action": body.action,
            "payload_hash": payload_hash,
            "target_set_hash": target_set_hash,
            "object_versions": {"objects": snapshot["targets"]},
            "assurance": assurance,
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
            "action": body.action,
            "policy_version_id": policy["id"],
            "payload": body.payload.model_dump(mode="json"),
            "payload_hash": payload_hash,
            "scope_hash": runtime.digest(snapshot),
            "target_set_hash": target_set_hash,
            "maximum_uses": body.maximum_uses,
            "maximum_spend": body.maximum_spend,
            "maximum_volume": body.maximum_volume,
            "expires_at": body.expires_at,
            "rationale": body.rationale,
            "correlation_id": correlation,
            "supersedes_id": body.supersedes_id,
        },
    )
    for target in body.targets:
        insert(
            conn,
            "approval_targets",
            {
                "request_id": request["id"],
                "target_id": target.id,
                "expected_version": target.version,
            },
        )
    if body.supersedes_id:
        old = get(conn, "approval_requests", body.supersedes_id, lock=True)
        if old["created_by"] != request["created_by"] or old["state"] not in {
            "pending",
            "approved",
            "rejected",
            "superseded",
        }:
            raise BusinessError("INVALID_SUPERSESSION")
        if old["state"] in {"pending", "approved"}:
            old = update(conn, "approval_requests", old, state="superseded")
            emit(conn, old, "approval.invalidated", correlation)
    emit(conn, request, "approval.requested", correlation)
    return {
        "result": result.result,
        "request_id": str(request["id"]),
        "decision_id": str(decision["id"]),
    }


def decide(
    conn: Connection,
    identifier: UUID,
    version: int,
    body: DecideAuthority,
    actor: SessionIdentity,
    correlation: UUID,
) -> dict[str, Any]:
    gate(conn)
    founder(conn, actor)
    request = get(conn, "approval_requests", identifier, lock=True)
    if request["record_version"] != version:
        raise BusinessError("VERSION_CONFLICT")
    if request["state"] != "pending" or request["expires_at"] <= clock(conn):
        raise BusinessError("REQUEST_NOT_CURRENT", 423)
    if body.expected_scope_hash != request["scope_hash"]:
        raise BusinessError("SCOPE_CHANGED", 423)
    if body.decision == "approve":
        if not rows(
            conn,
            "SELECT id FROM app.workspaces WHERE id=app.current_workspace_id() AND status='active'",
        ):
            raise BusinessError("WORKSPACE_NOT_ACTIVE", 423)
        policy = get(conn, "policy_versions", request["policy_version_id"])
        if get(conn, "policies", policy["policy_id"])["active_version_id"] != policy["id"]:
            raise BusinessError("POLICY_CHANGED", 423)
        if request["action"] == "policy.activate":
            reason = conn.execute(
                text("SELECT app.authority_candidate_current(:id)"), {"id": identifier}
            ).scalar_one()
            if reason:
                raise BusinessError(reason, 423)
        for target in [] if request["action"] == "policy.activate" else targets(conn, identifier):
            current = get(conn, "authority_test_targets", target["id"], lock=True)
            if (
                current["record_version"] != target["version"]
                or current["suppressed"]
                or not current["rights_valid"]
            ):
                raise BusinessError("TARGET_NOT_CURRENT", 423)
        if rows(
            conn,
            "SELECT id FROM app.authority_freezes WHERE action IS NULL OR action=:a",
            {"a": request["action"]},
        ):
            raise BusinessError("EMERGENCY_FREEZE", 423)
    decision = insert(
        conn,
        "approval_decisions",
        {
            "request_id": identifier,
            "decision": body.decision,
            "session_id": actor.session_id,
            "rationale": body.rationale,
            "correlation_id": correlation,
        },
    )
    if body.decision == "approve":
        scope = {
            "version": 1,
            "scope_hash": request["scope_hash"],
            "workspace_id": str(request["workspace_id"]),
            "action": request["action"],
            "policy_version_id": str(request["policy_version_id"]),
            "payload_hash": request["payload_hash"],
            "target_set_hash": request["target_set_hash"],
            "targets": [
                {"id": str(x["id"]), "version": x["version"]} for x in targets(conn, identifier)
            ],
            "maximum_uses": request["maximum_uses"],
            "maximum_spend": str(request["maximum_spend"]),
            "maximum_volume": request["maximum_volume"],
            "expires_at": request["expires_at"].astimezone(UTC).isoformat(),
            "approver_id": str(actor.principal_id),
            "assurance": "aal2",
        }
        if request["action"] == "policy.activate":
            scope["policy_change"] = request["payload"]
        insert(
            conn,
            "approval_manifests",
            {
                "request_id": identifier,
                "decision_id": decision["id"],
                "scope": scope,
                "manifest_hash": canonical_hash(scope),
                "starts_at": clock(conn),
                "expires_at": request["expires_at"],
            },
        )
    request = update(
        conn,
        "approval_requests",
        request,
        state={"approve": "approved", "reject": "rejected", "revise": "superseded"}[body.decision],
    )
    emit(
        conn,
        request,
        {
            "approve": "approval.granted",
            "reject": "approval.rejected",
            "revise": "approval.invalidated",
        }[body.decision],
        correlation,
    )
    return request


def validate(conn: Connection, manifest_id: UUID) -> str | None:
    return conn.execute(
        text("SELECT app.authority_validate(:id)"), {"id": manifest_id}
    ).scalar_one()  # type: ignore[no-any-return]


def final_temporal_check(conn: Connection, manifest_id: UUID) -> None:
    code = conn.execute(
        text("SELECT app.authority_temporal(:id)"), {"id": manifest_id}
    ).scalar_one()
    if code:
        raise BusinessError(code, 423)


def validate_budget(conn: Connection, effect: dict[str, Any]) -> None:
    caps = rows(
        conn,
        "SELECT b.* FROM app.budgets b WHERE b.id=(SELECT budget_id FROM app.budget_reservations WHERE id=:r) OR EXISTS(SELECT 1 FROM app.reservation_budget_caps c WHERE c.reservation_id=:r AND c.budget_id=b.id) ORDER BY b.id FOR SHARE",
        {"r": effect["reservation_id"]},
    )
    now = clock(conn)
    if not caps or any(
        b["status"] != "active"
        or not b["period_start"] <= now < b["period_end"]
        or b["spent_usd"] + b["reserved_usd"] > b["limit_usd"]
        for b in caps
    ):
        raise BusinessError("CURRENT_BUDGET_BLOCKED", 423)
    if not conn.execute(text("SELECT app.runtime_company_cap_ok()")).scalar_one():
        raise BusinessError("COMPANY_BUDGET_EXHAUSTED", 423)


def execute(
    conn: Connection, identifier: UUID, body: ExecuteAuthority, correlation: UUID
) -> dict[str, Any]:
    gate(conn)
    manifest = rows(
        conn, "SELECT * FROM app.approval_manifests WHERE request_id=:id", {"id": identifier}
    )
    if not manifest:
        raise BusinessError("APPROVAL_REQUIRED", 423)
    request = get(conn, "approval_requests", identifier)
    if request["action"] == "policy.activate":
        raise BusinessError("POLICY_ACTIVATION_COMMAND_REQUIRED", 423)
    if request["action"] == "ai.route.promote":
        raise BusinessError("ROUTE_PROMOTION_COMMAND_REQUIRED", 423)
    code = validate(conn, manifest[0]["id"])
    payload_hash = canonical_hash(body.payload.model_dump(mode="json"))
    cohort_hash = target_hash([x.model_dump() for x in body.targets])
    if payload_hash != request["payload_hash"]:
        code = "PAYLOAD_CHANGED"
    if cohort_hash != request["target_set_hash"]:
        code = "TARGET_SET_CHANGED"
    insert(
        conn,
        "policy_decisions",
        {
            "request_id": identifier,
            "policy_version_id": request["policy_version_id"],
            "action": request["action"],
            "payload_hash": payload_hash,
            "target_set_hash": cohort_hash,
            "object_versions": {"objects": [x.model_dump(mode="json") for x in body.targets]},
            "assurance": "durable_manifest",
            "result": "DENY" if code else "ALLOW",
            "reasons": [code or "WITHIN_CURRENT_AUTHORITY"],
            "correlation_id": correlation,
        },
    )
    if code:
        return {"result": "DENY", "reasons": [code]}
    # Namespace the logical operation by its immutable grant. The existing runtime
    # retains canonical effect ownership and deduplicates retries/followers.
    item = runtime.submit(
        conn,
        SyntheticInput(
            scenario=body.payload.scenario,
            logical_key="authority:" + str(manifest[0]["id"]) + ":" + body.logical_key,
        ),
        correlation,
    )
    existing = rows(
        conn, "SELECT * FROM app.authority_bindings WHERE input_id=:id", {"id": item["id"]}
    )
    if not existing:
        insert(
            conn,
            "authority_bindings",
            {
                "manifest_id": manifest[0]["id"],
                "input_id": item["id"],
                "payload_hash": payload_hash,
                "target_set_hash": cohort_hash,
            },
        )
    return {"result": "ALLOW", "input_id": str(item["id"]), "manifest_id": str(manifest[0]["id"])}


def reserve(conn: Connection, effect: dict[str, Any]) -> None:
    bindings = rows(
        conn,
        "SELECT * FROM app.authority_bindings WHERE input_id=:id",
        {"id": effect["request_ref"]},
    )
    if not bindings:
        return
    binding = bindings[0]
    code = validate(conn, binding["manifest_id"])
    if code:
        raise BusinessError(code, 423)
    if rows(conn, "SELECT id FROM app.approval_uses WHERE effect_id=:id", {"id": effect["id"]}):
        return
    manifest = get(conn, "approval_manifests", binding["manifest_id"])
    amount = rows(
        conn,
        "SELECT maximum_usd FROM app.budget_reservations WHERE id=:id",
        {"id": effect["reservation_id"]},
    )[0]["maximum_usd"]
    request = get(conn, "approval_requests", manifest["request_id"])
    counts = rows(
        conn,
        "SELECT count(*) AS uses,COALESCE(sum(u.spend_reserved),0) AS spend,COALESCE(sum(u.volume),0) AS volume FROM app.approval_uses u WHERE manifest_id=:m AND NOT EXISTS(SELECT 1 FROM app.approval_use_results r WHERE r.use_id=u.id AND r.result='released')",
        {"m": manifest["id"]},
    )[0]
    volume = len(targets(conn, manifest["request_id"]))
    if (
        counts["uses"] >= request["maximum_uses"]
        or counts["spend"] + amount > request["maximum_spend"]
        or counts["volume"] + volume > request["maximum_volume"]
    ):
        raise BusinessError("AUTHORITY_LIMIT", 423)
    insert(
        conn,
        "approval_uses",
        {
            "manifest_id": manifest["id"],
            "effect_id": effect["id"],
            "job_id": effect["job_id"],
            "use_number": 1,
            "spend_reserved": Decimal(amount),
            "volume": volume,
        },
    )


def resolve_use(conn: Connection, effect: dict[str, Any]) -> None:
    uses = rows(
        conn,
        "SELECT u.id FROM app.approval_uses u WHERE effect_id=:id AND NOT EXISTS(SELECT 1 FROM app.approval_use_results r WHERE r.use_id=u.id)",
        {"id": effect["id"]},
    )
    if uses and effect["state"] in {"confirmed", "rejected", "cancelled"}:
        insert(
            conn,
            "approval_use_results",
            {
                "use_id": uses[0]["id"],
                "result": "consumed" if effect["state"] == "confirmed" else "released",
            },
        )


def record_runtime_decision(conn: Connection, job: dict[str, Any], code: str | None) -> None:
    binding = rows(
        conn,
        "SELECT m.request_id FROM app.authority_bindings b JOIN app.approval_manifests m ON m.id=b.manifest_id WHERE b.input_id=:id",
        {"id": job["input_ref"]},
    )
    if not binding:
        return
    request = get(conn, "approval_requests", binding[0]["request_id"])
    insert(
        conn,
        "policy_decisions",
        {
            "request_id": request["id"],
            "policy_version_id": request["policy_version_id"],
            "action": request["action"],
            "payload_hash": request["payload_hash"],
            "target_set_hash": request["target_set_hash"],
            "object_versions": {
                "objects": [
                    {"id": str(t["id"]), "version": t["version"]}
                    for t in targets(conn, request["id"])
                ]
            },
            "assurance": "durable_manifest",
            "result": "DENY" if code else "ALLOW",
            "reasons": [code or "DISPATCH_AUTHORITY_CURRENT"],
            "correlation_id": job["correlation_id"],
        },
    )
