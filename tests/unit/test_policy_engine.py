from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from company_os.application.authority import target_hash
from company_os.policy.engine import REGISTRY, Evaluation, evaluate
from company_os.policy_contracts import PolicyRules


def fixture():
    now = datetime.now(UTC)
    rules = PolicyRules(
        action="runtime.synthetic_external_action",
        maximum_uses=10,
        maximum_targets=10,
        maximum_volume=100,
        maximum_spend="10",
        maximum_expiry_seconds=3600,
        permitted_roles=["founder"],
    )
    facts = Evaluation(
        action=rules.action,
        roles=frozenset({"founder"}),
        now=now,
        expires_at=now + timedelta(minutes=30),
        uses=1,
        spend=Decimal(1),
        volume=1,
        targets=1,
        versions_match=True,
        rights_valid=True,
        suppressed=False,
        frozen=False,
        policy_current=True,
    )
    return facts, rules


@pytest.mark.parametrize(
    "change,code",
    [
        ({"suppressed": True}, "SUPPRESSED"),
        ({"rights_valid": False}, "RIGHTS_REVOKED"),
        ({"frozen": True}, "EMERGENCY_FREEZE"),
        ({"versions_match": False}, "OBJECT_VERSION_CHANGED"),
        ({"roles": frozenset({"system_administrator"})}, "ROLE_DENIED"),
        ({"uses": 11}, "USE_LIMIT"),
        ({"spend": Decimal(11)}, "SPEND_LIMIT"),
        ({"volume": 101}, "VOLUME_LIMIT"),
        ({"policy_current": False}, "POLICY_CHANGED"),
    ],
)
def test_safety_dominates_grant(change, code):
    facts, rules = fixture()
    result = evaluate(replace(facts, authority_valid=True, **change), rules)
    assert result.result == "DENY" and code in result.reasons


def test_authority_levels_and_exact_expiry():
    facts, rules = fixture()
    assert evaluate(facts, rules).result == "REQUIRE_APPROVAL"
    assert evaluate(replace(facts, authority_valid=True), rules).result == "ALLOW"
    assert evaluate(replace(facts, expires_at=facts.now, authority_valid=True), rules).reasons == [
        "EXPIRED"
    ]
    assert evaluate(replace(facts, malformed=True), rules).result == "QUARANTINE"
    for action in ("runtime.synthetic_calculation", "runtime.synthetic_internal_action"):
        assert (
            evaluate(
                replace(facts, action=action), rules.model_copy(update={"action": action})
            ).result
            == "ALLOW"
        )
    action = "runtime.synthetic_binding_decision"
    assert (
        "HUMAN_ONLY"
        in evaluate(
            replace(facts, action=action, authority_valid=True),
            rules.model_copy(update={"action": action}),
        ).reasons
    )
    with pytest.raises(TypeError):
        REGISTRY["unsafe"] = REGISTRY[action]


def test_target_canonicalization():
    a = {"id": "a", "version": 1}
    b = {"id": "b", "version": 2}
    assert target_hash([a, b]) == target_hash([b, a])
    assert target_hash([a, b]) != target_hash([a, {**b, "version": 3}])


def test_all_roles_intersection_is_order_independent():
    facts, rules = fixture()
    rules = rules.model_copy(update={"permitted_roles": ["researcher"]})
    forward = replace(facts, roles=frozenset(["founder", "researcher"]))
    reverse = replace(facts, roles=frozenset(["researcher", "founder"]))
    assert evaluate(forward, rules) == evaluate(reverse, rules)
    assert evaluate(forward, rules).result == "REQUIRE_APPROVAL"
    assert evaluate(forward, rules.model_copy(update={"permitted_roles": ["sdr"]})).reasons == [
        "ROLE_DENIED"
    ]
    assert (
        evaluate(replace(facts, roles=frozenset(["researcher"])), rules).result
        == "REQUIRE_APPROVAL"
    )
