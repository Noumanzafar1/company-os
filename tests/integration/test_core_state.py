from uuid import uuid4

import pytest
from company_os.business_contracts import AccountInput
from company_os.persistence.business import get, insert, invalid_reasons
from company_os.persistence.database import rows, transaction
from company_os.reporting.business import score, search
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.seeds.synthetic import key
from tests.phase3_scope import CORE_TABLES


def scope(runtime, letter="a"):
    return transaction(runtime, key(f"user-{letter}"), key(f"workspace-{letter}"), 1)


@pytest.mark.parametrize("table", sorted(CORE_TABLES))
def test_all_core_tables_actual_runtime_missing_and_wrong_scope(runtime, table):
    with transaction(runtime) as conn:
        assert conn.execute(text(f"SELECT * FROM app.{table}")).all() == []
    with transaction(runtime, key("user-a"), key("workspace-b"), 1) as conn:
        assert conn.execute(text(f"SELECT * FROM app.{table}")).all() == []
    with scope(runtime) as conn:
        assert all(
            row["workspace_id"] == key("workspace-a")
            for row in rows(conn, f"SELECT workspace_id FROM app.{table}")
        )


def test_shared_domains_names_and_parent_remain_distinct(runtime):
    with scope(runtime) as conn:
        shared = rows(
            conn,
            "SELECT id,parent_id FROM app.accounts WHERE primary_domain='shared.synthetic.example' ORDER BY parent_id NULLS FIRST",
        )
        assert len(shared) == 2
        assert shared[1]["parent_id"] == shared[0]["id"]
        assert (
            len(rows(conn, "SELECT id FROM app.people WHERE display_name='Synthetic Alex Example'"))
            == 2
        )
        assert len(rows(conn, "SELECT id FROM app.accounts")) >= 12
    with scope(runtime, "b") as conn:
        assert len(rows(conn, "SELECT id FROM app.accounts")) >= 10


def test_runtime_cannot_create_cross_workspace_parent_or_source(runtime):
    for field, bad in [("parent_id", key("b-account-0")), ("source_id", key("b-source-approved"))]:
        with pytest.raises(DBAPIError) as error, scope(runtime) as conn:
            data = AccountInput(
                display_name="Synthetic FK test",
                primary_domain="fk-test.example",
                identity_discriminator=str(uuid4()),
                source_id=key("a-source-approved"),
            ).model_dump()
            insert(conn, "accounts", {**data, field: bad, "status": "active"})
        assert error.value.orig.sqlstate == "23503"


@pytest.mark.parametrize(
    "table,column,foreign",
    [
        ("employments", "person_id", "b-person-0"),
        ("employments", "account_id", "b-account-0"),
        ("leads", "account_id", "b-account-0"),
        ("leads", "icp_version_id", "b-icp-version"),
        ("leads", "offer_version_id", "b-offer-version"),
        ("document_versions", "document_id", "b-rights-document"),
        ("knowledge_items", "document_version_id", "b-rights-version"),
        ("evidence", "subject_id", "b-account-0"),
        ("evidence", "source_id", "b-source-approved"),
    ],
)
def test_cross_tenant_children_rejected_by_database(runtime, table, column, foreign):
    # Isolate the FK itself from application semantic guards and unique constraints:
    # update a deferred FK inside a rollback-only test transaction; immutable rows
    # are cloned with unique keys and checked at commit.
    with scope(runtime) as conn:
        item = rows(conn, f"SELECT * FROM app.{table} ORDER BY created_at,id LIMIT 1")[0]
    values = {
        k: v
        for k, v in item.items()
        if k
        not in {
            "id",
            "workspace_id",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "record_version",
            "schema_version",
            "resource_type",
        }
    }
    values[column] = key(foreign)
    if table == "document_versions":
        values["version"] = 9999
        values["export_sha256"] = uuid4().hex * 2
    if table == "evidence":
        values["content_sha256"] = uuid4().hex * 2
    if table == "employments":
        values["title"] = "Synthetic foreign relationship " + str(uuid4())
    with pytest.raises(DBAPIError) as error, scope(runtime) as conn:
        insert(conn, table, values)
    assert error.value.orig.sqlstate in {"23503", "23514"}
    # For employment the subject-evidence guard rejects before FK; every FK is
    # separately inspected below to prove its composite workspace structure.


def test_every_new_foreign_reference_is_composite_and_runtime_is_nonowner(admin, runtime):
    with admin.connect() as conn:
        foreign = rows(
            conn,
            """SELECT c.conname, pg_get_constraintdef(c.oid) AS definition, t.relname FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace JOIN pg_class parent ON parent.oid=c.confrelid WHERE n.nspname='app' AND c.contype='f' AND t.relname=ANY(:tables) AND parent.relname=ANY(:tables)""",
            {"tables": list(CORE_TABLES)},
        )
        assert len(foreign) >= 60
        assert all("FOREIGN KEY (workspace_id," in item["definition"] for item in foreign)
    with scope(runtime) as conn:
        assert conn.execute(text("SELECT current_user")).scalar_one() == "company_api"


def test_resource_spoofing_or_missing_child_cannot_commit(runtime):
    for kind in ["campaign", "account", "person"]:
        with pytest.raises(DBAPIError), scope(runtime) as conn:
            insert(conn, "resources", {"resource_type": kind})
    with pytest.raises(DBAPIError), scope(runtime) as conn:
        row = get(conn, "accounts", key("a-account-0"))
        insert(conn, "resources", {"resource_type": "person"}, identifier=row["id"])


def test_retractions_expiry_and_rights_are_current_query_inputs(runtime):
    with scope(runtime) as conn:
        cases = [
            (4, "problem", "retracted"),
            (5, "deal_capacity", "evidence_expired"),
            (6, "problem", "source_not_allowed"),
            (7, "problem", "source_not_allowed"),
        ]
        for index, fact, reason in cases:
            item = get(conn, "evidence", key(f"a-evidence-{index}-{fact}"))
            assert reason in invalid_reasons(conn, item)
        assert invalid_reasons(conn, get(conn, "evidence", key("a-evidence-0-problem"))) == []


def test_seed_scores_missingness_and_exclusion(runtime):
    with scope(runtime) as conn:
        scores = {}
        for index in [0, 2, 3, 4, 5, 6]:
            identifier = rows(
                conn,
                "SELECT id FROM app.scores WHERE subject_id=:id",
                {"id": key(f"a-account-{index}")},
            )[0]["id"]
            scores[index] = score(conn, identifier)
        assert scores[0].known_points == 85
        assert scores[0].missing_keys == ["role"]
        assert scores[2].known_points == 65
        assert "trigger" in scores[2].missing_keys
        assert scores[3].known_points == 85 and scores[3].priority == "excluded"
        assert scores[4].known_points == 40
        assert scores[6].known_points == 0


def test_knowledge_search_isolation_stale_and_revoked(runtime):
    with scope(runtime) as conn:
        hits = search(conn, "knowledge", 20)
        assert len(hits) == 2
        assert {hit.status for hit in hits} == {"approved", "stale"}
        assert all(
            "Synthetic A" in hit.excerpt and "Synthetic B" not in hit.excerpt for hit in hits
        )
        assert all("revoked" not in hit.excerpt for hit in hits)
    with scope(runtime, "b") as conn:
        assert all("Synthetic B" in hit.excerpt for hit in search(conn, "knowledge", 20))


def test_append_history_and_contact_values_cannot_change(runtime):
    for query in [
        "UPDATE app.evidence SET fact_key='changed'",
        "DELETE FROM app.scores",
        "UPDATE app.icp_versions SET version=99",
        "UPDATE app.offer_versions SET scope='changed'",
        "UPDATE app.contact_points SET value_original='changed',record_version=record_version+1",
    ]:
        with pytest.raises(DBAPIError), scope(runtime) as conn:
            conn.execute(text(query))


def test_api_commands_idempotency_expected_version_and_safe_cross_tenant(client, login):
    headers = {**login(), "Idempotency-Key": str(uuid4())}
    prefix = f"/v1/workspaces/{key('workspace-a')}"
    body = {
        "display_name": "Synthetic API account",
        "primary_domain": "api.synthetic.example",
        "identity_discriminator": str(uuid4()),
        "source_id": str(key("a-source-approved")),
    }
    first = client.post(prefix + "/accounts", headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert client.post(prefix + "/accounts", headers=headers, json=body).json() == first.json()
    assert (
        client.post(
            prefix + "/accounts", headers={**headers, "Idempotency-Key": str(uuid4())}, json=body
        ).status_code
        == 409
    )
    assert (
        client.post(
            prefix + "/accounts", headers=headers, json={**body, "display_name": "Changed"}
        ).status_code
        == 409
    )
    assert (
        client.get(prefix + f"/accounts/{key('b-account-0')}", headers=headers).status_code == 404
    )
    assert client.get(prefix + "/accounts", headers=headers).status_code == 200
    for bad in ["expired", "revoked", "pending"]:
        response = client.post(
            prefix + "/accounts",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={**body, "source_id": str(key(f"a-source-{bad}"))},
        )
        assert response.status_code == 423
    assert (
        client.post(
            prefix + "/accounts", headers={**headers, "Origin": "https://evil.example"}, json=body
        ).status_code
        == 403
    )


def test_signed_cursor_cannot_cross_scope_or_be_tampered(client, login):
    headers = login()
    prefix = f"/v1/workspaces/{key('workspace-a')}"
    first = client.get(prefix + "/accounts?limit=2", headers=headers).json()
    cursor = first["next_cursor"]
    second = client.get(
        prefix + "/accounts", params={"limit": 2, "cursor": cursor}, headers=headers
    )
    assert second.status_code == 200
    assert set(item["id"] for item in first["data"]).isdisjoint(
        item["id"] for item in second.json()["data"]
    )
    assert (
        client.get(prefix + "/people", params={"cursor": cursor}, headers=headers).status_code
        == 400
    )
    assert (
        client.get(
            prefix + "/accounts",
            params={"cursor": cursor[:-1] + ("0" if cursor[-1] != "0" else "1")},
            headers=headers,
        ).status_code
        == 400
    )


def test_normal_synthetic_login_cannot_merge_and_admin_cannot_read_business(client, login):
    payload = {
        "survivor_id": str(key("a-account-8")),
        "retired_id": str(key("a-account-9")),
        "survivor_version": 1,
        "retired_version": 1,
        "reason": "Synthetic review",
        "evidence_ids": [str(key("a-evidence-8-problem"))],
    }
    response = client.post(
        f"/v1/workspaces/{key('workspace-a')}/identities/merge",
        headers={**login(), "Idempotency-Key": str(uuid4())},
        json=payload,
    )
    assert response.status_code == 403
    b = login("b")
    assert client.get(f"/v1/workspaces/{key('workspace-b')}/accounts", headers=b).status_code == 403
    assert client.get(f"/v1/workspaces/{key('workspace-a')}/accounts", headers=b).status_code == 404
