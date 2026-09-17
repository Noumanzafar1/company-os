from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Meta(Model):
    request_id: UUID
    workspace_id: UUID | None = None
    as_of: datetime
    source: str = "company_os"
    freshness: Literal["current", "missing"] = "current"
    record_version: int | None = None


class Envelope[T](Model):
    data: T
    meta: Meta


class Workspace(Model):
    id: UUID
    name: str
    kind: Literal["acquisition", "client_delivery", "partners"]
    record_version: int
    roles: list[str]
    permissions: list[str]


class Profile(Model):
    principal_id: UUID
    display_name: str
    assurance: str
    workspaces: list[Workspace]


class SessionInput(Model):
    csrf_token: str = Field(pattern=r"^[a-f0-9]{64}$")


class SessionOutput(Model):
    session_token: str
    expires_in: int = 43200


class Probe(Model):
    status: Literal["ok", "unavailable"]


class Component(Model):
    name: str
    status: Literal["healthy", "not_configured"]


class FoundationHealth(Model):
    components: list[Component]
    live_sending: Literal[False] = False


class ErrorDetail(Model):
    code: str
    message: str
    request_id: UUID
    retryable: bool


class ErrorEnvelope(Model):
    error: ErrorDetail


class RetentionPolicy(Model):
    version: Literal[1] = 1
    profiles: dict[Literal["R1", "R2", "R3", "R4", "R5", "R6", "R7"], int]
    review_owner_role: Literal["founder"] = "founder"


class RegionPolicy(Model):
    version: Literal[1] = 1
    allowed_processing_regions: list[str] = Field(default_factory=list)
    allowed_recipient_countries: list[str] = Field(default_factory=list)
    channel_policies: list[None] = Field(default_factory=list, max_length=0)
