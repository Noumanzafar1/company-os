"""Closed AI-001–005 contracts. Browser requests never choose privileged fields."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from company_os.contracts import Model
from company_os.runtime_contracts import UtcTime

Provider = Literal["fake_openai", "fake_anthropic", "openai", "anthropic"]
TaskType = Literal["gateway_contract"]
Scenario = Literal[
    "success",
    "refusal",
    "malformed",
    "invalid_schema",
    "incomplete",
    "repair",
    "timeout",
    "connection_failure",
    "rate_limit",
    "overloaded",
    "uncertain",
    "unsupported_schema",
    "unsupported_model",
    "incorrect_usage",
    "delayed",
    "injection",
    "forged_evidence",
    "unsupported_claim",
    "secret",
    "tool_url",
    "tool_shell",
    "cross_workspace",
    "authority",
    "oversized",
    "fallback_denied",
    "budget_exhausted",
    "max_calls",
    "revocation",
]
Error = Literal[
    "auth",
    "permission",
    "invalid_request",
    "rate_limit",
    "quota",
    "provider_overloaded",
    "timeout_connect",
    "timeout_read",
    "timeout_total",
    "refused",
    "incomplete",
    "schema_invalid",
    "unsupported_capability",
    "provider_error",
    "uncertain",
    "cancelled",
]
Money = Annotated[Decimal, Field(ge=0, le=100, max_digits=12, decimal_places=8)]


class Frozen(Model):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class AIRequest(Model):
    task_type: TaskType = "gateway_contract"
    scenario: Scenario = "success"


class ResourceRef(Frozen):
    type: Literal["synthetic_evidence", "synthetic_document"]
    id: UUID
    version: int = Field(ge=1)
    observed_at: UtcTime
    validity: Literal["current"] = "current"


class Evidence(Frozen):
    ref: ResourceRef
    key: Literal["fixture_colour"] = "fixture_colour"
    value: Literal["blue"] = "blue"


class ContextPack(Frozen):
    id: UUID
    workspace_id: UUID
    task_type: TaskType = "gateway_contract"
    created_at: UtcTime
    expires_at: UtcTime
    authz_epoch: int
    document_permission_epochs: dict[str, int]
    company_brief_version: Literal["synthetic-v1"] = "synthetic-v1"
    policy_version: UUID
    selected_records: tuple[ResourceRef, ...]
    evidence: tuple[Evidence, ...]
    document_excerpts: tuple[str, ...]
    tool_descriptors: tuple[()] = ()
    output_schema: str = "gateway-output:1"
    redactions: tuple[str, ...] = ()
    omissions: tuple[str, ...] = ("No business records selected",)
    token_estimate: int = Field(ge=1, le=8000)
    content_hash: str


class AITask(Frozen):
    id: UUID
    task_type: TaskType = "gateway_contract"
    task_version: Literal[1] = 1
    workspace_id: UUID
    subject_refs: tuple[ResourceRef, ...]
    allowed_providers: tuple[Provider, ...]
    context_pack_id: UUID
    evidence_refs: tuple[ResourceRef, ...]
    policy_version_id: UUID
    allowed_tools: tuple[()] = ()
    output_schema_id: Literal["gateway-output:1"] = "gateway-output:1"
    max_cost_usd: Money = Decimal("0.05")
    max_input_tokens: int = Field(default=8000, ge=1, le=8000)
    max_output_tokens: int = Field(default=512, ge=1, le=1500)
    max_model_calls: int = Field(default=2, ge=1, le=2)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    sensitivity: Literal["synthetic"] = "synthetic"
    evaluation_policy_id: UUID
    deadline_at: UtcTime


class AIRoute(Frozen):
    route_id: UUID
    version: int = Field(ge=1)
    task_type: TaskType = "gateway_contract"
    task_version: Literal[1] = 1
    environment: Literal["technical"] = "technical"
    primary_provider: Provider
    primary_model_id: str = Field(min_length=1, max_length=100)
    model_snapshot: str | None = None
    fallback_provider: Provider | None = None
    fallback_model_id: str | None = None
    capabilities_required: tuple[Literal["structured_output"], ...] = ("structured_output",)
    prompt_version: UUID
    schema_version: UUID
    price_config_version: UUID
    context_policy_version: Literal["deterministic-synthetic-1"] = "deterministic-synthetic-1"
    quality_evaluation_id: UUID | None = None
    allowed_sensitivity: tuple[Literal["synthetic"], ...] = ("synthetic",)
    region_policy: Literal["offline", "preflight_required"] = "offline"
    provider_options_ref: Literal["no-tools-no-store-v1"] = "no-tools-no-store-v1"
    max_input_tokens: int = 8000
    max_output_tokens: int = 512
    max_cost_usd: Money = Decimal("0.05")
    timeout_seconds: int = 10
    review_policy: Literal["proposal_only"] = "proposal_only"


class Claim(Frozen):
    evidence_id: UUID
    key: Literal["fixture_colour"]
    value: str = Field(min_length=1, max_length=100)


class TypedProposal(Frozen):
    claims: tuple[Claim, ...] = Field(max_length=4)
    unknowns: tuple[Literal["business facts unavailable"], ...] = Field(max_length=1)
    uncertainties: tuple[Literal["synthetic fixture only"], ...] = Field(max_length=1)
    proposed_actions: tuple[()] = ()


class Usage(Frozen):
    input_tokens: int = Field(ge=0, le=1000000)
    output_tokens: int = Field(ge=0, le=1000000)
    cached_tokens: int = Field(default=0, ge=0, le=1000000)
    cache_creation_tokens: int = Field(default=0, ge=0, le=1000000)
    billable_units: int = Field(default=1, ge=0, le=1)


class ProviderResponse(Frozen):
    status: Literal["completed", "failed", "refused", "incomplete", "uncertain"]
    output: str | None = Field(default=None, max_length=16000)
    usage: Usage | None = None
    request_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    reported_model: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    error: Error | None = None
    retry_after: int = Field(default=0, ge=0, le=3600)


class Validation(Frozen):
    schema_valid: bool
    evidence: bool
    policy: bool
    semantic: bool
    defects: tuple[str, ...] = ()


class AIResult(Frozen):
    task_id: UUID
    status: Literal["proposed", "refused", "incomplete", "invalid", "quarantined"]
    result: TypedProposal | None
    claim_evidence_map: tuple[Claim, ...] = ()
    unknowns: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    proposed_actions: tuple[()] = ()
    provider: Provider
    model_id: str
    reported_model_version: str | None = None
    route_version: UUID
    prompt_version: UUID
    schema_version: UUID
    usage: Usage | None
    estimated_usd: Money
    confirmed_usd: Money | None = None
    price_version: UUID
    reservation_id: UUID
    latency_ms: float = Field(ge=0)
    validation: Validation
    provider_request_id: str | None = None


class ProviderCall(Frozen):
    execution_id: UUID
    input_hash: str
    task: AITask
    context: ContextPack
    route: AIRoute
    scenario: Scenario
    ordinal: int = Field(ge=1, le=2)
    prompt: str = Field(max_length=2000)
    output_schema: dict
    hard_timeout_seconds: float = Field(default=5, ge=0.1, le=60)
    cancellation_grace_seconds: float = 0.3


class ProviderReply(Frozen):
    execution_id: UUID
    input_hash: str
    response: ProviderResponse


class PromotionRequest(Model):
    route_id: UUID
    evaluation_id: UUID
    rollback_route_id: UUID


class AIEvaluation(Frozen):
    dataset_id: UUID
    dataset_version: int
    split: Literal["seed", "development", "holdout", "adversarial"]
    task_type: TaskType = "gateway_contract"
    task_version: Literal[1] = 1
    route_candidate: UUID
    sample_count: int
    class_counts: dict[str, int]
    metrics: dict[str, float | int | None]
    confidence_intervals: None = None
    hard_failure_examples: tuple[str, ...]
    cost_per_useful_output: Money | None
    latency_percentiles: dict[str, float | None]
    founder_edit_rate: None = None
    reviewer: Literal["synthetic-engineering-harness"] = "synthetic-engineering-harness"
    decision: Literal["technical_pass", "technical_fail"]
    run_at: UtcTime


class AIStatus(Model):
    id: UUID
    job_id: UUID
    state: str
    record_version: int


class AIInspection(AIStatus):
    task: AITask
    context: ContextPack | None
    context_current: bool
    route: AIRoute
    result: AIResult | None
    model_runs: list[dict]
    correlation_id: UUID


class EvaluationRequest(Model):
    dataset: Literal["seed", "development", "holdout", "adversarial"] = "adversarial"


class VersionRequest(Model):
    expected_version: int = Field(ge=1)


class EvaluationView(Model):
    id: UUID
    route_id: UUID
    body: AIEvaluation
    current_route_id: UUID
    current_result: dict


class AIHealth(Model):
    providers: list[dict]
    tasks: list[dict]
    counts: list[dict]
    routes: list[dict]
    evaluations: list[EvaluationView]
    budgets: list[dict]
    warning: str
