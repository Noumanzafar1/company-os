from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from company_os.application.business import CoreCommands
from company_os.business_contracts import ScoreInput
from company_os.persistence.business import get, insert, update
from company_os.persistence.database import rows, transaction
from company_os.reporting.business import score, search
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.seeds.synthetic import key


def evidence_ids(conn, index):
    return [
        item["id"]
        for item in rows(
            conn,
            "SELECT id FROM app.evidence WHERE subject_id=:id ORDER BY id",
            {"id": key(f"a-account-{index}")},
        )
    ]


def test_retracted_support_creates_new_score_and_preserves_history(runtime):
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        savepoint = conn.begin_nested()
        payload = ScoreInput(
            subject_id=key("a-account-11"),
            icp_version_id=key("a-icp-version"),
            evidence_ids=evidence_ids(conn, 11),
        ).model_dump(mode="json")
        first = CoreCommands.score(conn, payload, None, None)
        assert CoreCommands.score(conn, payload, None, None)["id"] == first["id"]
        insert(
            conn,
            "evidence_retractions",
            {"evidence_id": key("a-evidence-11-problem"), "reason": "Synthetic support withdrawn"},
        )
        assert score(conn, first["id"]).current_support is False
        second = CoreCommands.score(conn, payload, None, None)
        assert second["id"] != first["id"]
        assert second["input_hash"] != first["input_hash"]
        assert second["known_points"] == 40
        assert get(conn, "scores", first["id"])["known_points"] == 85
        savepoint.rollback()


def test_source_revocation_and_document_revocation_take_effect_immediately(runtime):
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        savepoint = conn.begin_nested()
        old = rows(
            conn, "SELECT id FROM app.scores WHERE subject_id=:id", {"id": key("a-account-0")}
        )[0]
        source = get(conn, "data_sources", key("a-source-approved"))
        update(
            conn,
            "data_sources",
            source["id"],
            source["record_version"],
            {"rights_status": "revoked"},
        )
        assert score(conn, old["id"]).current_support is False
        document = get(conn, "documents", key("a-knowledge-document-approved"))
        update(conn, "documents", document["id"], document["record_version"], {"state": "revoked"})
        remaining = search(conn, "knowledge", 20)
        assert len(remaining) == 1 and remaining[0].status == "stale"
        savepoint.rollback()


def test_database_rejects_parent_cycle_wrong_owner_and_score_evidence_subject(runtime):
    for operation in ["parent", "owner", "evidence"]:
        with (
            pytest.raises(DBAPIError),
            transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn,
        ):
            if operation == "parent":
                update(conn, "accounts", key("a-account-0"), 1, {"parent_id": key("a-account-1")})
            elif operation == "owner":
                lead = get(conn, "leads", key("a-lead-0"))
                update(
                    conn,
                    "leads",
                    lead["id"],
                    lead["record_version"],
                    {"owner_principal_id": key("user-b")},
                )
            else:
                component = rows(
                    conn,
                    "SELECT c.id FROM app.score_components c JOIN app.scores s ON s.workspace_id=c.workspace_id AND s.id=c.score_id WHERE s.subject_id=:id AND c.component='fit'",
                    {"id": key("a-account-0")},
                )[0]
                insert(
                    conn,
                    "score_evidence",
                    {
                        "score_component_id": component["id"],
                        "evidence_id": key("a-evidence-1-problem"),
                    },
                )


def test_phase3_lifecycle_and_version_conflict(client, login):
    headers = login()
    prefix = f"/v1/workspaces/{key('workspace-a')}/leads/{key('a-lead-0')}"

    def command(suffix, body, version):
        return client.post(
            prefix + suffix,
            json=body,
            headers={**headers, "Idempotency-Key": str(uuid4()), "If-Match": str(version)},
        )

    lead = client.get(prefix, headers=headers).json()["data"]
    version = lead["record_version"]
    assert (
        command(
            "/complete-research", {"evidence_ids": [str(key("a-evidence-0-problem"))]}, version
        ).status_code
        == 409
    )
    assert (
        command("/begin-research", {"reason": "Local synthetic research"}, version).status_code
        == 200
    )
    required = [
        str(key(f"a-evidence-0-{fact}")) for fact in ["industry_code", "problem", "deal_capacity"]
    ]
    assert command("/complete-research", {"evidence_ids": required}, version).status_code == 409
    completed = command("/complete-research", {"evidence_ids": required}, version + 1)
    assert completed.status_code == 200, completed.text
    assert client.get(prefix, headers=headers).json()["data"]["state"] == "researched"
    assert client.post(prefix + "/assess-eligibility", json={}, headers=headers).status_code == 404
    assert command("/disqualify", {"reason": "No actual exclusion"}, version + 2).status_code == 423


def test_draft_definition_versions_immutable_and_scoring_versioned(client, login, runtime):
    headers = login()
    prefix = f"/v1/workspaces/{key('workspace-a')}"

    def post(path, body, version=None):
        return client.post(
            prefix + path,
            json=body,
            headers={
                **headers,
                "Idempotency-Key": str(uuid4()),
                **({"If-Match": str(version)} if version is not None else {}),
            },
        )

    parent = post("/icps", {"name": "Synthetic version test " + str(uuid4())}).json()["result_id"]
    body = {
        "criteria": {
            "industries": ["synthetic_services"],
            "countries": [],
            "required_problem_fact_keys": ["problem"],
            "target_roles": [],
            "required_evidence_keys": ["industry_code", "problem", "deal_capacity"],
        },
        "exclusions": {},
        "score_policy": {"version": "fixture-1"},
    }
    first = post(f"/icps/{parent}/versions", body, 1)
    assert first.status_code == 200, first.text
    assert post(f"/icps/{parent}/versions", body, 1).status_code == 409
    second = post(f"/icps/{parent}/versions", {**body, "score_policy": {"version": "fixture-2"}}, 2)
    assert second.status_code == 200
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        ids = [str(identifier) for identifier in evidence_ids(conn, 0)]
        assert get(conn, "icps", parent)["active_version_id"] is None
    scores = []
    for version in [first, second]:
        response = post(
            "/scores/calculate",
            {
                "subject_id": str(key("a-account-0")),
                "icp_version_id": version.json()["result_id"],
                "evidence_ids": ids,
            },
        )
        assert response.status_code == 200, response.text
        scores.append(
            client.get(prefix + "/scores/" + response.json()["result_id"], headers=headers).json()[
                "data"
            ]
        )
    assert scores[0]["policy_hash"] != scores[1]["policy_hash"]
    assert scores[0]["input_hash"] != scores[1]["input_hash"]
    assert scores[0]["known_points"] == scores[1]["known_points"] == "85.00"


def test_worker_has_no_new_business_grants(worker_env):
    from company_os.persistence.database import make_engine

    engine = make_engine(worker_env["WORKER_DATABASE_URL"])
    try:
        with pytest.raises(DBAPIError), transaction(engine) as conn:
            conn.execute(text("SELECT * FROM app.accounts"))
    finally:
        engine.dispose()


def test_unrelated_fact_cannot_be_registered_as_observed_signal(client, login):
    now = datetime.now(UTC)
    response = client.post(
        f"/v1/workspaces/{key('workspace-a')}/signals",
        headers={**login(), "Idempotency-Key": str(uuid4())},
        json={
            "subject_id": str(key("a-account-0")),
            "kind": "hiring",
            "observed_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
            "evidence_id": str(key("a-evidence-0-industry_code")),
            "relevance_summary": "Unsupported attempted event",
        },
    )
    assert response.status_code == 422


def test_cross_workspace_contact_and_grantee_fail_at_database(runtime):
    for kind in ["contact", "grant"]:
        with (
            pytest.raises(DBAPIError),
            transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn,
        ):
            if kind == "contact":
                value = f"synthetic-{uuid4().hex}@example.test"
                insert(
                    conn,
                    "contact_points",
                    {
                        "person_id": key("b-person-0"),
                        "kind": "email",
                        "value_original": value,
                        "value_normalized": value,
                        "match_key": value,
                        "status": "active",
                        "source_id": key("a-source-approved"),
                    },
                )
            else:
                insert(
                    conn,
                    "document_grants",
                    {
                        "document_id": key("a-rights-document"),
                        "principal_id": key("user-b"),
                        "permission": "read",
                    },
                )
