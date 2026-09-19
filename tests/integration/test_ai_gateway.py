"""Phase 6B real-role, contained-process and durable-accounting acceptance."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from company_os.ai.contracts import AIRequest
from company_os.application import ai_evaluations, ai_gateway
from company_os.persistence.ai import get
from company_os.persistence.database import rows, transaction
from company_os.workflow.runtime import execute_claim
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.integration.test_authority import PREFIX, post
from tests.integration.test_identity_review import offline_mfa as mfa_fixture
from tests.integration.test_runtime import WA, A, B, claim_exact
from tests.integration.test_runtime import engine as worker_fixture

engine = worker_fixture
offline_mfa = mfa_fixture


@pytest.fixture(autouse=True)
def dispatch_fixture_events(runtime):
    # These tests invoke execute_claim directly, without the outer worker's
    # maintenance loop. Drain their ordinary outbox batches so later acceptance
    # tests do not inherit a synthetic backlog from dozens of evaluation jobs.
    yield
    from company_os.application import runtime as commands

    with transaction(runtime, *A) as conn:
        for _ in range(10):
            if commands.dispatch_outbox(conn) == 0:
                break
        else:
            pytest.fail("AI fixture outbox did not drain")


def create(runtime, scenario="success"):
    with transaction(runtime, *A) as conn:
        return ai_gateway.submit(conn, AIRequest(scenario=scenario), uuid4().hex, uuid4())


def perform(runtime, engine, run):
    with transaction(runtime, *A) as conn:
        job = rows(conn, "SELECT * FROM app.jobs WHERE id=:id", {"id": run["job_id"]})[0]
    claim = claim_exact(engine, job)
    assert execute_claim(engine, WA, "ai-test", claim, None)
    with transaction(runtime, *A) as conn:
        return ai_gateway.inspect(conn, run["id"])


@pytest.mark.parametrize(
    "scenario,state,calls",
    [
        ("success", "accepted", 1),
        ("refusal", "refused", 1),
        ("incomplete", "incomplete", 1),
        ("repair", "accepted", 2),
        ("forged_evidence", "quarantined", 1),
        ("unsupported_claim", "quarantined", 1),
        ("injection", "accepted", 1),
        ("secret", "quarantined", 1),
        ("tool_url", "quarantined", 1),
        ("cross_workspace", "quarantined", 1),
        ("incorrect_usage", "quarantined", 1),
        ("max_calls", "quarantined", 1),
        ("budget_exhausted", "failed", 0),
        ("timeout", "uncertain", 1),
        ("fallback_denied", "quarantined", 1),
    ],
)
def test_durable_outcomes(runtime, engine, scenario, state, calls):
    run = create(runtime, scenario)
    detail = perform(runtime, engine, run)
    assert detail["state"] == state, detail
    assert len(detail["model_runs"]) == calls
    with transaction(runtime, *A) as conn:
        for call in detail["model_runs"]:
            reservation = rows(
                conn,
                "SELECT * FROM app.budget_reservations WHERE id=:id",
                {"id": call["reservation_id"]},
            )[0]
            assert reservation["state"] == (
                "uncertain" if call["confirmed_usd"] is None else "settled"
            )
        assert not rows(
            conn, "SELECT id FROM app.external_effects WHERE job_id=:id", {"id": run["job_id"]}
        )


def test_concurrent_idempotency_and_populated_rls(runtime, engine):
    key = uuid4().hex

    def submit(_):
        with transaction(runtime, *A) as conn:
            return ai_gateway.submit(conn, AIRequest(), key, uuid4())["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(submit, range(2)))
    assert ids[0] == ids[1]
    with transaction(runtime, *A) as conn:
        run = get(conn, "agent_runs", ids[0])
    perform(runtime, engine, run)
    with transaction(runtime, *B) as conn:
        for table in ["agent_runs", "model_runs", "context_packs", "ai_results"]:
            assert not rows(
                conn, f"SELECT id FROM app.{table} WHERE workspace_id=:id", {"id": A[1]}
            )
    with pytest.raises(DBAPIError), transaction(runtime, *A) as conn:
        conn.execute(text("UPDATE app.ai_routes SET version=version+1"))
    with pytest.raises(DBAPIError), transaction(engine, *WA) as conn:
        conn.execute(text("UPDATE app.ai_route_states SET state='active'"))


def test_context_revocation_withholds_accepted_result(runtime, engine):
    run = create(runtime)
    assert perform(runtime, engine, run)["result"]["status"] == "proposed"
    with transaction(runtime, *A) as conn:
        context = get(conn, "context_packs", run["context_id"])
        ai_gateway.revoke(conn, context["source_id"], 1)
        detail = ai_gateway.inspect(conn, run["id"])
        assert (
            detail["context"] is None and detail["result"] is None and not detail["context_current"]
        )
    second = create(runtime)
    assert second["context_id"] != run["context_id"]


def test_api_bounded_fields_and_idempotency(client, login):
    headers = {**login(), "Idempotency-Key": uuid4().hex}
    for forbidden in [
        "model_id",
        "provider",
        "api_key",
        "workspace_id",
        "route_id",
        "tools",
        "url",
    ]:
        assert (
            client.post(
                PREFIX + "/ai-tasks", json={forbidden: "untrusted"}, headers=headers
            ).status_code
            == 422
        )
    one = client.post(PREFIX + "/ai-tasks", json={"scenario": "success"}, headers=headers)
    assert one.status_code == 200, one.text
    two = client.post(PREFIX + "/ai-tasks", json={"scenario": "success"}, headers=headers)
    assert one.json() == two.json()
    assert (
        client.post(PREFIX + "/ai-tasks", json={"scenario": "refusal"}, headers=headers).status_code
        == 409
    )
    assert (
        client.get(PREFIX + "/ai-tasks/" + one.json()["data"]["id"], headers=login("b")).status_code
        == 404
    )


def test_frozen_comparison_and_exact_human_promotion(runtime, engine, client, offline_mfa):
    with transaction(runtime, *A) as conn:
        batch = ai_evaluations.request_evaluation(conn, "seed", uuid4())
        saved = get(conn, "ai_evaluation_batches", batch["id"])
        identifiers = sum(saved["body"]["runs"].values(), [])
    for identifier in identifiers:
        with transaction(runtime, *A) as conn:
            run = get(conn, "agent_runs", identifier)
        perform(runtime, engine, run)
    with transaction(engine, *WA) as conn:
        ai_evaluations.finalize(conn)
    with transaction(runtime, *A) as conn:
        evaluation = rows(
            conn, "SELECT * FROM app.ai_evaluations WHERE batch_id=:id", {"id": batch["id"]}
        )[0]
        assert evaluation["body"]["decision"] == "technical_pass"
        assert evaluation["current_result"]["decision"] == "technical_pass"
    proposal = post(
        client,
        offline_mfa,
        "/ai-routes/propose",
        {
            "route_id": str(evaluation["route_id"]),
            "evaluation_id": str(evaluation["id"]),
            "rollback_route_id": str(evaluation["current_route_id"]),
        },
    )
    assert proposal.status_code == 200, proposal.text
    identifier = proposal.json()["data"]["request_id"]
    detail = client.get(PREFIX + "/approvals/" + identifier, headers=offline_mfa).json()["data"]
    assert (
        post(
            client,
            offline_mfa,
            "/ai-routes/" + identifier + "/promote",
            {"rationale": "Synthetic review"},
            1,
        ).status_code
        == 423
    )
    decision = post(
        client,
        offline_mfa,
        "/approvals/" + identifier + "/decide",
        {
            "decision": "approve",
            "rationale": "Reviewed synthetic comparison",
            "expected_scope_hash": detail["request"]["scope_hash"],
        },
        1,
    )
    assert decision.status_code == 200, decision.text
    promoted = post(
        client,
        offline_mfa,
        "/ai-routes/" + identifier + "/promote",
        {"rationale": "Activate reviewed synthetic comparison"},
        2,
    )
    assert promoted.status_code == 200, promoted.text
    with transaction(runtime, *A) as conn:
        assert ai_gateway.active_route(conn)["id"] == evaluation["route_id"]


@pytest.mark.parametrize("split", ["development", "holdout", "adversarial"])
def test_all_frozen_datasets(runtime, engine, split):
    import json
    from pathlib import Path

    with transaction(runtime, *A) as conn:
        batch = ai_evaluations.request_evaluation(conn, split, uuid4())
        saved = get(conn, "ai_evaluation_batches", batch["id"])
        identifiers = sum(saved["body"]["runs"].values(), [])
    for identifier in identifiers:
        with transaction(runtime, *A) as conn:
            run = get(conn, "agent_runs", identifier)
        perform(runtime, engine, run)
    with transaction(engine, *WA) as conn:
        ai_evaluations.finalize(conn)
    with transaction(runtime, *A) as conn:
        evaluation = rows(
            conn, "SELECT * FROM app.ai_evaluations WHERE batch_id=:id", {"id": batch["id"]}
        )[0]
        assert evaluation["body"]["decision"] == "technical_pass"
        assert evaluation["current_result"]["decision"] == "technical_pass"
        output = Path(".local") / ("phase6b-evaluation-" + split + ".json")
        output.write_text(json.dumps(evaluation, default=str, indent=2) + "\n", encoding="utf-8")


def test_revocation_during_inference_rejects_late_output(runtime, engine):
    import time

    run = create(runtime, "delayed")
    with ThreadPoolExecutor(max_workers=1) as pool:
        work = pool.submit(perform, runtime, engine, run)
        for _ in range(100):
            with transaction(runtime, *A) as conn:
                started = rows(
                    conn, "SELECT id FROM app.model_runs WHERE agent_run_id=:id", {"id": run["id"]}
                )
            if started:
                break
            time.sleep(0.02)
        assert started
        with transaction(runtime, *A) as conn:
            context = get(conn, "context_packs", run["context_id"])
            ai_gateway.revoke(conn, context["source_id"], 1)
        result = work.result(timeout=10)
    assert result["result"] is None and not result["context_current"]
    assert result["state"] in {"quarantined", "uncertain"}


def test_uncertain_call_survives_restart_without_replay(runtime, engine, admin):
    from company_os.ai.contracts import AIRoute
    from company_os.application import runtime as commands
    from company_os.persistence.runtime import update

    run = create(runtime)
    with transaction(runtime, *A) as conn:
        job = rows(conn, "SELECT * FROM app.jobs WHERE id=:id", {"id": run["job_id"]})[0]
    claim = claim_exact(engine, job)
    with transaction(engine, *WA) as conn:
        current = commands.fenced(conn, claim)
        update(conn, "jobs", current, state="running")
        route = AIRoute.model_validate(get(conn, "ai_routes", run["route_id"])["body"])
        call = ai_gateway.reserve_call(conn, claim, run, route)
    # Simulate process loss after durable start and before any response.
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE app.jobs SET lease_expires_at=clock_timestamp()-interval '1 second',record_version=record_version+1 WHERE id=:id"
            ),
            {"id": job["id"]},
        )
    with transaction(engine, *WA) as conn:
        commands.recover(conn)
        ai_gateway.recover(conn)
        assert get(conn, "agent_runs", run["id"])["state"] == "uncertain"
        assert get(conn, "model_runs", call["id"])["status"] == "uncertain"
    result = perform(runtime, engine, run)
    assert result["state"] == "uncertain" and len(result["model_runs"]) == 1


def test_rate_limit_releases_slot_and_counts_second_call(runtime, engine):
    from company_os.persistence.runtime import clock

    run = create(runtime, "rate_limit")
    first = perform(runtime, engine, run)
    assert first["state"] == "retry_wait"
    with transaction(runtime, *A) as conn:
        job = rows(conn, "SELECT * FROM app.jobs WHERE id=:id", {"id": run["job_id"]})[0]
        assert job["lease_owner"] is None
        assert (job["available_at"] - clock(conn)).total_seconds() > 3
    second = perform(runtime, engine, run)
    assert len(second["model_runs"]) == 2 and second["state"] == "quarantined"
