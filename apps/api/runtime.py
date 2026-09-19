"""Scoped runtime inspection and explicit synthetic/control commands."""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from company_os import runtime_contracts as dto
from company_os.application import long_tasks, webhooks
from company_os.application import runtime as commands
from company_os.application.identity import digest
from company_os.contracts import Envelope, Meta
from company_os.domain.identity import AccessDenied, SessionIdentity
from company_os.long_contracts import LongSubmission
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows, transaction
from company_os.persistence.runtime import get
from company_os.policy.access import require_permission
from company_os.reporting.runtime import health
from fastapi import Depends, FastAPI, Header, Query, Request, Response
from pydantic import ValidationError


def view(model: Any, item: dict[str, Any]) -> Any:
    return model.model_validate({k: item[k] for k in model.model_fields})


def register(api: FastAPI, authenticated: Callable[..., SessionIdentity]) -> None:
    prefix = "/v1/workspaces/{workspace_id}"

    def scope(request: Request, actor: SessionIdentity, workspace_id: UUID) -> dict[str, Any]:
        workspace = request.app.state.identity.workspace(actor, workspace_id)
        if workspace is None:
            raise BusinessError("NOT_FOUND", 404)
        require_permission(workspace["permissions"], "system.read")
        return workspace  # type: ignore[no-any-return]

    def meta(request: Request, w: UUID) -> Meta:
        return Meta(request_id=request.state.request_id, workspace_id=w, as_of=datetime.now(UTC))

    def mutation(request: Request, actor: SessionIdentity, workspace: dict[str, Any]) -> None:
        if not {"founder", "system_administrator"}.intersection(workspace["roles"]):
            raise AccessDenied()
        if request.headers.get(
            "origin"
        ) != request.app.state.config.console_origin or not secrets.compare_digest(
            digest(request.headers.get("x-csrf-token", "")), actor.csrf_hash
        ):
            raise AccessDenied()
        key = request.headers.get("idempotency-key", "")
        if not 8 <= len(key) <= 128:
            raise BusinessError("IDEMPOTENCY_KEY_REQUIRED", 400)

    @api.get(prefix + "/jobs", response_model=Envelope[list[dto.JobView]])
    def jobs(
        workspace_id: UUID,
        request: Request,
        state: str | None = Query(default=None, max_length=30),
        limit: int = Query(default=50, ge=1, le=200),
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            result = rows(
                conn,
                "SELECT * FROM app.jobs WHERE (CAST(:state AS text) IS NULL OR state=CAST(:state AS text)) ORDER BY created_at DESC,id LIMIT :limit",
                {"state": state, "limit": limit},
            )
        return Envelope(
            data=[view(dto.JobView, x) for x in result], meta=meta(request, workspace_id)
        )

    @api.get(prefix + "/jobs/{identifier}", response_model=Envelope[dto.JobDetail])
    def job_detail(
        workspace_id: UUID,
        identifier: UUID,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            job = get(conn, "jobs", identifier)
            attempts = rows(
                conn,
                "SELECT * FROM app.job_attempts WHERE job_id=:id ORDER BY attempt_no,phase DESC",
                {"id": identifier},
            )
            effect_ref = job["effect_id"] or job["coalesced_effect_id"]
            effect = get(conn, "external_effects", effect_ref) if effect_ref else None
            executions = rows(
                conn,
                "SELECT id,attempt_id,fence,state,outcome,created_at,ended_at,(details->>'forced')::boolean AS forced,(details->>'elapsed_ms')::float AS elapsed_ms FROM app.long_executions WHERE job_id=:id ORDER BY created_at LIMIT 100",
                {"id": identifier},
            )
            events = rows(
                conn,
                "SELECT * FROM app.events WHERE correlation_id=:c OR aggregate_id=:id ORDER BY created_at LIMIT 200",
                {"c": job["correlation_id"], "id": identifier},
            )
        return Envelope(
            data=dto.JobDetail(
                job=view(dto.JobView, job),
                attempts=[view(dto.AttemptView, x) for x in attempts],
                effect=view(dto.EffectView, effect) if effect else None,
                events=[view(dto.EventView, x) for x in events],
                long_executions=[view(dto.LongExecutionView, x) for x in executions],
            ),
            meta=meta(request, workspace_id),
        )

    @api.get(prefix + "/events", response_model=Envelope[list[dto.EventView]])
    def events(
        workspace_id: UUID,
        request: Request,
        correlation_id: UUID | None = None,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            items = rows(
                conn,
                "SELECT * FROM app.events WHERE (CAST(:c AS uuid) IS NULL OR correlation_id=:c) ORDER BY created_at DESC LIMIT 200",
                {"c": correlation_id},
            )
        return Envelope(
            data=[view(dto.EventView, x) for x in items], meta=meta(request, workspace_id)
        )

    @api.get(prefix + "/incidents", response_model=Envelope[list[dto.IncidentView]])
    def incidents(
        workspace_id: UUID, request: Request, actor: SessionIdentity = Depends(authenticated)
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            items = rows(conn, "SELECT * FROM app.incidents ORDER BY opened_at DESC LIMIT 200")
        return Envelope(
            data=[view(dto.IncidentView, x) for x in items], meta=meta(request, workspace_id)
        )

    @api.get(prefix + "/runtime-health", response_model=Envelope[dto.RuntimeHealth])
    def runtime_health(
        workspace_id: UUID, request: Request, actor: SessionIdentity = Depends(authenticated)
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            result = health(conn)
        return Envelope(data=result, meta=meta(request, workspace_id))

    @api.post(prefix + "/runtime/synthetic", response_model=Envelope[dto.Submitted])
    def submit(
        workspace_id: UUID,
        body: dto.SyntheticInput,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        mutation(request, actor, workspace)
        if request.app.state.config.company_env not in {"development", "test"}:
            raise AccessDenied()
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            item = commands.idempotent(
                conn,
                actor.principal_id,
                request.headers["idempotency-key"],
                "runtime.synthetic",
                body.model_dump(mode="json"),
                "runtime_inputs",
                lambda: commands.submit(conn, body, request.state.request_id),
            )
        return Envelope(data=view(dto.Submitted, item), meta=meta(request, workspace_id))

    @api.post(prefix + "/runtime/long-tasks", response_model=Envelope[dto.Submitted])
    def long_submit(
        workspace_id: UUID,
        body: LongSubmission,
        request: Request,
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        mutation(request, actor, workspace)
        if request.app.state.config.company_env not in {"development", "test"}:
            raise AccessDenied()
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            item = commands.idempotent(
                conn,
                actor.principal_id,
                request.headers["idempotency-key"],
                "runtime.long",
                body.model_dump(mode="json"),
                "runtime_inputs",
                lambda: long_tasks.submit(conn, body, request.state.request_id),
            )
        return Envelope(data=view(dto.Submitted, item), meta=meta(request, workspace_id))

    def control(action: str) -> Callable[..., Any]:
        def endpoint(
            workspace_id: UUID,
            identifier: UUID,
            body: dto.RuntimeCommand,
            request: Request,
            if_match: int = Header(ge=1),
            actor: SessionIdentity = Depends(authenticated),
        ) -> Any:
            workspace = scope(request, actor, workspace_id)
            mutation(request, actor, workspace)
            with transaction(
                request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
            ) as conn:
                item = commands.idempotent(
                    conn,
                    actor.principal_id,
                    request.headers["idempotency-key"],
                    "runtime." + action,
                    {
                        **body.model_dump(mode="json"),
                        "target": str(identifier),
                        "version": if_match,
                    },
                    "jobs",
                    lambda: (
                        commands.retry(conn, identifier, if_match, body.reason, body.cause_changed)
                        if action == "retry"
                        else commands.cancel(conn, identifier, if_match, body.reason)
                    ),
                )
            return Envelope(data=view(dto.JobView, item), meta=meta(request, workspace_id))

        endpoint.__name__ = "job_" + action
        return endpoint

    for action in ("retry", "cancel"):
        api.post(prefix + "/jobs/{identifier}/" + action, response_model=Envelope[dto.JobView])(
            control(action)
        )

    @api.post("/webhooks/fake/{connection_token}", response_model=dto.CallbackReceipt)
    async def callback(connection_token: UUID, request: Request, response: Response) -> Any:
        config = request.app.state.config
        if config.company_env not in {"development", "test"}:
            raise AccessDenied()
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                raise BusinessError("PAYLOAD_TOO_LARGE", 413)
        secret = config.fake_webhook_secret.get_secret_value()
        webhooks.authenticate(
            secret,
            bytes(body),
            request.headers.get("x-fake-timestamp", ""),
            request.headers.get("x-fake-signature", ""),
            datetime.now(UTC),
        )
        with transaction(request.app.state.engine) as conn:
            contexts = rows(
                conn, "SELECT * FROM app.fake_callback_context(:id)", {"id": connection_token}
            )
        if not contexts:
            raise BusinessError("NOT_FOUND", 404)
        context = contexts[0]
        try:
            with transaction(
                request.app.state.engine,
                context["principal_id"],
                context["workspace_id"],
                context["authz_epoch"],
            ) as conn:
                item = webhooks.receive(conn, connection_token, bytes(body), secret)
        except ValidationError as error:
            raise BusinessError("INVALID_CALLBACK_SCHEMA", 422) from error
        response.status_code = 202
        return view(dto.CallbackReceipt, item)

    @api.get(prefix + "/attention", response_model=Envelope[list[dto.AttentionView]])
    def attention(
        workspace_id: UUID, request: Request, actor: SessionIdentity = Depends(authenticated)
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            items = rows(
                conn,
                "SELECT * FROM app.runtime_attention WHERE state<>'resolved' ORDER BY created_at LIMIT 200",
            )
        return Envelope(
            data=[view(dto.AttentionView, x) for x in items], meta=meta(request, workspace_id)
        )

    @api.post(prefix + "/attention/{identifier}/snooze", response_model=Envelope[dto.AttentionView])
    def snooze(
        workspace_id: UUID,
        identifier: UUID,
        body: dto.SnoozeInput,
        request: Request,
        if_match: int = Header(ge=1),
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        if "founder" not in workspace["roles"]:
            raise AccessDenied()
        mutation(request, actor, workspace)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            item = commands.idempotent(
                conn,
                actor.principal_id,
                request.headers["idempotency-key"],
                "runtime.snooze",
                {**body.model_dump(mode="json"), "target": str(identifier), "version": if_match},
                "runtime_attention",
                lambda: commands.snooze(conn, identifier, if_match, body.until, body.reason),
            )
        return Envelope(data=view(dto.AttentionView, item), meta=meta(request, workspace_id))

    @api.post("/service/jobs/{identifier}/result", response_model=dto.CallbackReceipt)
    async def completion(identifier: UUID, request: Request) -> Any:
        config = request.app.state.config
        if config.company_env not in {"development", "test"}:
            raise AccessDenied()
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise BusinessError("PAYLOAD_TOO_LARGE", 413)
        webhooks.authenticate(
            config.fake_webhook_secret.get_secret_value(),
            bytes(body),
            request.headers.get("x-fake-timestamp", ""),
            request.headers.get("x-fake-signature", ""),
            datetime.now(UTC),
        )
        try:
            payload = dto.CompletionInput.model_validate_json(body)
        except ValidationError as error:
            raise BusinessError("INVALID_CALLBACK_SCHEMA", 422) from error
        with transaction(request.app.state.engine) as conn:
            contexts = rows(
                conn, "SELECT * FROM app.fake_callback_context(:id)", {"id": payload.connection_id}
            )
        if not contexts:
            raise BusinessError("NOT_FOUND", 404)
        ctx = contexts[0]
        with transaction(
            request.app.state.engine, ctx["principal_id"], ctx["workspace_id"], ctx["authz_epoch"]
        ) as conn:
            item = commands.complete_callback(
                conn, identifier, payload.expected_fence, payload.result_ref
            )
        return dto.CallbackReceipt(id=item["id"], state="received")
