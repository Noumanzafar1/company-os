import hashlib
import secrets
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from company_os.application.ports import IdentityProvider
from company_os.domain.identity import AuthenticationFailed, SessionIdentity
from company_os.persistence.database import rows, transaction


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class IdentityService:
    def __init__(self, engine: Engine, provider: IdentityProvider) -> None:
        self.engine = engine
        self.provider = provider

    def start(self, token: str, csrf: str) -> str:
        identity = self.provider.verify(token)
        session = secrets.token_urlsafe(48)
        with transaction(self.engine) as conn:
            principal = conn.execute(
                text("""
                SELECT app.open_session(:subject,:id,:hash,:csrf,:aal,:mfa)
            """),
                {
                    "subject": identity.subject,
                    "id": uuid4(),
                    "hash": digest(session),
                    "csrf": digest(csrf),
                    "aal": identity.assurance,
                    "mfa": identity.mfa_at,
                },
            ).scalar_one()
            if principal is None:
                raise AuthenticationFailed("Uninvited or disabled identity")
        return session

    def resolve(self, token: str) -> SessionIdentity:
        with transaction(self.engine) as conn:
            found = rows(conn, "SELECT * FROM app.resolve_session(:hash)", {"hash": digest(token)})
        if not found:
            raise AuthenticationFailed("Session unavailable")
        return SessionIdentity(**found[0])

    def profile(self, identity: SessionIdentity) -> dict[str, Any]:
        with transaction(self.engine, identity.principal_id) as conn:
            profile = rows(conn, "SELECT * FROM app.profile()")
            workspaces = rows(conn, "SELECT * FROM app.authorized_workspaces()")
        if not profile:
            raise AuthenticationFailed("Session unavailable")
        return {**profile[0], "assurance": identity.assurance, "workspaces": workspaces}

    def workspace(self, identity: SessionIdentity, workspace_id: UUID) -> dict[str, Any] | None:
        # Route IDs only select among memberships fetched from verified server identity.
        profile = self.profile(identity)
        candidate = next((w for w in profile["workspaces"] if w["id"] == workspace_id), None)
        if candidate is None or "workspace.read" not in candidate["permissions"]:
            return None
        with transaction(
            self.engine, identity.principal_id, workspace_id, candidate["authz_epoch"]
        ) as conn:
            visible = rows(conn, "SELECT id FROM app.workspaces WHERE id=:id", {"id": workspace_id})
        return candidate if visible else None

    def logout(self, token: str, csrf: str, request_id: UUID) -> None:
        with transaction(self.engine) as conn:
            conn.execute(
                text("SELECT app.close_session(:hash,:csrf,:rid)"),
                {"hash": digest(token), "csrf": digest(csrf), "rid": request_id},
            )
