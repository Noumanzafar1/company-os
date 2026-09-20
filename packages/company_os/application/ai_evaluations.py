"""Evaluation jobs, frozen comparison and human-only exact route promotion."""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection

from company_os.ai.contracts import AIEvaluation, AIRequest, PromotionRequest
from company_os.ai.evaluation import metrics
from company_os.ai.validation import digest
from company_os.application import ai_gateway, authority, runtime
from company_os.domain.identity import SessionIdentity
from company_os.persistence.ai import get, insert, update
from company_os.persistence.authority import get as authority_get
from company_os.persistence.authority import insert as authority_insert
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows
from company_os.persistence.runtime import clock
from company_os.policy.engine import Evaluation, evaluate
from company_os.policy_contracts import PolicyRules, RoutePromotionPayload


def request_evaluation(conn: Connection, split: str, correlation: UUID) -> dict[str, Any]:
    current = ai_gateway.active_route(conn)
    candidate = rows(
        conn,
        "SELECT r.* FROM app.ai_routes r JOIN app.ai_route_states s ON s.route_id=r.id WHERE s.state IN ('draft','evaluated','superseded') ORDER BY r.id LIMIT 1",
    )
    if not candidate:
        raise BusinessError("NO_ROUTE_CANDIDATE", 423)
    dataset = rows(
        conn,
        "SELECT * FROM app.ai_registry WHERE kind='dataset' AND name=:name ORDER BY version DESC LIMIT 1",
        {"name": split},
    )[0]
    batch_id = uuid4()
    runs: dict[str, list[str]] = {}
    for label, route in (("candidate", candidate[0]), ("current", current)):
        runs[label] = []
        for i, scenario in enumerate(dataset["body"]["cases"]):
            request = AIRequest.model_validate({"scenario": scenario})
            run = ai_gateway.submit(
                conn,
                request,
                f"eval:{batch_id}:{label}:{i}",
                correlation,
                evaluation_route=route["id"],
            )
            runs[label].append(str(run["id"]))
    batch = insert(
        conn,
        "ai_evaluation_batches",
        {
            "id": batch_id,
            "body": {
                "candidate": str(candidate[0]["id"]),
                "current": str(current["id"]),
                "dataset": str(dataset["id"]),
                "runs": runs,
            },
        },
    )
    runtime.audit(conn, "ai.evaluation_requested", batch_id, correlation)
    return {
        "id": str(batch["id"]),
        "state": "queued",
        "model_tasks": sum(len(v) for v in runs.values()),
    }


def finalize(conn: Connection) -> None:
    # Called by the existing worker maintenance loop. No model work happens here.
    for batch in rows(
        conn,
        "SELECT b.* FROM app.ai_evaluation_batches b WHERE NOT EXISTS(SELECT 1 FROM app.ai_evaluations e WHERE e.batch_id=b.id) ORDER BY b.created_at LIMIT 10",
    ):
        body = batch["body"]
        freshness = {
            str(r["run_id"]): r["context_current"]
            for r in rows(conn, "SELECT * FROM app.ai_evaluation_inputs(:id)", {"id": batch["id"]})
        }
        compared: dict[str, dict[str, Any]] = {}
        for label in ("candidate", "current"):
            runs = rows(
                conn,
                "SELECT a.*,r.body result FROM app.agent_runs a LEFT JOIN app.ai_results r ON r.id=a.result_id WHERE a.id=ANY(CAST(:ids AS uuid[]))",
                {"ids": body["runs"][label]},
            )
            if len(runs) != len(body["runs"][label]) or any(
                r["state"] in {"queued", "running", "retry_wait"} for r in runs
            ):
                break
            for run in runs:
                run["result"] = run["result"] or {}
                run["context_current"] = freshness.get(str(run["id"]), False)
            calls = rows(
                conn,
                "SELECT * FROM app.model_runs WHERE agent_run_id=ANY(CAST(:ids AS uuid[]))",
                {"ids": body["runs"][label]},
            )
            compared[label] = metrics(runs, calls)
        if len(compared) != 2:
            continue
        dataset, route = (
            get(conn, "ai_registry", UUID(body["dataset"])),
            get(conn, "ai_routes", UUID(body["candidate"])),
        )
        # Either cohort becoming stale invalidates the whole comparison. Keep
        # both original denominators and immutable sample IDs in the batch.
        if not all(freshness.values()):
            compared["candidate"]["decision"] = "technical_fail"
            compared["candidate"]["hard_failure_examples"].append("STALE_EVALUATION_CONTEXT")
        value = AIEvaluation(
            dataset_id=dataset["id"],
            dataset_version=dataset["version"],
            split=dataset["body"]["split"],
            route_candidate=route["id"],
            run_at=clock(conn),
            **compared["candidate"],
        )
        # Serialize competing maintenance loops without holding a call transaction.
        authority.gate(conn)
        if rows(conn, "SELECT id FROM app.ai_evaluations WHERE batch_id=:id", {"id": batch["id"]}):
            continue
        saved = insert(
            conn,
            "ai_evaluations",
            {
                "batch_id": batch["id"],
                "route_id": route["id"],
                "dataset_id": dataset["id"],
                "binding_hash": digest(
                    {"route": route["content_hash"], "dataset": dataset["content_hash"]}
                ),
                "body": value.model_dump(mode="json"),
                "current_route_id": UUID(body["current"]),
                "current_result": compared["current"],
            },
        )
        runtime.audit(conn, "ai.evaluation_completed", saved["id"], batch["id"])


def propose(
    conn: Connection, body: PromotionRequest, actor: SessionIdentity, correlation: UUID
) -> dict[str, Any]:
    authority.gate(conn)
    authority.founder(conn, actor, mfa=False)
    route = get(conn, "ai_routes", body.route_id)
    evaluation = get(conn, "ai_evaluations", body.evaluation_id)
    dataset = get(conn, "ai_registry", evaluation["dataset_id"])
    current = ai_gateway.active_route(conn)
    rollback = get(conn, "ai_routes", body.rollback_route_id)
    if route["body"]["primary_provider"] not in {"fake_openai", "fake_anthropic"}:
        raise BusinessError("FOUNDER_LABELLED_DATASET_REQUIRED", 423)
    if (
        evaluation["route_id"] != route["id"]
        or evaluation["current_route_id"] != current["id"]
        or evaluation["created_at"] < clock(conn) - timedelta(days=30)
        or evaluation["body"]["decision"] != "technical_pass"
        or evaluation["binding_hash"]
        != digest({"route": route["content_hash"], "dataset": dataset["content_hash"]})
    ):
        raise BusinessError("EVALUATION_REQUIRED", 423)
    require_current(conn, evaluation["id"])
    if rollback["id"] != current["id"]:
        raise BusinessError("ROLLBACK_MUST_BE_CURRENT", 423)
    policies = rows(
        conn,
        "SELECT v.* FROM app.policies p JOIN app.policy_versions v ON v.id=p.active_version_id WHERE p.action='ai.route.promote' AND v.effective_at<=clock_timestamp() AND v.expires_at>clock_timestamp()",
    )
    if not policies:
        raise BusinessError("POLICY_UNCONFIGURED", 423)
    target = authority_get(conn, "authority_test_targets", route["target_id"])
    payload = RoutePromotionPayload(
        label="Promote evaluated synthetic AI route",
        route_id=route["id"],
        route_hash=route["content_hash"],
        evaluation_id=evaluation["id"],
        binding_hash=evaluation["binding_hash"],
        rollback_route_id=rollback["id"],
        current_route_id=current["id"],
    ).model_dump(mode="json")
    cohort = [{"id": str(target["id"]), "version": target["record_version"]}]
    expires = clock(conn) + timedelta(minutes=10)
    now = clock(conn)
    policy_result = evaluate(
        Evaluation(
            action="ai.route.promote",
            roles=frozenset({"founder"}),
            now=now,
            expires_at=expires,
            uses=1,
            spend=Decimal(0),
            volume=1,
            targets=1,
            versions_match=True,
            rights_valid=target["rights_valid"],
            suppressed=target["suppressed"],
            frozen=bool(
                rows(
                    conn,
                    "SELECT id FROM app.authority_freezes WHERE action IS NULL OR action='ai.route.promote'",
                )
            ),
            policy_current=policies[0]["effective_at"] <= now < policies[0]["expires_at"],
        ),
        PolicyRules.model_validate(policies[0]["rules"]),
    )
    decision = authority_insert(
        conn,
        "policy_decisions",
        {
            "policy_version_id": policies[0]["id"],
            "action": "ai.route.promote",
            "payload_hash": digest(payload),
            "target_set_hash": digest(cohort),
            "object_versions": {"objects": cohort},
            "assurance": actor.assurance,
            "result": policy_result.result,
            "reasons": policy_result.reasons,
            "correlation_id": correlation,
        },
    )
    if policy_result.result != "REQUIRE_APPROVAL":
        return {
            "result": policy_result.result,
            "reasons": policy_result.reasons,
            "decision_id": str(decision["id"]),
        }
    request = authority_insert(
        conn,
        "approval_requests",
        {
            "action": "ai.route.promote",
            "policy_version_id": policies[0]["id"],
            "payload": payload,
            "payload_hash": digest(payload),
            "target_set_hash": digest(cohort),
            "scope_hash": digest(
                {
                    "payload": payload,
                    "policy": str(policies[0]["id"]),
                    "targets": cohort,
                    "expires": expires.isoformat(),
                }
            ),
            "maximum_uses": 1,
            "maximum_spend": Decimal(0),
            "maximum_volume": 1,
            "expires_at": expires,
            "rationale": "Synthetic technical route only; no production or live provider authority",
            "correlation_id": correlation,
        },
    )
    authority_insert(
        conn,
        "approval_targets",
        {
            "request_id": request["id"],
            "target_id": target["id"],
            "expected_version": target["record_version"],
        },
    )
    authority.emit(conn, request, "approval.requested", correlation)
    return {"request_id": str(request["id"]), "state": "pending"}


def promote(conn: Connection, request_id: UUID, actor: SessionIdentity) -> dict[str, Any]:
    authority.gate(conn)
    authority.founder(conn, actor)
    request = authority_get(conn, "approval_requests", request_id, lock=True)
    if request["action"] != "ai.route.promote":
        raise BusinessError("WRONG_ACTION", 423)
    manifests = rows(
        conn, "SELECT * FROM app.approval_manifests WHERE request_id=:id", {"id": request_id}
    )
    if not manifests:
        raise BusinessError("APPROVAL_REQUIRED", 423)
    manifest = manifests[0]
    if reason := authority.validate(conn, manifest["id"]):
        raise BusinessError(reason, 423)
    require_current(conn, UUID(request["payload"]["evaluation_id"]))
    route_id = UUID(request["payload"]["route_id"])
    use = authority_insert(
        conn,
        "approval_uses",
        {
            "manifest_id": manifest["id"],
            "activation_route_id": route_id,
            "activation_session_id": actor.session_id,
            "use_number": 1,
            "spend_reserved": Decimal(0),
            "volume": 1,
        },
    )
    for state in rows(conn, "SELECT * FROM app.ai_route_states WHERE state='active' FOR UPDATE"):
        update(conn, "ai_route_states", state, state="superseded")
    state = rows(
        conn, "SELECT * FROM app.ai_route_states WHERE route_id=:id FOR UPDATE", {"id": route_id}
    )[0]
    update(
        conn,
        "ai_route_states",
        state,
        state="active",
        manifest_id=manifest["id"],
        evaluation_id=UUID(request["payload"]["evaluation_id"]),
        rollback_route_id=UUID(request["payload"]["rollback_route_id"]),
        activated_at=clock(conn),
        approved_by=actor.principal_id,
    )
    authority_insert(conn, "approval_use_results", {"use_id": use["id"], "result": "consumed"})
    runtime.audit(conn, "ai.route_promoted", route_id, request["correlation_id"])
    return {"route_id": str(route_id), "state": "active"}


def require_current(conn: Connection, evaluation_id: UUID) -> None:
    if not rows(conn, "SELECT app.ai_evaluation_current(:id) ok", {"id": evaluation_id})[0]["ok"]:
        raise BusinessError("EVALUATION_STALE", 423)
