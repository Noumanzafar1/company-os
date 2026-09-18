"""Founder authority routes over the existing authenticated command boundary."""

import secrets
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

from company_os.application import authority as commands
from company_os.application.identity import digest
from company_os.domain.identity import AccessDenied, SessionIdentity
from company_os.persistence.authority import get, insert, update
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows, transaction
from company_os.policy_contracts import (
    ApprovalDetail,
    ApprovalView,
    AuthorityEnvelope,
    AuthorityResult,
    AuthorityTargetView,
    DecideAuthority,
    ExecuteAuthority,
    FreezeAuthority,
    FreezeView,
    PolicyActivate,
    PolicyInput,
    PolicyRecord,
    PolicyView,
    Reason,
    RequestAuthority,
)
from fastapi import Depends, FastAPI, Header, Request, Response
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool


def register(api: FastAPI, authenticated: Callable[..., SessionIdentity]) -> None:
    prefix = "/v1/workspaces/{workspace_id}"

    @api.middleware("http")
    async def audit_authority_denial(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        context = getattr(request.state, "authority_audit", None)
        if context and response.status_code >= 400:
            actor, workspace_id, epoch = context

            def persist() -> None:
                with transaction(
                    request.app.state.engine, actor.principal_id, workspace_id, epoch
                ) as conn:
                    conn.execute(
                        text(
                            "INSERT INTO app.audit_entries(id,workspace_id,created_by,actor_id,actor_type,action_type,target_type,target_id,request_id,correlation_id,command_id,decision,outcome,change_summary,payload_hash,policy_version) VALUES(:id,app.current_workspace_id(),app.current_principal_id(),app.current_principal_id(),'user','authority.denied','workspace',:w,:c,:c,:c,'deny','denied',:reason,:hash,'phase-5-closed-v1')"
                        ),
                        {
                            "id": uuid4(),
                            "w": workspace_id,
                            "c": request.state.request_id,
                            "reason": f"Authority command denied (HTTP {response.status_code})",
                            "hash": "0" * 64,
                        },
                    )

            await run_in_threadpool(persist)
        return response

    def scope(
        request: Request, actor: SessionIdentity, workspace_id: UUID, *, write: bool = False
    ) -> dict[str, Any]:
        workspace = request.app.state.identity.workspace(actor, workspace_id)
        if not workspace:
            raise BusinessError("NOT_FOUND", 404)
        if write:
            request.state.authority_audit = (actor, workspace_id, workspace["authz_epoch"])
        if "business.read" not in workspace["permissions"]:
            raise AccessDenied()
        if write:
            if request.headers.get(
                "origin"
            ) != request.app.state.config.console_origin or not secrets.compare_digest(
                digest(request.headers.get("x-csrf-token", "")), actor.csrf_hash
            ):
                raise AccessDenied()
            if not 8 <= len(request.headers.get("idempotency-key", "")) <= 128:
                raise BusinessError("IDEMPOTENCY_KEY_REQUIRED", 400)
            if request.app.state.config.company_env not in {"development", "test"}:
                raise AccessDenied()
        return workspace  # type: ignore[no-any-return]

    @api.get(
        prefix + "/approvals",
        response_model=AuthorityEnvelope[list[ApprovalView]],
        response_model_exclude_none=True,
    )
    def approvals(
        workspace_id: UUID, request: Request, actor: SessionIdentity = Depends(authenticated)
    ) -> Any:
        w = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            items = rows(
                conn,
                "SELECT *,CASE WHEN expires_at<=clock_timestamp() AND state IN ('pending','approved') THEN 'expired' ELSE state END AS effective_state FROM app.approval_requests WHERE (:founder OR created_by=:actor) ORDER BY created_at DESC,id LIMIT 200",
                {"founder": "founder" in w["roles"], "actor": actor.principal_id},
            )
        return {"data": items}

    @api.get(
        prefix + "/approvals/{identifier}",
        response_model=AuthorityEnvelope[ApprovalDetail],
        response_model_exclude_none=True,
    )
    def detail(
        workspace_id: UUID,
        identifier: UUID,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            item = get(conn, "approval_requests", identifier)
            if "founder" not in w["roles"] and item["created_by"] != actor.principal_id:
                raise BusinessError("NOT_FOUND", 404)
            item["effective_state"] = (
                "expired"
                if item["state"] in {"pending", "approved"}
                and item["expires_at"] <= commands.clock(conn)
                else item["state"]
            )
            manifest = rows(
                conn,
                "SELECT * FROM app.approval_manifests WHERE request_id=:id",
                {"id": identifier},
            )
            history = rows(
                conn,
                "SELECT id,decision,rationale,created_by,created_at,correlation_id FROM app.approval_decisions WHERE request_id=:id ORDER BY created_at",
                {"id": identifier},
            )
            uses = rows(
                conn,
                "SELECT u.*,COALESCE(x.result,'reserved') AS state FROM app.approval_uses u JOIN app.approval_manifests m ON m.id=u.manifest_id LEFT JOIN app.approval_use_results x ON x.use_id=u.id WHERE m.request_id=:id ORDER BY u.use_number",
                {"id": identifier},
            )
            current = commands.validate(conn, manifest[0]["id"]) if manifest else "NO_MANIFEST"
            data = {
                "request": item,
                "targets": commands.targets(conn, identifier),
                "manifest": manifest[0] if manifest else None,
                "history": history,
                "uses": uses,
                "validation_reason": current,
                "remaining_uses": item["maximum_uses"]
                - sum(x["state"] != "released" for x in uses),
            }
        return {"data": data}

    @api.get(
        prefix + "/policies",
        response_model=AuthorityEnvelope[list[PolicyView]],
        response_model_exclude_none=True,
    )
    def policies(
        workspace_id: UUID, request: Request, actor: SessionIdentity = Depends(authenticated)
    ) -> Any:
        w = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            data = rows(
                conn,
                "SELECT p.id,p.record_version,p.action,p.active_version_id,v.version,v.rules,v.content_hash,v.expires_at FROM app.policies p LEFT JOIN app.policy_versions v ON v.id=p.active_version_id ORDER BY p.action",
            )
        return {"data": data}

    @api.post(
        prefix + "/policies/propose",
        response_model=AuthorityEnvelope[AuthorityResult],
        response_model_exclude_none=True,
    )
    def propose(
        workspace_id: UUID,
        body: PolicyInput,
        request: Request,
        if_match: int = Header(ge=1),
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        from company_os.application.policy_activation import propose as command

        w = scope(request, actor, workspace_id, write=True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            commands.founder(conn, actor)
            result = commands.idempotent(
                conn,
                "policy.propose",
                request.headers["idempotency-key"],
                {**body.model_dump(mode="json"), "version": if_match},
                lambda: command(
                    conn, body, if_match, actor, frozenset(w["roles"]), request.state.request_id
                ),
            )
        return {"data": result}

    @api.post(
        prefix + "/policies/activate",
        response_model=AuthorityEnvelope[PolicyRecord],
        response_model_exclude_none=True,
    )
    def activate(
        workspace_id: UUID,
        body: PolicyActivate,
        request: Request,
        if_match: int = Header(ge=1),
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        from company_os.application.policy_activation import activate as command

        w = scope(request, actor, workspace_id, write=True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            commands.founder(conn, actor)
            result = commands.idempotent(
                conn,
                "policy.activate",
                request.headers["idempotency-key"],
                {**body.model_dump(mode="json"), "version": if_match},
                lambda: command(conn, body, if_match, actor, request.state.request_id),
            )
        return {"data": result}

    @api.get(
        prefix + "/authority/targets",
        response_model=AuthorityEnvelope[list[AuthorityTargetView]],
        response_model_exclude_none=True,
    )
    def targets(
        workspace_id: UUID, request: Request, actor: SessionIdentity = Depends(authenticated)
    ) -> Any:
        w = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            data = rows(conn, "SELECT * FROM app.authority_test_targets ORDER BY id LIMIT 200")
        return {"data": data}

    @api.post(
        prefix + "/approvals/request",
        response_model=AuthorityEnvelope[AuthorityResult],
        response_model_exclude_none=True,
    )
    def create(
        workspace_id: UUID,
        body: RequestAuthority,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, write=True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            result = commands.idempotent(
                conn,
                "request",
                request.headers["idempotency-key"],
                body.model_dump(mode="json"),
                lambda: commands.request_authority(
                    conn, body, frozenset(w["roles"]), actor.assurance, request.state.request_id
                ),
            )
        return {"data": result}

    @api.post(
        prefix + "/approvals/{identifier}/decide",
        response_model=AuthorityEnvelope[ApprovalView],
        response_model_exclude_none=True,
    )
    def decide(
        workspace_id: UUID,
        identifier: UUID,
        body: DecideAuthority,
        request: Request,
        if_match: int = Header(ge=1),
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, write=True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            commands.founder(conn, actor)
            result = commands.idempotent(
                conn,
                "decide",
                request.headers["idempotency-key"],
                {**body.model_dump(mode="json"), "id": str(identifier), "version": if_match},
                lambda: commands.decide(
                    conn, identifier, if_match, body, actor, request.state.request_id
                ),
            )
        return {"data": result}

    @api.post(
        prefix + "/approvals/{identifier}/execute",
        response_model=AuthorityEnvelope[AuthorityResult],
        response_model_exclude_none=True,
    )
    def execute(
        workspace_id: UUID,
        identifier: UUID,
        body: ExecuteAuthority,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, write=True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            result = commands.idempotent(
                conn,
                "execute",
                request.headers["idempotency-key"],
                {**body.model_dump(mode="json"), "id": str(identifier)},
                lambda: commands.execute(conn, identifier, body, request.state.request_id),
                recheck=True,
            )
        return {"data": result}

    @api.post(
        prefix + "/approvals/{identifier}/revoke",
        response_model=AuthorityEnvelope[ApprovalView],
        response_model_exclude_none=True,
    )
    def revoke(
        workspace_id: UUID,
        identifier: UUID,
        body: Reason,
        request: Request,
        if_match: int = Header(ge=1),
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, write=True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            commands.gate(conn)
            commands.founder(conn, actor, mfa=False)

            def withdraw() -> dict[str, Any]:
                item = get(conn, "approval_requests", identifier, lock=True)
                if item["record_version"] != if_match:
                    raise BusinessError("VERSION_CONFLICT")
                insert(
                    conn,
                    "approval_decisions",
                    {
                        "request_id": identifier,
                        "decision": "revoke",
                        "session_id": actor.session_id,
                        "rationale": body.rationale,
                        "correlation_id": request.state.request_id,
                    },
                )
                changed = update(conn, "approval_requests", item, state="revoked")
                commands.emit(conn, changed, "approval.revoked", request.state.request_id)
                return changed

            result = commands.idempotent(
                conn,
                "revoke",
                request.headers["idempotency-key"],
                {**body.model_dump(mode="json"), "id": str(identifier), "version": if_match},
                withdraw,
            )
        return {"data": result}

    @api.post(
        prefix + "/authority/freeze",
        response_model=AuthorityEnvelope[FreezeView],
        response_model_exclude_none=True,
    )
    def freeze(
        workspace_id: UUID,
        body: FreezeAuthority,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        w = scope(request, actor, workspace_id, write=True)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, w["authz_epoch"]
        ) as conn:
            commands.gate(conn)
            commands.founder(conn, actor, mfa=False)
            result = commands.idempotent(
                conn,
                "freeze",
                request.headers["idempotency-key"],
                body.model_dump(mode="json"),
                lambda: insert(
                    conn,
                    "authority_freezes",
                    {**body.model_dump(), "correlation_id": request.state.request_id},
                ),
            )
        return {"data": result}
