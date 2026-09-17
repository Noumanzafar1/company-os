"""Closed Phase 3 command and read contracts; API-001, DATA-009–026."""

from datetime import UTC, date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, Field, model_validator

from company_os.contracts import Meta, Model

UtcTime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]

Short = Annotated[str, Field(min_length=1, max_length=500)]
Text = Annotated[str, Field(max_length=20000)]
Refs = Annotated[list[UUID], Field(max_length=200)]


class AccountInput(Model):
    display_name: Short
    legal_name: Short | None = None
    primary_domain: (
        Annotated[str, Field(max_length=253, pattern=r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$")] | None
    ) = None
    identity_discriminator: Short
    parent_id: UUID | None = None
    country_code: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] | None = None
    industry_code: Short | None = None
    size_min: Annotated[int, Field(ge=0)] | None = None
    size_max: Annotated[int, Field(ge=0)] | None = None
    source_id: UUID

    @model_validator(mode="after")
    def sizes(self) -> "AccountInput":
        if (
            self.size_min is not None
            and self.size_max is not None
            and self.size_max < self.size_min
        ):
            raise ValueError("Invalid size range")
        return self


class PersonInput(Model):
    display_name: Short
    given_name: Short | None = None
    family_name: Short | None = None
    source_id: UUID


class EmploymentInput(Model):
    person_id: UUID
    account_id: UUID
    title: Short
    start_date: date | None = None
    end_date: date | None = None
    observed_at: UtcTime
    evidence_id: UUID
    status: Literal["current", "former", "uncertain"]


class ContactInput(Model):
    person_id: UUID | None = None
    account_id: UUID | None = None
    kind: Literal["email", "phone", "url"]
    value: Annotated[str, Field(min_length=1, max_length=2000)]
    source_id: UUID


class FactValue(Model):
    type: Literal["string", "integer", "decimal", "date", "boolean", "unknown"]
    value: str | int | bool | None
    unit: Short | None = None

    @model_validator(mode="after")
    def typed(self) -> "FactValue":
        expected = {
            "string": str,
            "integer": int,
            "decimal": str,
            "date": str,
            "boolean": bool,
            "unknown": type(None),
        }
        if type(self.value) is not expected[self.type]:
            raise ValueError("Fact value type mismatch")
        if self.type == "decimal":
            number = Decimal(str(self.value))
            if (
                not number.is_finite()
                or abs(number) >= Decimal("1e14")
                or (
                    isinstance(number.as_tuple().exponent, int)
                    and int(number.as_tuple().exponent) < -6
                )
            ):
                raise ValueError("Fact decimal out of bounds")
        if self.type == "date":
            date.fromisoformat(str(self.value))
        if isinstance(self.value, str) and len(self.value) > 20000:
            raise ValueError("Fact too long")
        return self


class EvidenceInput(Model):
    subject_id: UUID
    source_id: UUID
    source_url: Annotated[str, Field(max_length=2000, pattern=r"^https?://")] | None = None
    provider_record_id: Short | None = None
    fact_key: Annotated[str, Field(min_length=1, max_length=100)]
    fact_value: FactValue
    excerpt: Text | None = None
    document_version_id: UUID | None = None
    observed_at: UtcTime
    event_at: UtcTime | None = None
    expires_at: UtcTime
    entity_match: Literal["confirmed", "uncertain", "rejected"]
    fact_kind: Literal["observed", "reported", "inferred"]
    supersedes_id: UUID | None = None

    @model_validator(mode="after")
    def provenance(self) -> "EvidenceInput":
        if not (self.source_url or self.provider_record_id or self.document_version_id):
            raise ValueError("Provenance locator required")
        if self.expires_at < self.observed_at:
            raise ValueError("Invalid expiry")
        return self


class RetractionInput(Model):
    reason: Short
    replacement_id: UUID | None = None


class SignalInput(Model):
    subject_id: UUID
    kind: Literal["hiring", "funding", "technology_change", "expansion", "stated_need", "other"]
    event_at: UtcTime | None = None
    observed_at: UtcTime
    expires_at: UtcTime
    evidence_id: UUID
    relevance_summary: Text

    @model_validator(mode="after")
    def chronology(self) -> "SignalInput":
        if self.expires_at < self.observed_at:
            raise ValueError("Invalid expiry")
        return self


class EmployeeRange(Model):
    min: int = Field(ge=0)
    max: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> "EmployeeRange":
        if self.max < self.min:
            raise ValueError("Invalid employee range")
        return self


class Criteria(Model):
    industries: list[Short] = Field(max_length=200)
    countries: list[Annotated[str, Field(pattern=r"^[A-Z]{2}$")]] = Field(max_length=200)
    employee_range: EmployeeRange | None = None
    required_problem_fact_keys: list[Short] = Field(max_length=200)
    target_roles: list[Short] = Field(max_length=200)
    required_evidence_keys: list[Short] = Field(max_length=200)


class ExclusionRule(Model):
    field: Literal["industry_code", "country_code", "primary_domain", "employee_count"]
    operator: Literal["eq", "in", "lt", "gt"]
    value: str | int | list[str] | list[int]
    reason_code: Short

    @model_validator(mode="after")
    def operands(self) -> "ExclusionRule":
        if self.operator == "in" and (not isinstance(self.value, list) or len(self.value) > 200):
            raise ValueError("Bounded list required")
        if self.operator in {"lt", "gt"} and (
            self.field != "employee_count" or type(self.value) is not int
        ):
            raise ValueError("Numeric comparison required")
        if self.operator == "eq" and isinstance(self.value, list):
            raise ValueError("Scalar comparison required")
        return self


class Exclusions(Model):
    account_ids: Refs = Field(default_factory=list)
    domains: list[Short] = Field(default_factory=list, max_length=200)
    countries: list[Short] = Field(default_factory=list, max_length=200)
    industry_codes: list[Short] = Field(default_factory=list, max_length=200)
    reason_rules: list[ExclusionRule] = Field(default_factory=list, max_length=200)


class ScoreWeights(Model):
    fit: Literal[30] = 30
    economics: Literal[20] = 20
    trigger: Literal[20] = 20
    role: Literal[15] = 15
    freshness: Literal[15] = 15


class ScorePolicy(Model):
    version: Short
    weights: ScoreWeights = Field(default_factory=ScoreWeights)
    review_threshold: Literal[70] = 70
    priority_threshold: Literal[85] = 85
    contract: Literal["DATA-026/binary-fixture-v1"] = "DATA-026/binary-fixture-v1"
    # A bounded named binary fixture. No executable conditions or weight overrides.
    economics_fact_key: Literal["deal_capacity"] = "deal_capacity"
    trigger_fact_key: Literal["observed_trigger"] = "observed_trigger"


class ICPVersionInput(Model):
    criteria: Criteria
    exclusions: Exclusions
    score_policy: ScorePolicy


class NamedInput(Model):
    name: Short


class OfferVersionInput(Model):
    scope: Text
    exclusions: Text
    proof_document_version_ids: Refs = Field(default_factory=list)
    rate_card_document_version_id: UUID | None = None
    capacity_limit: int = Field(ge=0)


class LeadInput(Model):
    account_id: UUID
    person_id: UUID | None = None
    contact_point_id: UUID | None = None
    icp_version_id: UUID
    offer_version_id: UUID


class ScoreInput(Model):
    subject_id: UUID
    icp_version_id: UUID
    evidence_ids: Refs


class CorrectionInput(Model):
    display_name: Short | None = None
    legal_name: Short | None = None
    primary_domain: Short | None = None
    country_code: Short | None = None
    industry_code: Short | None = None
    size_min: int | None = Field(default=None, ge=0)
    size_max: int | None = Field(default=None, ge=0)
    parent_id: UUID | None = None
    evidence_ids: Refs = Field(min_length=1)
    reason: Short


class MergeInput(Model):
    survivor_id: UUID
    retired_id: UUID
    survivor_version: int = Field(gt=0)
    retired_version: int = Field(gt=0)
    reason: Short
    evidence_ids: Refs = Field(min_length=1)


class ReversalInput(Model):
    reason: Short
    survivor_version: int = Field(gt=0)
    retired_version: int = Field(gt=0)
    evidence_ids: Refs = Field(min_length=1)


class DocumentInput(Model):
    external_file_id: Annotated[str, Field(pattern=r"^fixture:[a-z0-9-]{1,100}$")]
    classification: Literal["public", "internal", "client_confidential", "restricted"]


class CommandResult(Model):
    command_id: UUID
    result_id: UUID
    record_version: int | None
    events: list[None] = Field(default_factory=list, max_length=0)


class Record(Model):
    id: UUID
    workspace_id: UUID
    created_at: UtcTime
    schema_version: int
    record_version: int | None = None


class SourceView(Record):
    name: str
    source_type: str
    rights_status: str
    permitted_purposes: list[str]
    allowed_fields: list[str]
    rights_document_version_id: UUID | None
    expires_at: UtcTime | None
    retention_days: int | None
    current_use_allowed: bool


class EvidenceView(Record):
    subject_id: UUID
    source_id: UUID
    fact_key: str
    fact_value: FactValue
    fact_kind: str
    entity_match: str
    source_url: str | None
    provider_record_id: str | None
    observed_at: UtcTime
    expires_at: UtcTime
    content_sha256: str
    current_support: bool
    invalid_reasons: list[str]


class ScoreComponentView(Model):
    component: str
    points: Decimal | None
    max_points: Decimal
    evidence_ids: list[UUID]
    reason_codes: list[str]


class ScoreView(Record):
    subject_id: UUID
    icp_version_id: UUID
    known_points: Decimal
    maximum_known_points: Decimal
    missing_keys: list[str]
    hard_exclusions: list[str]
    priority: str
    policy_hash: str
    input_hash: str
    current_support: bool
    components: list[ScoreComponentView]


class SignalView(Record):
    acceptance_reason: str | None = None
    subject_id: UUID
    kind: str
    evidence_id: UUID
    relevance_summary: str
    observed_at: UtcTime
    expires_at: UtcTime
    status: str
    current_support: bool


class EmploymentView(Record):
    person_id: UUID
    account_id: UUID
    title: str
    status: str
    evidence_id: UUID
    start_date: date | None
    end_date: date | None
    current_support: bool


class AccountView(Record):
    display_name: str
    legal_name: str | None
    primary_domain: str | None
    identity_discriminator: str
    parent_id: UUID | None
    country_code: str | None
    industry_code: str | None
    size_min: int | None
    size_max: int | None
    status: str
    merged_into_id: UUID | None
    source_id: UUID
    unknown_fields: list[str]
    source_status: str
    current_fact_count: int
    signals: list[str]
    score_summary: ScoreView | None


class PersonView(Record):
    display_name: str
    given_name: str | None
    family_name: str | None
    status: str
    merged_into_id: UUID | None
    source_id: UUID


class LeadView(Record):
    account_id: UUID
    person_id: UUID | None
    contact_point_id: UUID | None
    icp_version_id: UUID
    offer_version_id: UUID
    state: str
    reason_code: str | None
    latest_score_id: UUID | None
    account_name: str
    person_name: str | None
    icp_name: str
    icp_version: int
    offer_name: str
    offer_version: int


class ResearchInput(Model):
    evidence_ids: Refs = Field(min_length=1)


class ReasonInput(Model):
    reason: Short


class DocumentVersionView(Record):
    document_id: UUID
    version: int
    export_sha256: str
    media_type: str
    byte_count: int
    observed_at: UtcTime
    is_final: bool


class DocumentView(Record):
    title: str
    classification: str
    external_file_id: str
    state: str
    permission_epoch: int
    versions: list[DocumentVersionView]


class KnowledgeHit(Model):
    knowledge_id: UUID
    document_id: UUID
    document_version_id: UUID
    title: str
    excerpt: str
    kind: str
    status: Literal["approved", "stale"]
    review_due_at: UtcTime
    hash: str


class Page[T](Model):
    items: list[T]
    next_cursor: str | None = None


class AccountDetail(Model):
    account: AccountView
    source: SourceView
    evidence: list[EvidenceView]
    signals: list[SignalView]
    employments: list[EmploymentView]
    scores: list[ScoreView]


class PageEnvelope[T](Model):
    data: list[T]
    meta: Meta
    next_cursor: str | None = None


class DefinitionVersionView(Record):
    version: int
    content_hash: str
    name: str
    state: Literal["draft"] = "draft"


class ICPVersionView(Record):
    icp_id: UUID
    version: int
    criteria: Criteria
    exclusions: Exclusions
    score_policy: ScorePolicy
    content_hash: str


class OfferVersionView(Record):
    offer_id: UUID
    version: int
    scope: str
    exclusions: str
    proof_document_version_ids: list[UUID]
    rate_card_document_version_id: UUID | None
    capacity_limit: int
    content_hash: str
