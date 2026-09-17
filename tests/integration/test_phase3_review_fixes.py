from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from company_os.application.business import CoreCommands
from company_os.business_contracts import DocumentInput, ScoreInput
from company_os.persistence.business import BusinessError, get, insert, invalid_reasons, update
from company_os.persistence.database import rows, transaction
from company_os.reporting.business import score
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.seeds.synthetic import key


@pytest.fixture
def scoped(runtime):
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        savepoint = conn.begin_nested()
        yield conn
        savepoint.rollback()


def payload(conn, policy=None, extra=()):
    return ScoreInput(
        subject_id=key("a-account-11"),
        icp_version_id=policy or key("a-icp-version"),
        evidence_ids=[
            r["id"]
            for r in rows(
                conn,
                "SELECT id FROM app.evidence WHERE subject_id=:id ORDER BY id",
                {"id": key("a-account-11")},
            )
        ]
        + list(extra),
    ).model_dump(mode="json")


def fact(conn, field, kind, value):
    source = get(conn, "data_sources", key("a-source-approved"))
    if field not in source["allowed_fields"]:
        update(
            conn,
            "data_sources",
            source["id"],
            source["record_version"],
            {"allowed_fields": [*source["allowed_fields"], field]},
        )
    return CoreCommands.evidence(
        conn,
        {
            "subject_id": str(key("a-account-11")),
            "source_id": str(source["id"]),
            "provider_record_id": str(uuid4()),
            "fact_key": field,
            "fact_value": {"type": kind, "value": value},
            "observed_at": datetime.now(UTC) - timedelta(days=1),
            "expires_at": datetime.now(UTC) + timedelta(days=20),
            "entity_match": "confirmed",
            "fact_kind": "observed",
        },
        None,
        None,
    )


def policy(conn, *, employee_range=None, rules=()):
    original = get(conn, "icp_versions", key("a-icp-version"))
    values = {
        k: v
        for k, v in original.items()
        if k not in {"id", "workspace_id", "created_by", "created_at", "schema_version"}
    }
    values.update(
        version=99,
        content_hash="f" * 64,
        criteria={**values["criteria"], "employee_range": employee_range},
        exclusions={**values["exclusions"], "reason_rules": list(rules)},
    )
    return insert(conn, "icp_versions", values)["id"]


@pytest.mark.parametrize("change", ["expiry", "rejected", "unsupported"])
def test_exact_signal_dependency_invalidates_historical_score(scoped, change):
    conn = scoped
    body = payload(conn)
    first = CoreCommands.score(conn, body, None, None)
    view = score(conn, first["id"])
    assert view.current_support
    assert next(c.points for c in view.components if c.component == "trigger") == 20
    dependency = rows(
        conn, "SELECT * FROM app.score_signals WHERE score_id=:id", {"id": first["id"]}
    )[0]
    observed = get(conn, "signals", dependency["signal_id"])
    assert dependency["signal_version"] == observed["record_version"]
    if change == "unsupported":
        insert(
            conn,
            "evidence_retractions",
            {"evidence_id": observed["evidence_id"], "reason": "Synthetic support withdrawn"},
        )
    else:
        changes = (
            {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
            if change == "expiry"
            else {"status": "rejected"}
        )
        update(conn, "signals", observed["id"], observed["record_version"], changes)
        assert not invalid_reasons(conn, get(conn, "evidence", observed["evidence_id"]))
    assert not score(conn, first["id"]).current_support
    second = CoreCommands.score(conn, body, None, None)
    assert second["id"] != first["id"] and second["input_hash"] != first["input_hash"]
    assert "trigger" in second["missing_keys"]
    assert (
        next(c.points for c in score(conn, second["id"]).components if c.component == "trigger")
        is None
    )
    assert CoreCommands.score(conn, body, None, None)["id"] == second["id"]
    assert get(conn, "scores", first["id"]) == first
    assert rows(
        conn, "SELECT * FROM app.score_signals WHERE score_id=:id", {"id": first["id"]}
    ) == [dependency]


def test_exclusion_only_evidence_is_tracked_and_can_become_stale(scoped):
    conn = scoped
    support = fact(conn, "employee_count", "integer", 1)
    version = policy(
        conn,
        rules=[
            {"field": "employee_count", "operator": "lt", "value": 10, "reason_code": "too_small"}
        ],
    )
    body = payload(conn, version)
    first = CoreCommands.score(conn, body, None, None)
    assert "too_small" in first["hard_exclusions"]
    assert score(conn, first["id"]).current_support
    assert not rows(
        conn, "SELECT id FROM app.score_evidence WHERE evidence_id=:id", {"id": support["id"]}
    )
    assert rows(
        conn,
        "SELECT id FROM app.score_input_evidence WHERE score_id=:s AND evidence_id=:e",
        {"s": first["id"], "e": support["id"]},
    )
    insert(
        conn,
        "evidence_retractions",
        {"evidence_id": support["id"], "reason": "Exclusion fact withdrawn"},
    )
    assert not score(conn, first["id"]).current_support
    second = CoreCommands.score(conn, body, None, None)
    assert "too_small" not in second["hard_exclusions"]
    assert second["id"] != first["id"]
    assert get(conn, "scores", first["id"]) == first


@pytest.mark.parametrize(
    "field,observations,expected",
    [
        ("employee_count", [("integer", 1), ("string", "1")], None),
        ("deal_capacity", [("boolean", True), ("string", "True")], None),
        ("employee_count", [("integer", 1), ("integer", 1)], 30),
        ("deal_capacity", [("boolean", True), ("boolean", True)], 20),
        ("employee_count", [("integer", 1), ("integer", 2)], None),
        ("deal_capacity", [("boolean", True), ("boolean", False)], None),
        ("employee_count", [("string", "1")], None),
    ],
)
def test_typed_observations_do_not_silently_win(scoped, field, observations, expected):
    conn = scoped
    for kind, value in observations:
        fact(conn, field, kind, value)
    version = (
        policy(conn, employee_range={"min": 0, "max": 10}) if field == "employee_count" else None
    )
    result = CoreCommands.score(conn, payload(conn, version), None, None)
    component = "fit" if field == "employee_count" else "economics"
    actual = next(
        c.points for c in score(conn, result["id"]).components if c.component == component
    )
    assert actual == expected
    assert score(conn, result["id"]).current_support


@pytest.mark.parametrize(
    "kind,value",
    [
        ("email", "Synthetic+tag@EXAMPLE.TEST"),
        ("phone", "+15555550123"),
        ("url", "https://synthetic.example/profile"),
    ],
)
def test_contact_permission_is_email_only(scoped, kind, value):
    contact = CoreCommands.contact(
        scoped,
        {
            "account_id": str(key("a-account-11")),
            "kind": kind,
            "value": value,
            "source_id": str(key("a-source-approved")),
        },
        None,
        None,
    )
    assert contact["status"] == "active"
    assessments = rows(
        scoped,
        "SELECT * FROM app.permission_assessments WHERE contact_point_id=:id",
        {"id": contact["id"]},
    )
    if kind == "email":
        assert len(assessments) == 1
        assert assessments[0]["channel"] == "email" and assessments[0]["result"] == "unknown"
    else:
        assert assessments == []
    assert not rows(
        scoped, "SELECT id FROM app.suppressions WHERE contact_point_id=:id", {"id": contact["id"]}
    )


def signal_payload(conn):
    support = get(conn, "evidence", key("a-evidence-11-observed_trigger"))
    return {
        "subject_id": support["subject_id"],
        "kind": "expansion",
        "observed_at": support["observed_at"] + timedelta(hours=1),
        "event_at": datetime.now(UTC) + timedelta(days=10),
        "expires_at": datetime.now(UTC) + timedelta(days=20),
        "evidence_id": support["id"],
        "relevance_summary": "Synthetic future event announced earlier",
    }


@pytest.mark.parametrize("time_case", ["future", "before_evidence", "expiry_before_observation"])
def test_signal_chronology_application(scoped, time_case):
    body = signal_payload(scoped)
    if time_case == "future":
        body["observed_at"] = datetime.now(UTC) + timedelta(days=1)
    elif time_case == "before_evidence":
        body["observed_at"] -= timedelta(days=1)
    else:
        body["expires_at"] = body["observed_at"] - timedelta(seconds=1)
    with pytest.raises((BusinessError, ValueError)):
        CoreCommands.signal(scoped, body, None, None)


@pytest.mark.parametrize("time_case", ["future", "before_evidence", "expiry_before_observation"])
def test_signal_chronology_database(scoped, time_case):
    body = signal_payload(scoped)
    if time_case == "future":
        body["observed_at"] = datetime.now(UTC) + timedelta(days=1)
    elif time_case == "before_evidence":
        body["observed_at"] -= timedelta(days=1)
    else:
        body["expires_at"] = body["observed_at"] - timedelta(seconds=1)
    with pytest.raises(DBAPIError), scoped.begin_nested():
        insert(scoped, "signals", {**body, "status": "candidate", "fingerprint": "a" * 64})


def test_future_event_is_allowed_and_acceptance_reason_is_durable(scoped):
    body = signal_payload(scoped)
    record = CoreCommands.signal(scoped, body, None, None)
    accepted = CoreCommands.accept_signal(
        scoped, {"reason": "Synthetic observation reviewed"}, record["id"], 1
    )
    assert accepted["event_at"] > datetime.now(UTC)
    assert (
        get(scoped, "signals", record["id"])["acceptance_reason"]
        == "Synthetic observation reviewed"
    )


@pytest.mark.parametrize("table", ["score_input_evidence", "score_signals"])
def test_dependency_rows_reject_cross_workspace_evidence_and_mutation(scoped, table):
    result = CoreCommands.score(scoped, payload(scoped), None, None)
    existing = rows(scoped, f"SELECT * FROM app.{table} WHERE score_id=:id", {"id": result["id"]})[
        0
    ]
    values = {
        k: v
        for k, v in existing.items()
        if k not in {"id", "workspace_id", "created_at", "created_by", "schema_version"}
    }
    values["evidence_id"] = key("b-evidence-0-problem")
    with pytest.raises(DBAPIError), scoped.begin_nested():
        insert(scoped, table, values)
    with pytest.raises(DBAPIError), scoped.begin_nested():
        scoped.execute(
            text(f"UPDATE app.{table} SET schema_version=2 WHERE id=:id"), {"id": existing["id"]}
        )


def test_unused_document_purpose_is_not_silently_accepted():
    with pytest.raises(ValueError):
        DocumentInput.model_validate(
            {
                "external_file_id": "fixture:synthetic-guide",
                "classification": "internal",
                "purpose": "knowledge",
            }
        )


def test_signal_version_change_and_legacy_inputs_fail_closed(scoped):
    conn = scoped
    body = payload(conn)
    first = CoreCommands.score(conn, body, None, None)
    dependency = rows(
        conn, "SELECT * FROM app.score_signals WHERE score_id=:id", {"id": first["id"]}
    )[0]
    observed = get(conn, "signals", dependency["signal_id"])
    update(
        conn,
        "signals",
        observed["id"],
        observed["record_version"],
        {"expires_at": observed["expires_at"] + timedelta(days=1)},
    )
    assert not score(conn, first["id"]).current_support
    second = CoreCommands.score(conn, body, None, None)
    assert second["id"] != first["id"]
    assert score(conn, second["id"]).current_support
    assert (
        next(c.points for c in score(conn, second["id"]).components if c.component == "trigger")
        == 20
    )
    legacy = insert(
        conn,
        "scores",
        {
            **{
                k: v
                for k, v in first.items()
                if k not in {"id", "workspace_id", "created_at", "created_by"}
            },
            "input_hash": "0" * 64,
            "dependency_version": 0,
        },
    )
    assert not score(conn, legacy["id"]).current_support
    assert get(conn, "scores", first["id"]) == first
