from decimal import Decimal

import pytest
from company_os.domain.scoring import WEIGHTS, ComponentInput, calculate


def supported():
    return {key: ComponentInput(True, (f"evidence:{key}:v1",)) for key in WEIGHTS}


def score(inputs, **kwargs):
    return calculate(inputs, rubric_version="synthetic-1", icp_version_id="icp-version-1", **kwargs)


def test_reproducibility_and_fixed_decimal_bounds():
    inputs = supported()
    first = score(inputs)
    second = score(dict(reversed(list(inputs.items()))))
    assert first == second
    assert first.known_points == Decimal("100.00")
    assert first.maximum_known_points == Decimal("100.00")
    assert all(value.points == WEIGHTS[key] for key, value in first.components.items())


def test_missing_trigger_stays_null_without_renormalization():
    inputs = supported()
    inputs["trigger"] = ComponentInput(None, (), ("missing_trigger",))
    result = score(inputs)
    assert result.components["trigger"].points is None
    assert result.missing_keys == ("trigger",)
    assert result.known_points == result.maximum_known_points == Decimal("80.00")
    assert result.priority == "review"


def test_unknown_and_confirmed_mismatch_are_distinct():
    inputs = supported()
    inputs["fit"] = ComponentInput(False, ("evidence:industry:mismatch",))
    result = score(inputs)
    assert result.components["fit"].points == Decimal("0.00")
    assert result.maximum_known_points == Decimal("100.00")
    assert result.missing_keys == ()


def test_hard_exclusion_dominates_high_points():
    result = score(supported(), exclusions=("excluded_industry",))
    assert result.known_points == Decimal("100.00")
    assert result.priority == "excluded"
    assert result.hard_exclusions == ("excluded_industry",)


def test_no_support_cannot_earn_points_or_claim_known_mismatch():
    for value in (True, False):
        inputs = supported()
        inputs["role"] = ComponentInput(value, ())
        with pytest.raises(ValueError, match="supporting"):
            score(inputs)


def test_all_unknown_is_not_fabricated_zero_components():
    result = score({key: ComponentInput(None, ()) for key in WEIGHTS})
    assert result.known_points == Decimal("0.00")
    assert result.maximum_known_points == Decimal("0.00")
    assert all(component.points is None for component in result.components.values())
    assert len(result.missing_keys) == 5


def test_new_rubric_or_icp_changes_hash_and_keeps_old_result():
    first = score(supported())
    new_rubric = calculate(
        supported(), rubric_version="synthetic-2", icp_version_id="icp-version-1"
    )
    new_icp = calculate(supported(), rubric_version="synthetic-1", icp_version_id="icp-version-2")
    assert first.policy_hash != new_rubric.policy_hash
    assert len({first.input_hash, new_rubric.input_hash, new_icp.input_hash}) == 3
    assert first == score(supported())


def test_support_order_is_canonical_and_reference_change_invalidates_hash():
    inputs = supported()
    inputs["fit"] = ComponentInput(True, ("b", "a", "a"))
    first = score(inputs)
    inputs["fit"] = ComponentInput(True, ("a", "b"))
    assert score(inputs) == first
    inputs["fit"] = ComponentInput(True, ("a", "c"))
    assert score(inputs).input_hash != first.input_hash


def test_closed_component_set_and_required_versions():
    inputs = supported()
    del inputs["fit"]
    with pytest.raises(ValueError):
        score(inputs)
    with pytest.raises(ValueError):
        calculate(supported(), rubric_version="", icp_version_id="icp-1")
