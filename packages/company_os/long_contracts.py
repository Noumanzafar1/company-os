"""Closed synthetic execution transport. No destinations, code or credentials."""

from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from company_os.contracts import Model

Handler = Literal[
    "immediate_success",
    "sleep_success",
    "cooperative_cancel",
    "ignore_cancel",
    "infinite_cpu",
    "child_crash",
    "abrupt_exit",
    "malformed_result",
    "no_result",
    "corrupted_result",
    "oversized_result",
    "transient_read_timeout",
    "fake_remote_success",
    "fake_remote_accept_then_hang",
    "fake_remote_reject",
    "network_hang",
    "network_drop",
    "network_malformed",
    "network_delayed",
    "delayed_result_after_lease_loss",
    "process_tree",
    "inspect_environment",
]


class LongSpec(Model):
    model_config = ConfigDict(extra="forbid", validate_default=True, allow_inf_nan=False)
    handler: Handler
    handler_version: Literal[1] = 1
    duration_seconds: float = Field(default=0.2, ge=0, le=120)
    hard_timeout_seconds: float = Field(default=3, ge=0.1, le=180)
    cancellation_grace_seconds: float = Field(default=0.3, ge=0.05, le=2)
    connect_timeout_seconds: float = Field(default=1, ge=0.05, le=5)
    read_timeout_seconds: float = Field(default=1, ge=0.05, le=120)


class LongSubmission(Model):
    logical_key: str = Field(min_length=1, max_length=150, pattern=r"^[a-zA-Z0-9_.:-]+$")
    spec: LongSpec


class ExecutionEnvelope(Model):
    execution_id: UUID
    workspace_id: UUID
    job_id: UUID
    attempt_id: UUID
    fence: int = Field(ge=1)
    input_reference: UUID
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    correlation_id: UUID
    trace_id: UUID
    authority_reference: UUID | None = None
    reservation_reference: UUID | None = None
    spec: LongSpec
    # Assigned by the parent to a server it has just bound on 127.0.0.1.
    loopback_port: int | None = Field(default=None, ge=1, le=65535)


class ExecutionResult(Model):
    execution_id: UUID
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    handler_version: Literal[1] = 1
    status: Literal[
        "succeeded", "rejected", "transient_failure", "permanent_failure", "cancelled", "uncertain"
    ]
    output_reference: UUID
    error_code: (
        Literal["READ_TIMEOUT", "CONNECT_TIMEOUT", "CONNECTION_DROP", "INVALID_RESPONSE"] | None
    ) = None
    duration_seconds: float = Field(ge=0, le=300, allow_inf_nan=False)
    receipt_reference: UUID | None = None
    environment_names: list[str] = Field(default_factory=list, max_length=12)


MAX_MESSAGE = 8192
