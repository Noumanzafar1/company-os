from datetime import UTC, datetime, timedelta

from company_os.domain.identity import AccessDenied, SessionIdentity

PERMISSIONS = frozenset(
    {
        "workspace.read",
        "system.read",
        "approval.grant",
        "business.read",
        "business.write",
        "identity.review",
    }
)


def require_permission(permissions: list[str], permission: str) -> None:
    if permission not in PERMISSIONS or permission not in permissions:
        raise AccessDenied("Permission denied")


def require_recent_mfa(identity: SessionIdentity) -> None:
    now = datetime.now(UTC)
    if (
        identity.assurance != "aal2"
        or identity.mfa_at is None
        or not now - timedelta(minutes=10) <= identity.mfa_at <= now
    ):
        raise AccessDenied("Recent MFA required")
