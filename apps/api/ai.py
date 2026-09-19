"""API-057: bounded requests using authenticated shared commands."""

import secrets
from collections.abc import Callable
from typing import Any
from uuid import UUID

from company_os.ai.contracts import (
    AIHealth,
    AIInspection,
    AIRequest,
    AIStatus,
    EvaluationRequest,
    PromotionRequest,
)
from company_os.application import ai_evaluations, ai_gateway, authority
from company_os.application.identity import digest
from company_os.domain.identity import AccessDenied, SessionIdentity
from company_os.persistence.ai import get
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows, transaction
from company_os.policy.access import require_permission
from company_os.policy_contracts import AuthorityEnvelope, Reason
from fastapi import Depends, FastAPI, Header, Request


def register(api: FastAPI, authenticated: Callable[..., SessionIdentity]) -> None:
    prefix = "/v1/workspaces/{workspace_id}"

    def scope(
        request: Request, actor: SessionIdentity, workspace_id: UUID, write: bool = False
    ) -> dict[str, Any]:
        workspace = request.app.state.identity.workspace(actor, workspace_id)
        if workspace is None:
            raise BusinessError("NOT_FOUND", 404)
        require_permission(workspace["permissions"], "system.read")
        if write:
            if not {"founder", "system_administrator"}.intersection(workspace["roles"]):
                raise AccessDenied()
            if request.app.state.config.company_env not in {"development", "test"}:
                raise AccessDenied()
            if request.headers.get(
                "origin"
            ) != request.app.state.config.console_origin or not secrets.compare_digest(
                digest(request.headers.get("x-csrf-token", "")), actor.csrf_hash
            ):
                raise AccessDenied()
            if not 8 <= len(request.headers.get("idempotency-key", "")) <= 128:
                raise BusinessError("IDEMPOTENCY_KEY_REQUIRED", 400)
        return workspace  # type: ignore[no-any-return]

    @api.post(prefix + "/ai-tasks", response_model=AuthorityEnvelope[AIStatus])
    def submit(
        workspace_id: UUID,
        body: AIRequest,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            result = authority.idempotent(
                conn,
                "ai.submit",
                request.headers["idempotency-key"],
                body.model_dump(mode="json"),
                lambda: ai_gateway.submit(
                    conn, body, request.headers["idempotency-key"], request.state.request_id
                ),
            )
        return {"data": {key: result[key] for key in AIStatus.model_fields}}

    @api.get(prefix + "/ai-tasks/{identifier}", response_model=AuthorityEnvelope[AIInspection])
    def inspect(
        workspace_id: UUID,
        identifier: UUID,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            result = ai_gateway.inspect(conn, identifier)
        return {"data": result}

    @api.get(prefix + "/ai-health", response_model=AuthorityEnvelope[AIHealth])
    def health(
        workspace_id: UUID, request: Request, actor: SessionIdentity = Depends(authenticated)
    ) -> Any:
        w = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            result = {
                "providers": rows(
                    conn,
                    "SELECT provider,status,report FROM app.ai_provider_connections ORDER BY provider",
                ),
                "tasks": rows(
                    conn,
                    "SELECT id,job_id,state,error_code,created_at FROM app.agent_runs ORDER BY created_at DESC LIMIT 100",
                ),
                "counts": rows(
                    conn,
                    "SELECT state,count(*) count FROM app.agent_runs GROUP BY state ORDER BY state",
                ),
                "routes": rows(
                    conn,
                    "SELECT r.id,r.version,r.body,s.state,s.evaluation_id,s.record_version,CASE WHEN e.id IS NULL THEN 'missing' WHEN e.created_at<clock_timestamp()-interval '30 days' THEN 'expired' ELSE 'current' END evaluation_status FROM app.ai_routes r JOIN app.ai_route_states s ON s.route_id=r.id LEFT JOIN app.ai_evaluations e ON e.id=s.evaluation_id ORDER BY r.id",
                ),
                "evaluations": rows(
                    conn,
                    "SELECT id,route_id,body,current_route_id,current_result FROM app.ai_evaluations ORDER BY created_at DESC LIMIT 20",
                ),
                "budgets": rows(
                    conn,
                    "SELECT category,status,limit_usd,spent_usd,reserved_usd,period_end FROM app.budgets WHERE category LIKE 'ai_technical_%' ORDER BY category",
                ),
                "warning": "Live providers require separately authorized account preflight. Synthetic evaluation does not establish business quality.",
            }
        return {"data": result}

    @api.post(prefix + "/ai-evaluations", response_model=AuthorityEnvelope[dict[str, Any]])
    def evaluate(
        workspace_id: UUID,
        body: EvaluationRequest,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            result = authority.idempotent(
                conn,
                "ai.evaluate",
                request.headers["idempotency-key"],
                body.model_dump(mode="json"),
                lambda: ai_evaluations.request_evaluation(
                    conn, body.dataset, request.state.request_id
                ),
            )
        return {"data": result}

    @api.post(prefix + "/ai-routes/propose", response_model=AuthorityEnvelope[dict[str, Any]])
    def propose(
        workspace_id: UUID,
        body: PromotionRequest,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            result = authority.idempotent(
                conn,
                "ai.propose",
                request.headers["idempotency-key"],
                body.model_dump(mode="json"),
                lambda: ai_evaluations.propose(conn, body, actor, request.state.request_id),
            )
        return {"data": result}

    @api.post(
        prefix + "/ai-routes/{identifier}/promote", response_model=AuthorityEnvelope[dict[str, Any]]
    )
    def promote(
        workspace_id: UUID,
        identifier: UUID,
        body: Reason,
        request: Request,
        if_match: int = Header(ge=1),
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            authority.founder(conn, actor)

            def command() -> dict[str, Any]:
                record = rows(
                    conn,
                    "SELECT record_version FROM app.approval_requests WHERE id=:id",
                    {"id": identifier},
                )
                if not record or record[0]["record_version"] != if_match:
                    raise BusinessError("VERSION_CONFLICT")
                return ai_evaluations.promote(conn, identifier, actor)

            result = authority.idempotent(
                conn,
                "ai.promote",
                request.headers["idempotency-key"],
                {**body.model_dump(mode="json"), "id": str(identifier), "version": if_match},
                command,
            )
        return {"data": result}

    @api.post(
        prefix + "/ai-tasks/{identifier}/revoke-context",
        response_model=AuthorityEnvelope[dict[str, Any]],
    )
    def revoke(
        workspace_id: UUID,
        identifier: UUID,
        body: Reason,
        request: Request,
        if_match: int = Header(ge=1),
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:

            def command() -> dict[str, Any]:
                run = get(conn, "agent_runs", identifier)
                context = get(conn, "context_packs", run["context_id"])
                source = ai_gateway.revoke(conn, context["source_id"], if_match)
                return {"id": str(identifier), "state": source["state"]}

            result = authority.idempotent(
                conn,
                "ai.revoke",
                request.headers["idempotency-key"],
                {**body.model_dump(mode="json"), "id": str(identifier), "version": if_match},
                command,
            )
        return {"data": result}
