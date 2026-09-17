import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from company_os import business_contracts as dto
from company_os.application.identity import digest
from company_os.contracts import Envelope, Meta, Model
from company_os.domain.identity import AccessDenied, SessionIdentity
from company_os.persistence.business import BusinessError, get
from company_os.persistence.database import transaction
from company_os.policy.access import require_permission
from company_os.reporting import business as report
from fastapi import Depends, FastAPI, Query, Request


def register(api: FastAPI, authenticated: Callable[..., SessionIdentity]) -> None:
    prefix = "/v1/workspaces/{workspace_id}"

    def scope(request: Request, actor: SessionIdentity, workspace_id: UUID) -> dict[str, Any]:
        found = request.app.state.identity.workspace(actor, workspace_id)
        if found is None:
            raise BusinessError("NOT_FOUND", 404)
        require_permission(found["permissions"], "business.read")
        return found  # type: ignore[no-any-return]

    def meta(request: Request, workspace_id: UUID) -> Meta:
        return Meta(
            request_id=request.state.request_id, workspace_id=workspace_id, as_of=datetime.now(UTC)
        )

    def add_collection(path: str, table: str, model: Any) -> None:
        def endpoint(
            workspace_id: UUID,
            request: Request,
            cursor: str | None = Query(default=None, max_length=2000),
            limit: int = Query(default=50, ge=1, le=200),
            actor: SessionIdentity = Depends(authenticated),
        ) -> Any:
            workspace = scope(request, actor, workspace_id)
            with transaction(
                request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
            ) as conn:
                items, next_cursor = report.page(
                    conn,
                    table,
                    cursor,
                    limit,
                    request.app.state.config.console_secret.get_secret_value(),
                    actor.principal_id,
                    workspace_id,
                )
                request.app.state.commands.audit(
                    conn,
                    actor,
                    request.state.request_id,
                    request.state.request_id,
                    f"{table}.read",
                    workspace_id,
                    "0" * 64,
                    "allow",
                    "read",
                )
            return {"data": items, "meta": meta(request, workspace_id), "next_cursor": next_cursor}

        endpoint.__name__ = f"list_{table}"
        api.get(prefix + path, response_model=dto.PageEnvelope[model])(endpoint)

    def add_detail(path: str, table: str, model: Any) -> None:
        def endpoint(
            workspace_id: UUID,
            identifier: UUID,
            request: Request,
            actor: SessionIdentity = Depends(authenticated),
        ) -> Any:
            workspace = scope(request, actor, workspace_id)
            with transaction(
                request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
            ) as conn:
                if table == "accounts":
                    value: Any = report.account_detail(conn, identifier)
                elif table == "scores":
                    value = report.score(conn, identifier)
                else:
                    value = report.view(conn, table, get(conn, table, identifier))
                request.app.state.commands.audit(
                    conn,
                    actor,
                    request.state.request_id,
                    request.state.request_id,
                    f"{table}.read",
                    identifier,
                    "0" * 64,
                    "allow",
                    "read",
                )
            return Envelope(data=value, meta=meta(request, workspace_id))

        endpoint.__name__ = f"detail_{table}"
        api.get(prefix + path + "/{identifier}", response_model=Envelope[model])(endpoint)

    for path, table, model in [
        ("/accounts", "accounts", dto.AccountView),
        ("/people", "people", dto.PersonView),
        ("/leads", "leads", dto.LeadView),
        ("/evidence", "evidence", dto.EvidenceView),
        ("/signals", "signals", dto.SignalView),
        ("/sources", "data_sources", dto.SourceView),
        ("/documents", "documents", dto.DocumentView),
    ]:
        add_collection(path, table, model)
        add_detail(path, table, dto.AccountDetail if table == "accounts" else model)
    add_detail("/scores", "scores", dto.ScoreView)
    add_detail("/icp-versions", "icp_versions", dto.ICPVersionView)
    add_detail("/offer-versions", "offer_versions", dto.OfferVersionView)

    @api.get(prefix + "/knowledge/search", response_model=Envelope[list[dto.KnowledgeHit]])
    def knowledge(
        workspace_id: UUID,
        request: Request,
        q: str = Query(min_length=1, max_length=200),
        limit: int = Query(default=20, ge=1, le=20),
        actor: SessionIdentity = Depends(authenticated),
    ) -> Any:
        workspace = scope(request, actor, workspace_id)
        with transaction(
            request.app.state.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
        ) as conn:
            value = report.search(conn, q, limit)
            request.app.state.commands.audit(
                conn,
                actor,
                request.state.request_id,
                request.state.request_id,
                "knowledge.read",
                workspace_id,
                "0" * 64,
                "allow",
                "read",
            )
            return Envelope(data=value, meta=meta(request, workspace_id))

    def add_command(path: str, command: str, model: Any, existing: bool = False) -> None:
        def execute(
            body: Model,
            workspace_id: UUID,
            request: Request,
            actor: SessionIdentity,
            identifier: UUID | None,
        ) -> dto.CommandResult:
            csrf = request.headers.get("x-csrf-token", "")
            if request.headers.get(
                "origin"
            ) != request.app.state.config.console_origin or not secrets.compare_digest(
                actor.csrf_hash, digest(csrf)
            ):
                raise AccessDenied()
            version = None
            if existing:
                try:
                    version = int(request.headers.get("if-match", "").strip('"'))
                    if version <= 0:
                        raise ValueError()
                except ValueError:
                    raise BusinessError("VERSION_REQUIRED", 400) from None
            return request.app.state.commands.execute(
                actor,
                workspace_id,
                command,
                body,
                request.headers.get("idempotency-key", ""),
                target=identifier,
                version=version,
                request_id=request.state.request_id,
            )  # type: ignore[no-any-return]

        endpoint: Any
        if existing:

            def existing_endpoint(
                body: Any,
                workspace_id: UUID,
                identifier: UUID,
                request: Request,
                actor: SessionIdentity = Depends(authenticated),
            ) -> dto.CommandResult:
                return execute(body, workspace_id, request, actor, identifier)

            endpoint = existing_endpoint
        else:

            def create_endpoint(
                body: Any,
                workspace_id: UUID,
                request: Request,
                actor: SessionIdentity = Depends(authenticated),
            ) -> dto.CommandResult:
                return execute(body, workspace_id, request, actor, None)

            endpoint = create_endpoint

        endpoint.__annotations__["body"] = model
        endpoint.__name__ = command.replace(".", "_")
        api.post(prefix + path, response_model=dto.CommandResult)(endpoint)

    for path, command, model, existing in [
        ("/accounts", "account.create", dto.AccountInput, False),
        ("/accounts/{identifier}/propose-correction", "account.correct", dto.CorrectionInput, True),
        ("/people", "person.create", dto.PersonInput, False),
        ("/employments", "employment.create", dto.EmploymentInput, False),
        ("/contact-points", "contact.create", dto.ContactInput, False),
        ("/evidence", "evidence.create", dto.EvidenceInput, False),
        ("/evidence/{identifier}/retract", "evidence.retract", dto.RetractionInput, True),
        ("/signals", "signal.create", dto.SignalInput, False),
        ("/signals/{identifier}/accept", "signal.accept", dto.ReasonInput, True),
        ("/icps", "icp.create", dto.NamedInput, False),
        ("/icps/{identifier}/versions", "icp.version", dto.ICPVersionInput, True),
        ("/offers", "offer.create", dto.NamedInput, False),
        ("/offers/{identifier}/versions", "offer.version", dto.OfferVersionInput, True),
        ("/leads", "lead.create", dto.LeadInput, False),
        ("/leads/{identifier}/begin-research", "lead.begin-research", dto.ReasonInput, True),
        (
            "/leads/{identifier}/complete-research",
            "lead.complete-research",
            dto.ResearchInput,
            True,
        ),
        ("/leads/{identifier}/disqualify", "lead.disqualify", dto.ReasonInput, True),
        ("/leads/{identifier}/archive", "lead.archive", dto.ReasonInput, True),
        ("/scores/calculate", "score.calculate", dto.ScoreInput, False),
        ("/documents/register", "document.register", dto.DocumentInput, False),
        ("/identities/merge", "identity.merge", dto.MergeInput, False),
        ("/identities/merges/{identifier}/reverse", "identity.reverse", dto.ReversalInput, True),
    ]:
        add_command(path, command, model, existing)
