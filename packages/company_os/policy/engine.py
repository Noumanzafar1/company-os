"""Deterministic decisions over server-resolved facts; results never grant authority."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType

from company_os.policy_contracts import Action, PolicyResult, PolicyRules


@dataclass(frozen=True)
class ActionDefinition:
    level: int
    target_type: str
    material: bool
    reversible: bool
    approval_required: bool
    assurance: str
    executor: str
    execution_class: str


REGISTRY = MappingProxyType(
    {
        "ai.route.promote": ActionDefinition(
            3, "synthetic_route", True, False, True, "aal2", "human", "route_promotion"
        ),
        "policy.activate": ActionDefinition(
            3, "policy", True, False, True, "aal2", "human", "policy_activation"
        ),
        "runtime.synthetic_calculation": ActionDefinition(
            0, "synthetic", False, True, False, "aal1", "application", "calculation"
        ),
        "runtime.synthetic_internal_action": ActionDefinition(
            1, "synthetic", False, True, False, "aal1", "application", "internal"
        ),
        "runtime.synthetic_external_action": ActionDefinition(
            3, "synthetic", True, False, True, "aal2", "fake_local_v1", "bounded_fake"
        ),
        "runtime.synthetic_batch_action": ActionDefinition(
            3, "synthetic", True, False, True, "aal2", "fake_local_v1", "bounded_fake"
        ),
        "runtime.synthetic_binding_decision": ActionDefinition(
            4, "synthetic", True, False, True, "aal2", "human", "record_only"
        ),
    }
)


@dataclass(frozen=True)
class Evaluation:
    action: Action
    roles: frozenset[str]
    now: datetime
    expires_at: datetime
    uses: int
    spend: Decimal
    volume: int
    targets: int
    versions_match: bool
    rights_valid: bool
    suppressed: bool
    frozen: bool
    policy_current: bool
    authority_valid: bool = False
    malformed: bool = False


def evaluate(facts: Evaluation, rules: PolicyRules) -> PolicyResult:
    reasons: list[str] = []
    if facts.malformed:
        return PolicyResult(result="QUARANTINE", reasons=["MALFORMED_SCOPE"])
    definition = REGISTRY[facts.action]
    for denied, code in (
        (not facts.roles.intersection(rules.permitted_roles), "ROLE_DENIED"),
        (facts.action != rules.action or not facts.policy_current, "POLICY_CHANGED"),
        (not facts.versions_match, "OBJECT_VERSION_CHANGED"),
        (not facts.rights_valid, "RIGHTS_REVOKED"),
        (facts.suppressed, "SUPPRESSED"),
        (facts.frozen and definition.material, "EMERGENCY_FREEZE"),
        (facts.now >= facts.expires_at, "EXPIRED"),
        (
            (facts.expires_at - facts.now).total_seconds() > rules.maximum_expiry_seconds,
            "EXPIRY_LIMIT",
        ),
        (facts.uses > rules.maximum_uses, "USE_LIMIT"),
        (facts.spend > rules.maximum_spend, "SPEND_LIMIT"),
        (
            facts.volume > rules.maximum_volume or facts.targets > rules.maximum_targets,
            "VOLUME_LIMIT",
        ),
        (definition.level == 4, "HUMAN_ONLY"),
    ):
        if denied:
            reasons.append(code)
    if reasons:
        return PolicyResult(result="DENY", reasons=reasons)
    if definition.approval_required and not facts.authority_valid:
        return PolicyResult(result="REQUIRE_APPROVAL", reasons=["EXACT_GRANT_REQUIRED"])
    return PolicyResult(result="ALLOW", reasons=["WITHIN_CURRENT_AUTHORITY"])
