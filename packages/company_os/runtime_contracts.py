"""Closed Phase 4 contracts. No provider methods or arbitrary payload input."""

from datetime import UTC
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, Field

from company_os.contracts import Model

UtcTime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]

Scenario = Literal[
    "success",
    "transient",
    "invalid",
    "exhausted",
    "wait",
    "effect_success",
    "effect_rejected",
    "effect_lost",
    "effect_unknown",
    "safety",
    "reconcile",
]


class SyntheticInput(Model):
    scenario: Scenario
    logical_key: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9_.:-]+$")


class RuntimeCommand(Model):
    reason: str = Field(min_length=5, max_length=500)
    cause_changed: bool = False


class FakeCallback(Model):
    event_key: str = Field(min_length=1, max_length=200)
    schema_version: int = Field(ge=1, le=100)
    external_id: UUID
    version: int = Field(ge=1)
    observation: Literal["active", "stopped"]
    occurred_at: UtcTime
    workspace_id: UUID | None = None


class SnoozeInput(Model):
    until: UtcTime
    reason: str = Field(min_length=5, max_length=500)


class JobView(Model):
    id: UUID
    workspace_id: UUID
    record_version: int
    job_type: str
    state: str
    priority: str
    input_ref: UUID
    origin_event_id: UUID | None
    workflow_run_id: UUID | None
    correlation_id: UUID
    attempt_count: int
    max_attempts: int
    fence: int
    lease_owner: str | None
    lease_expires_at: UtcTime | None
    available_at: UtcTime
    created_at: UtcTime
    deadline_at: UtcTime
    last_error_code: str | None
    effect_id: UUID | None
    recovery_of_id: UUID | None
    coalesced_effect_id: UUID | None


class EventView(Model):
    workspace_id: UUID
    received_at: UtcTime
    actor_id: UUID
    actor_type: str
    origin: str
    classification: str
    payload: dict[str, str | int | list[str] | None]
    payload_ref: UUID | None
    id: UUID
    event_type: str
    schema_version: int
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int
    occurred_at: UtcTime
    correlation_id: UUID
    causation_id: UUID | None
    trace_id: str


class AttemptView(Model):
    id: UUID
    attempt_no: int
    worker_id: str
    fence: int
    phase: str
    started_at: UtcTime
    ended_at: UtcTime | None
    outcome: str
    error_code: str | None


class EffectView(Model):
    id: UUID
    job_id: UUID
    state: str
    effect_key: str
    request_hash: str
    receipt_hash: str | None
    provider_request_id: str | None
    reconcile_after: UtcTime | None
    reservation_id: UUID | None


class JobDetail(Model):
    job: JobView
    attempts: list[AttemptView]
    effect: EffectView | None
    events: list[EventView]


class IncidentView(Model):
    id: UUID
    record_version: int
    severity: str
    kind: str
    state: str
    opened_at: UtcTime
    resolved_at: UtcTime | None
    owner_id: UUID


class Submitted(Model):
    id: UUID
    scenario: Scenario
    logical_key: str


class CallbackReceipt(Model):
    id: UUID
    state: str


class HealthComponent(Model):
    name: str
    status: Literal["GREEN", "AMBER", "RED", "UNKNOWN"]
    age_seconds: float | None = None
    count: int | None = None


class QueueCount(Model):
    state: str
    priority: str
    count: int
    oldest: UtcTime


class BudgetView(Model):
    id: UUID
    category: str
    limit_usd: str
    reserved_usd: str
    spent_usd: str
    status: str


class UncertainView(Model):
    id: UUID
    state: str
    dispatch_started_at: UtcTime | None
    reconcile_after: UtcTime | None
    job_id: UUID


class RuntimeHealth(Model):
    threshold_version: str
    as_of: UtcTime
    status: Literal["GREEN", "AMBER", "RED", "UNKNOWN"]
    components: list[HealthComponent]
    queues: list[QueueCount]
    uncertain_effects: list[UncertainView]
    budgets: list[BudgetView]
    incidents: list[IncidentView]
    integrations: str


class CompletionInput(Model):
    connection_id: UUID
    expected_fence: int = Field(ge=1)
    result_ref: UUID


class AttentionView(Model):
    id: UUID
    record_version: int
    incident_id: UUID
    state: str
    snooze_until: UtcTime | None
    reason: str | None
