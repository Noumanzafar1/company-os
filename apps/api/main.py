import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from company_os.adapters.auth import JWTIdentityProvider
from company_os.adapters.local_documents import FakeDocumentStore
from company_os.application.business import CoreCommands
from company_os.application.identity import IdentityService, digest
from company_os.config import Settings
from company_os.contracts import (
    Component,
    Envelope,
    ErrorEnvelope,
    FoundationHealth,
    Meta,
    Probe,
    Profile,
    SessionInput,
    SessionOutput,
    Workspace,
)
from company_os.domain.identity import AccessDenied, AuthenticationFailed, SessionIdentity
from company_os.persistence.business import BusinessError
from company_os.persistence.database import check_runtime, make_engine, transaction
from company_os.policy.access import require_permission
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.authority import register as register_authority
from apps.api.business import register
from apps.api.runtime import register as register_runtime


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        config = settings or Settings()  # type: ignore[call-arg]
        engine = make_engine(config.database_url.get_secret_value())
        with transaction(engine) as conn:
            check_runtime(conn, "company_api")
        api.state.config = config
        api.state.engine = engine
        api.state.identity = IdentityService(engine, JWTIdentityProvider(config))
        api.state.commands = CoreCommands(
            engine, api.state.identity, FakeDocumentStore(Path(".local/documents"))
        )
        yield
        engine.dispose()

    api = FastAPI(
        title="Company OS Foundation",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        responses={status: {"model": ErrorEnvelope} for status in (400, 401, 403, 404, 422, 503)},
    )

    @api.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = uuid4()
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request.state.request_id)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": str(request.state.request_id),
                    "retryable": status == 503,
                }
            },
        )

    @api.exception_handler(AuthenticationFailed)
    async def unauthenticated(request: Request, exc: AuthenticationFailed) -> JSONResponse:
        return error(request, 401, "UNAUTHENTICATED", "Sign in required.")

    @api.exception_handler(BusinessError)
    async def business_error(request: Request, exc: BusinessError) -> JSONResponse:
        return error(
            request,
            exc.status,
            exc.code,
            "Resource unavailable." if exc.status == 404 else "Command could not be completed.",
        )

    @api.exception_handler(AccessDenied)
    async def denied(request: Request, exc: AccessDenied) -> JSONResponse:
        return error(request, 403, "FORBIDDEN", "Request denied.")

    @api.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {
            400: "INVALID_REQUEST",
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
        }
        return error(
            request,
            exc.status_code,
            codes.get(exc.status_code, "INVALID_REQUEST"),
            "Resource unavailable." if exc.status_code == 404 else "Request denied.",
        )

    @api.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never return submitted values or credential-bearing validation input.
        return error(request, 422, "VALIDATION_FAILED", "Request did not match the contract.")

    @api.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return error(request, 503, "DEPENDENCY_UNAVAILABLE", "Service temporarily unavailable.")

    def bearer(request: Request) -> str:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer ") or len(header) > 8192:
            raise AuthenticationFailed()
        return header[7:]

    def authenticated(request: Request) -> SessionIdentity:
        return request.app.state.identity.resolve(bearer(request))  # type: ignore[no-any-return]

    def meta(
        request: Request, workspace_id: UUID | None = None, version: int | None = None
    ) -> Meta:
        return Meta(
            request_id=request.state.request_id,
            workspace_id=workspace_id,
            as_of=datetime.now(UTC),
            record_version=version,
        )

    def dto(item: dict[str, Any]) -> Workspace:
        return Workspace.model_validate(
            {key: value for key, value in item.items() if key != "authz_epoch"}
        )

    @api.get("/health/live", response_model=Probe)
    def live() -> Probe:
        return Probe(status="ok")

    @api.get("/health/ready", response_model=Probe, responses={503: {"model": Probe}})
    def ready(request: Request, response: Response) -> Probe:
        try:
            with transaction(request.app.state.engine) as conn:
                check_runtime(conn, "company_api")
            return Probe(status="ok")
        except (SQLAlchemyError, RuntimeError):
            response.status_code = 503
            return Probe(status="unavailable")

    @api.post("/v1/auth/session", response_model=SessionOutput)
    def bootstrap_session(body: SessionInput, request: Request) -> SessionOutput:
        supplied = request.headers.get("x-console-secret", "")
        if not secrets.compare_digest(
            supplied, request.app.state.config.console_secret.get_secret_value()
        ):
            raise HTTPException(403)
        return SessionOutput(
            session_token=request.app.state.identity.start(bearer(request), body.csrf_token)
        )

    @api.get("/v1/me", response_model=Envelope[Profile])
    def me(
        request: Request, identity: SessionIdentity = Depends(authenticated)
    ) -> Envelope[Profile]:
        data = request.app.state.identity.profile(identity)
        data["workspaces"] = [dto(w) for w in data["workspaces"]]
        return Envelope(data=Profile(**data), meta=meta(request))

    @api.get("/v1/workspaces/{workspace_id}", response_model=Envelope[Workspace])
    def workspace(
        workspace_id: UUID, request: Request, identity: SessionIdentity = Depends(authenticated)
    ) -> Envelope[Workspace]:
        found = request.app.state.identity.workspace(identity, workspace_id)
        if found is None:
            raise HTTPException(404)
        return Envelope(data=dto(found), meta=meta(request, workspace_id, found["record_version"]))

    @api.get("/v1/workspaces/{workspace_id}/health", response_model=Envelope[FoundationHealth])
    def health(
        workspace_id: UUID, request: Request, identity: SessionIdentity = Depends(authenticated)
    ) -> Envelope[FoundationHealth]:
        found = request.app.state.identity.workspace(identity, workspace_id)
        if found is None:
            raise HTTPException(404)
        require_permission(found["permissions"], "system.read")
        components = [
            Component(name=name, status="healthy") for name in ["API", "Database", "Authentication"]
        ]
        components.extend(
            Component(name=name, status="not_configured")
            for name in [
                "CRM",
                "Sequencer",
                "Research",
                "Verification",
                "Documents",
                "Calendar",
                "AI",
            ]
        )
        return Envelope(
            data=FoundationHealth(components=components), meta=meta(request, workspace_id)
        )

    @api.post("/v1/auth/logout", status_code=204)
    def logout(request: Request) -> Response:
        token = bearer(request)
        csrf = request.headers.get("x-csrf-token", "")
        if (
            request.headers.get("origin") != request.app.state.config.console_origin
            or len(csrf) != 64
        ):
            raise HTTPException(403)
        try:
            identity = request.app.state.identity.resolve(token)
        except AuthenticationFailed:
            return Response(status_code=204)  # Session-local idempotency.
        if not secrets.compare_digest(identity.csrf_hash, digest(csrf)):
            raise HTTPException(403)
        request.app.state.identity.logout(token, csrf, request.state.request_id)
        return Response(status_code=204)

    register(api, authenticated)
    register_runtime(api, authenticated)
    register_authority(api, authenticated)
    return api


app = create_app()
