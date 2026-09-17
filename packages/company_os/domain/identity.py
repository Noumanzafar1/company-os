from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: str
    assurance: Literal["aal1", "aal2"]
    mfa_at: datetime | None = None


@dataclass(frozen=True)
class SessionIdentity:
    principal_id: UUID
    session_id: UUID
    assurance: str
    mfa_at: datetime | None
    csrf_hash: str


class AuthenticationFailed(Exception):
    """No valid, current application identity could be established."""


class AccessDenied(Exception):
    """An authenticated identity lacks permission or required assurance."""
