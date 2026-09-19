"""Closed synthetic authority contracts. No executable provider configuration."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from company_os.contracts import Model
from company_os.runtime_contracts import UtcTime

SyntheticAction = Literal[
    "runtime.synthetic_calculation",
    "runtime.synthetic_internal_action",
    "runtime.synthetic_external_action",
    "runtime.synthetic_batch_action",
    "runtime.synthetic_binding_decision",
]
Action = SyntheticAction | Literal["policy.activate", "ai.route.promote"]
Money = Annotated[Decimal, Field(ge=0, le=100, max_digits=12, decimal_places=8)]


class PolicyRules(Model):
    action: Action
    maximum_uses: int = Field(ge=1, le=100)
    maximum_targets: int = Field(ge=1, le=200)
    maximum_volume: int = Field(ge=1, le=20000)
    maximum_spend: Money
    maximum_expiry_seconds: int = Field(ge=1, le=86400)
    permitted_roles: list[Literal["founder", "researcher", "sdr"]] = Field(min_length=1)


class FakePayload(Model):
    label: str = Field(min_length=1, max_length=100)
    scenario: Literal["effect_success", "effect_rejected", "effect_lost", "effect_unknown"]


class TargetVersion(Model):
    id: UUID
    version: int = Field(ge=1)


class RequestAuthority(Model):
    action: SyntheticAction
    targets: list[TargetVersion] = Field(min_length=1, max_length=200)
    payload: FakePayload
    maximum_uses: int = Field(ge=1, le=100)
    maximum_spend: Money
    maximum_volume: int = Field(ge=1, le=20000)
    expires_at: UtcTime
    rationale: str = Field(min_length=5, max_length=500)
    supersedes_id: UUID | None = None

    @model_validator(mode="after")
    def unique_targets(self) -> "RequestAuthority":
        if len({x.id for x in self.targets}) != len(self.targets):
            raise ValueError("Duplicate target")
        return self


class DecideAuthority(Model):
    decision: Literal["approve", "reject", "revise"]
    expected_scope_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rationale: str = Field(min_length=5, max_length=500)


class Reason(Model):
    rationale: str = Field(min_length=5, max_length=500)


class ExecuteAuthority(Model):
    payload: FakePayload
    targets: list[TargetVersion] = Field(min_length=1, max_length=200)
    logical_key: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")


class FreezeAuthority(Reason):
    action: Action | None = None


class PolicyInput(Model):
    rules: PolicyRules
    rationale: str = Field(min_length=5, max_length=500)
    effective_at: UtcTime
    expires_at: UtcTime
    approval_expires_at: UtcTime


class PolicyActivate(Model):
    policy_version_id: UUID
    decision_id: UUID
    manifest_id: UUID


class PolicyActivationPayload(Model):
    label: str
    policy_id: UUID
    policy_record_version: int
    current_active_version_id: UUID | None
    candidate_version_id: UUID
    candidate_version_number: int
    candidate_content_hash: str
    candidate_effective_at: str
    candidate_expires_at: str
    rules: PolicyRules
    action: Literal["policy.activate"] = "policy.activate"
    workspace_id: UUID

    @model_serializer(mode="wrap")
    def exact_pointer(self, handler: SerializerFunctionWrapHandler):  # type: ignore[no-untyped-def]
        # Keep the model's typed OpenAPI schema; a dict return annotation would
        # replace it with an untyped serialization schema.
        result = handler(self)
        # A disabled pointer is a material part of the hashed snapshot, even in
        # API responses that omit other optional null fields.
        result["current_active_version_id"] = (
            str(self.current_active_version_id) if self.current_active_version_id else None
        )
        return result


class PolicyResult(Model):
    result: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL", "QUARANTINE"]
    reasons: list[str]


class AuthorityEnvelope[T](Model):
    data: T


class AuthorityRecord(Model):
    id: UUID
    workspace_id: UUID
    created_at: UtcTime
    created_by: UUID
    schema_version: int


class MutableAuthorityRecord(AuthorityRecord):
    updated_at: UtcTime
    updated_by: UUID
    record_version: int


class RoutePromotionPayload(Model):
    label: str
    route_id: UUID
    route_hash: str
    evaluation_id: UUID
    binding_hash: str
    rollback_route_id: UUID
    current_route_id: UUID
    action: Literal["ai.route.promote"] = "ai.route.promote"


class ApprovalView(MutableAuthorityRecord):
    action: Action
    policy_version_id: UUID
    payload: FakePayload | PolicyActivationPayload | RoutePromotionPayload
    payload_hash: str
    scope_hash: str
    target_set_hash: str
    maximum_uses: int
    maximum_spend: Decimal
    maximum_volume: int
    expires_at: UtcTime
    rationale: str
    correlation_id: UUID
    supersedes_id: UUID | None
    state: Literal["pending", "approved", "rejected", "expired", "revoked", "superseded"]
    effective_state: str | None = None
    policy_id: UUID | None = None
    candidate_version_id: UUID | None = None
    expected_policy_record_version: int | None = None
    expected_active_version_id: UUID | None = None


class ManifestScope(Model):
    version: Literal[1]
    scope_hash: str
    workspace_id: UUID
    action: Action
    policy_version_id: UUID
    payload_hash: str
    target_set_hash: str
    targets: list[TargetVersion]
    maximum_uses: int
    maximum_spend: str
    maximum_volume: int
    expires_at: str
    approver_id: UUID
    assurance: Literal["aal2"]
    policy_change: PolicyActivationPayload | None = None


class ManifestView(AuthorityRecord):
    request_id: UUID
    decision_id: UUID
    scope: ManifestScope
    manifest_hash: str
    starts_at: UtcTime
    expires_at: UtcTime


class AuthorityUseView(AuthorityRecord):
    manifest_id: UUID
    effect_id: UUID | None
    job_id: UUID | None
    activation_policy_id: UUID | None = None
    activation_session_id: UUID | None = None
    activation_route_id: UUID | None = None
    use_number: int
    spend_reserved: Decimal
    volume: int
    state: Literal["reserved", "consumed", "released"]


class DecisionView(Model):
    id: UUID
    decision: Literal["approve", "reject", "revise", "revoke"]
    rationale: str
    created_by: UUID
    created_at: UtcTime
    correlation_id: UUID


class ApprovalDetail(Model):
    request: ApprovalView
    targets: list[TargetVersion]
    manifest: ManifestView | None
    history: list[DecisionView]
    uses: list[AuthorityUseView]
    validation_reason: str | None
    remaining_uses: int


class AuthorityTargetView(MutableAuthorityRecord):
    label: str
    suppressed: bool
    rights_valid: bool


class PolicyView(Model):
    id: UUID
    record_version: int
    action: Action
    active_version_id: UUID | None
    version: int | None
    rules: PolicyRules | None
    content_hash: str | None
    expires_at: UtcTime | None


class PolicyRecord(MutableAuthorityRecord):
    action: Action
    active_version_id: UUID | None


class FreezeView(AuthorityRecord):
    action: Action | None
    rationale: str
    correlation_id: UUID


class AuthorityResult(Model):
    result: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL", "QUARANTINE"]
    reasons: list[str] = []
    request_id: UUID | None = None
    decision_id: UUID | None = None
    input_id: UUID | None = None
    manifest_id: UUID | None = None
