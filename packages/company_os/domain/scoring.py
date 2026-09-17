"""DATA-026 pure, deterministic scoring. No I/O, inference or eligibility grant."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ComponentKey = Literal["fit", "economics", "trigger", "role", "freshness"]
WEIGHTS: dict[ComponentKey, Decimal] = {
    "fit": Decimal("30.00"),
    "economics": Decimal("20.00"),
    "trigger": Decimal("20.00"),
    "role": Decimal("15.00"),
    "freshness": Decimal("15.00"),
}


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ComponentInput:
    """The application resolves current evidence before entering this boundary.

    A missing/unusable observation is unknown. False means a supported mismatch.
    Support references are immutable evidence IDs/content hashes or an explicitly
    versioned deterministic definition; a bare unsupported True is rejected.
    """

    matches: bool | None
    support: tuple[str, ...]
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComponentResult:
    points: Decimal | None
    max_points: Decimal
    support: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ScoreResult:
    components: dict[ComponentKey, ComponentResult]
    known_points: Decimal
    maximum_known_points: Decimal
    missing_keys: tuple[ComponentKey, ...]
    hard_exclusions: tuple[str, ...]
    priority: Literal["excluded", "priority", "review", "below_review"]
    policy_hash: str
    input_hash: str


def calculate(
    inputs: dict[ComponentKey, ComponentInput],
    *,
    rubric_version: str,
    icp_version_id: str,
    exclusions: tuple[str, ...] = (),
) -> ScoreResult:
    """Canonical binary fixture rubric; policy/version changes preserve history.

    This function deliberately has no configurable weights or arbitrary formulas.
    A richer rubric requires a separately versioned closed contract.
    """
    if not rubric_version or not icp_version_id or set(inputs) != set(WEIGHTS):
        raise ValueError("An exact version and every component are required")
    components: dict[ComponentKey, ComponentResult] = {}
    missing: list[ComponentKey] = []
    known = Decimal("0.00")
    maximum = Decimal("0.00")
    normalized_inputs: dict[str, object] = {}
    for key, weight in WEIGHTS.items():
        observation = inputs[key]
        if observation.matches is not None and type(observation.matches) is not bool:
            raise ValueError("Component match must be boolean or unknown")
        if observation.matches is not None and not observation.support:
            raise ValueError("Known components require supporting references")
        support = tuple(sorted(set(observation.support)))
        reasons = tuple(sorted(set(observation.reasons)))
        points = None
        if observation.matches is None:
            missing.append(key)
        else:
            points = weight if observation.matches else Decimal("0.00")
            known += points
            maximum += weight
        components[key] = ComponentResult(points, weight, support, reasons)
        normalized_inputs[key] = {
            "matches": observation.matches,
            "support": support,
            "reasons": reasons,
        }
    hard_exclusions = tuple(sorted(set(exclusions)))
    policy_hash = canonical_hash(
        {
            "contract": "DATA-026/binary-fixture-v1",
            "rubric_version": rubric_version,
            "weights": {key: str(weight) for key, weight in WEIGHTS.items()},
            "review_threshold": "70.00",
            "priority_threshold": "85.00",
        }
    )
    input_hash = canonical_hash(
        {
            "icp_version_id": icp_version_id,
            "policy_hash": policy_hash,
            "components": normalized_inputs,
            "hard_exclusions": hard_exclusions,
        }
    )
    priority: Literal["excluded", "priority", "review", "below_review"]
    priority = (
        "excluded"
        if hard_exclusions
        else "priority"
        if known >= Decimal("85")
        else "review"
        if known >= Decimal("70")
        else "below_review"
    )
    return ScoreResult(
        components,
        known,
        maximum,
        tuple(missing),
        hard_exclusions,
        priority,
        policy_hash,
        input_hash,
    )
