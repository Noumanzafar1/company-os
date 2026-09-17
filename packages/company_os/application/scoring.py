"""Read-only Phase 3 score evaluation shared by commands and freshness projections."""

from dataclasses import dataclass
from datetime import UTC
from typing import Any, cast

from sqlalchemy import Connection

from company_os.business_contracts import ICPVersionInput, ScoreInput
from company_os.domain.scoring import (
    WEIGHTS,
    ComponentInput,
    ComponentKey,
    ScoreResult,
    calculate,
    canonical_hash,
)
from company_os.persistence.business import (
    BusinessError,
    fact_value,
    get,
    invalid_reasons,
    require_source,
)
from company_os.persistence.database import rows


@dataclass
class Evaluation:
    result: ScoreResult
    input_hash: str
    used: dict[str, list[dict[str, Any]]]
    evidence: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    lead: dict[str, Any] | None


def evaluate(conn: Connection, body: ScoreInput) -> Evaluation:
    resource = get(conn, "resources", body.subject_id)
    if resource["resource_type"] not in {"account", "lead"}:
        raise BusinessError("INVALID_SCORE_SUBJECT", 422)
    lead = get(conn, "leads", body.subject_id) if resource["resource_type"] == "lead" else None
    account = get(conn, "accounts", lead["account_id"] if lead else body.subject_id)
    require_source(conn, account["source_id"], ["account.identity"])
    policy = get(conn, "icp_versions", body.icp_version_id)
    if lead and lead["icp_version_id"] != body.icp_version_id:
        raise BusinessError("ICP_VERSION_MISMATCH", 422)
    definition = ICPVersionInput.model_validate(
        {
            "criteria": policy["criteria"],
            "exclusions": policy["exclusions"],
            "score_policy": policy["score_policy"],
        }
    )
    evidence = [
        get(conn, "evidence", identifier) for identifier in sorted(set(body.evidence_ids), key=str)
    ]
    if any(item["subject_id"] != account["id"] for item in evidence):
        raise BusinessError("EVIDENCE_SUBJECT_MISMATCH", 422)
    valid = [item for item in evidence if not invalid_reasons(conn, item)]
    by_key: dict[str, list[dict[str, Any]]] = {}
    for item in valid:
        by_key.setdefault(item["fact_key"], []).append(item)

    def supported(key: str) -> tuple[Any, list[dict[str, Any]]]:
        candidates = by_key.get(key, [])
        expected = {
            "industry_code": "string",
            "country_code": "string",
            "employee_count": "integer",
            "deal_capacity": "boolean",
            "observed_trigger": "boolean",
        }
        expected.update({key: "boolean" for key in definition.criteria.required_problem_fact_keys})
        if key in expected and any(item["fact_type"] != expected[key] for item in candidates):
            return None, []
        values = {canonical_hash(fact_value(item).model_dump(mode="json")) for item in candidates}
        if len(values) != 1:
            return None, []  # Contradictory observations do not silently win.
        return fact_value(candidates[0]).value, candidates

    inputs = {key: ComponentInput(None, (), ("missing_evidence",)) for key in WEIGHTS}
    used: dict[str, list[dict[str, Any]]] = {key: [] for key in WEIGHTS}
    industry, fit_support = supported("industry_code")
    fit_support = list(fit_support)
    matches = industry in definition.criteria.industries if industry is not None else None
    if definition.criteria.countries:
        country, support = supported("country_code")
        matches = (
            None
            if country is None or matches is None
            else matches and country in definition.criteria.countries
        )
        fit_support.extend(support)
    if definition.criteria.employee_range:
        employee_count, support = supported("employee_count")
        interval = definition.criteria.employee_range
        matches = (
            None
            if type(employee_count) is not int or matches is None
            else matches and interval.min <= employee_count <= interval.max
        )
        fit_support.extend(support)
    for key in definition.criteria.required_problem_fact_keys:
        value, support = supported(key)
        if value is None:
            matches = None
        elif matches is not None:
            matches = matches and value is True
        fit_support.extend(support)
    if industry is not None and matches is not None:
        used["fit"] = fit_support
        inputs["fit"] = ComponentInput(
            matches,
            tuple(str(item["id"]) + ":" + item["content_sha256"] for item in fit_support),
        )
    signal_dependencies: list[dict[str, Any]] = []
    for component, key in [("economics", "deal_capacity"), ("trigger", "observed_trigger")]:
        value, support = supported(key)
        if type(value) is bool:
            if component == "trigger":
                accepted = rows(
                    conn,
                    "SELECT * FROM app.signals WHERE subject_id=:id AND status='accepted' AND expires_at>now() ORDER BY id",
                    {"id": account["id"]},
                )
                accepted_ids = {item["evidence_id"] for item in accepted}
                support = [
                    item
                    for item in support
                    if item["id"] in accepted_ids and item["fact_kind"] == "observed"
                ]
                support_ids = {item["id"] for item in support}
                signal_dependencies = [
                    item for item in accepted if item["evidence_id"] in support_ids
                ]
            if support:
                used[component] = support
                inputs[cast(ComponentKey, component)] = ComponentInput(
                    value,
                    tuple(str(item["id"]) + ":" + item["content_sha256"] for item in support),
                )
    # Phase 3 never upgrades an unverified contact into a reachable verified role.
    inputs["role"] = ComponentInput(None, (), ("contact_verification_deferred",))
    freshness = [supported(key) for key in definition.criteria.required_evidence_keys]
    if freshness and all(value is not None for value, _ in freshness):
        used["freshness"] = [item for _, support in freshness for item in support]
        inputs["freshness"] = ComponentInput(
            True,
            tuple(str(item["id"]) + ":" + item["content_sha256"] for item in used["freshness"]),
        )
    exclusions = []
    rules = definition.exclusions
    if account["primary_domain"] in rules.domains:
        exclusions.append("excluded_domain")
    if account["country_code"] in rules.countries:
        exclusions.append("excluded_country")
    if industry in rules.industry_codes or account["industry_code"] in rules.industry_codes:
        exclusions.append("excluded_industry")
    for rule in rules.reason_rules:
        value = (
            supported(rule.field)[0] if rule.field == "employee_count" else account.get(rule.field)
        )
        if value is None:
            continue
        applies = (rule.operator == "eq" and value == rule.value) or (
            rule.operator == "in" and isinstance(rule.value, list) and value in rule.value
        )
        if rule.operator in {"lt", "gt"} and type(value) is int and type(rule.value) is int:
            applies = value < rule.value if rule.operator == "lt" else value > rule.value
        if applies:
            exclusions.append(rule.reason_code)
    if rows(
        conn,
        "SELECT id FROM app.icp_excluded_accounts WHERE icp_version_id=:p AND account_id=:a",
        {"p": body.icp_version_id, "a": account["id"]},
    ):
        exclusions.append("excluded_account")
    if account["status"] != "active":
        exclusions.append("identity_not_active")
    result = calculate(
        inputs,
        rubric_version=definition.score_policy.version + ":" + policy["content_hash"],
        icp_version_id=str(body.icp_version_id),
        exclusions=tuple(exclusions),
    )
    input_hash = canonical_hash(
        {
            "dependency_version": 1,
            "calculation": result.input_hash,
            "signals": [
                {
                    "id": str(item["id"]),
                    "version": item["record_version"],
                    "status": item["status"],
                    "expires_at": item["expires_at"].astimezone(UTC).isoformat(),
                    "evidence_id": str(item["evidence_id"]),
                }
                for item in signal_dependencies
            ],
            "account_id": str(account["id"]),
            "account_version": account["record_version"],
            "evidence": [
                {
                    "id": str(item["id"]),
                    "hash": item["content_sha256"],
                    "invalid_reasons": invalid_reasons(conn, item),
                    "source_version": get(conn, "data_sources", item["source_id"])[
                        "record_version"
                    ],
                }
                for item in evidence
            ],
        }
    )
    return Evaluation(result, input_hash, used, evidence, signal_dependencies, lead)


def current_input(conn: Connection, score: dict[str, Any]) -> bool:
    """Legacy results without complete inputs fail closed; history is never backfilled."""
    if score["dependency_version"] != 1:
        return False
    inputs = rows(
        conn,
        "SELECT evidence_id FROM app.score_input_evidence WHERE score_id=:id ORDER BY evidence_id",
        {"id": score["id"]},
    )
    try:
        evaluated = evaluate(
            conn,
            ScoreInput(
                subject_id=score["subject_id"],
                icp_version_id=score["icp_version_id"],
                evidence_ids=[ref["evidence_id"] for ref in inputs],
            ),
        )
        return evaluated.input_hash == score["input_hash"]
    except BusinessError:
        return False
