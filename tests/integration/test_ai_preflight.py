"""B1 normal durable pipeline, actual API/worker roles, no provider network."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.metadata import version
from uuid import uuid4

import pytest
from company_os.ai.contracts import AIRequest, AIRoute
from company_os.ai.credentials import SelectedCredential, credential_binding, credential_reference
from company_os.ai.preflight import CapabilityReport
from company_os.application import ai_gateway, ai_preflight
from company_os.application.identity import IdentityService
from company_os.domain.identity import AccessDenied
from company_os.persistence.ai import get
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows, transaction
from company_os.workflow import ai_runtime
from company_os.workflow.isolation import execute as contained
from company_os.workflow.runtime import execute_claim
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import admin as admin
from tests.conftest import db_env as db_env
from tests.conftest import runtime as runtime
from tests.conftest import settings as settings
from tests.integration.test_ai_gateway import dispatch_fixture_events as dispatch_fixture_events
from tests.integration.test_identity_review import offline_mfa as offline_mfa
from tests.integration.test_runtime import WA, A, B, claim_exact
from tests.integration.test_runtime import engine as engine


@pytest.fixture
def identity(runtime, offline_mfa):
    return IdentityService(runtime, None).resolve(
        offline_mfa["Authorization"].removeprefix("Bearer ")
    )


def setup(
    runtime,
    identity,
    providers=("openai",),
    maximum=Decimal(5),
    scope=A,
    report_changes=None,
    credentials=None,
):
    with transaction(runtime, *scope) as conn:
        gate = ai_preflight.authorize(
            conn, identity, maximum, datetime.now(UTC) + timedelta(minutes=15)
        )
        ordinary = AIRoute.model_validate(ai_gateway.active_route(conn)["body"])
        links = []
        for provider in providers:
            route = ordinary.model_copy(
                update={
                    "route_id": uuid4(),
                    "selection": "preflight",
                    "primary_provider": provider,
                    "primary_model_id": "synthetic-b1-model",
                    "price_config_version": uuid4(),
                    "region_policy": "preflight_required",
                }
            )
            now = datetime.now(UTC)
            report = CapabilityReport(
                provider=provider,
                environment="test",
                model_id=route.primary_model_id,
                checked_at=now - timedelta(seconds=1),
                expires_at=now + timedelta(minutes=10),
                account_verified=True,
                structured_output=True,
                billing_verified=True,
                retention_approved=True,
                region_approved=True,
                rates_verified=True,
                requests_per_minute=1,
                input_token_limit=8000,
                output_token_limit=1500,
                sdk_version=version(provider),
                external_account_id="synthetic-account",
                credential_ref=credential_reference(scope[1], provider),
                credential_binding=credential_binding(
                    scope[1],
                    SelectedCredential(
                        provider,
                        (credentials or {}).get(provider, f"synthetic-{provider}-selected-canary"),
                    ),
                ),
            )
            if report_changes:
                report = report.model_copy(update=report_changes)
            price = {
                "provider": provider,
                "model_id": route.primary_model_id,
                "input": "1",
                "output": "2",
                "cached": "0.1",
                "cache_creation": "2",
                "verified_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
                "source": "synthetic B1 fixture, not current price",
            }
            c = rows(
                conn, "SELECT * FROM app.ai_provider_connections WHERE provider=:p", {"p": provider}
            )[0]
            links.append(
                ai_preflight.provision(
                    conn, identity, gate, c["id"], c["connection_version"], route, price, report
                )
            )
        return gate, links


def submit(runtime, identity, link):
    with transaction(runtime, *A) as conn:
        return ai_preflight.submit(conn, identity, link, uuid4().hex, uuid4())


def claim(runtime, engine, run):
    with transaction(runtime, *A) as conn:
        job = rows(conn, "SELECT * FROM app.jobs WHERE id=:id", {"id": run["job_id"]})[0]
    return claim_exact(engine, job)


def test_normal_pipeline_and_one_call(
    runtime, engine, identity, monkeypatch, client, offline_mfa, admin, caplog, capsys
):
    import secrets

    credentials = {p: "synthetic-" + secrets.token_hex(32) for p in ("openai", "anthropic")}
    gate, links = setup(runtime, identity, ("openai", "anthropic"), credentials=credentials)
    monkeypatch.setenv("OPENAI_API_KEY", credentials["openai"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", credentials["anthropic"])
    seen = []

    def execute(call, control, **kwargs):
        seen.append(call.route.primary_provider)
        assert all(value not in call.model_dump_json() for value in credentials.values())
        assert "credential_binding" not in call.model_dump_json()
        # This is the same child/SDK path with a closed in-child mock transport.
        return contained(call, control, contract_only=True, **kwargs)

    monkeypatch.setattr(ai_runtime, "execute", execute)
    for link in links:
        run = submit(runtime, identity, link)
        job = claim(runtime, engine, run)
        assert execute_claim(engine, WA, "b1-test", job, None)
        with transaction(runtime, *A) as conn:
            detail = ai_gateway.inspect(conn, run["id"])
            assert detail["state"] == "accepted", detail
            assert len(detail["model_runs"]) == 1
            assert detail["result"]["provider_request_id"] == "req_fixture"
            assert "selected-canary" not in str(detail)
        with pytest.raises((BusinessError, DBAPIError)), transaction(engine, *WA) as conn:
            ai_gateway.reserve_call(conn, job, run, AIRoute.model_validate(detail["route"]))
        with pytest.raises(DBAPIError):
            submit(runtime, identity, link)
    with transaction(runtime, *A) as conn:
        budget = get(conn, "ai_preflight_gates", gate)["budget_id"]
        b = rows(conn, "SELECT * FROM app.budgets WHERE id=:id", {"id": budget})[0]
        assert b["reserved_usd"] == 0 and b["spent_usd"] == Decimal("0.0004")
        assert ai_gateway.active_route(conn)["body"]["primary_provider"].startswith("fake_")
        for link in links:
            with (
                pytest.raises(BusinessError, match="LIVE_AUTHORIZATION_REQUIRED"),
                conn.begin_nested(),
            ):
                ai_gateway.submit(
                    conn,
                    AIRequest(),
                    uuid4().hex,
                    uuid4(),
                    evaluation_route=get(conn, "ai_preflight_routes", link)["route_id"],
                )
    assert seen == ["openai", "anthropic"]
    response = client.get(f"/v1/workspaces/{A[1]}/ai-health", headers=offline_mfa)
    assert response.status_code == 200
    visible = response.text + str(detail) + caplog.text + str(capsys.readouterr())
    assert "credential_binding" not in visible
    assert all(value not in visible for value in credentials.values())
    # Scan persisted application rows as the test owner, including technical reports.
    with admin.connect() as conn:
        tables = (
            conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='app'"))
            .scalars()
            .all()
        )
        for table in tables:
            records = str(conn.execute(text(f'SELECT to_jsonb(t) FROM app."{table}" t')).all())
            assert all(value not in records for value in credentials.values())


def test_concurrent_shared_budget(runtime, engine, identity):
    gate, links = setup(runtime, identity, ("openai", "anthropic"), maximum=Decimal("0.020"))
    runs = [submit(runtime, identity, link) for link in links]
    jobs = [claim(runtime, engine, run) for run in runs]
    from company_os.application import runtime as commands
    from company_os.persistence.runtime import update as runtime_update

    for job in jobs:
        with transaction(engine, *WA) as conn:
            current = commands.fenced(conn, job)
            current = runtime_update(conn, "jobs", current, state="running")
            commands.emit(conn, "job.started", current, "job")

    def reserve(i):
        try:
            with transaction(engine, *WA) as conn:
                route = AIRoute.model_validate(get(conn, "ai_routes", runs[i]["route_id"])["body"])
                return ai_gateway.reserve_call(conn, jobs[i], runs[i], route)["id"]
        except BusinessError as exc:
            assert exc.code == "BUDGET_EXHAUSTED"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert sum(r is not None for r in results) == 1
    with transaction(runtime, *A) as conn:
        b = rows(
            conn,
            "SELECT b.* FROM app.budgets b JOIN app.ai_preflight_gates g ON b.id=g.budget_id WHERE g.id=:g",
            {"g": gate},
        )[0]
        assert 0 < b["reserved_usd"] <= b["limit_usd"] and b["spent_usd"] == 0


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_selected_environment_substitution_denied_before_dispatch(
    runtime, engine, identity, monkeypatch, provider, caplog, capsys
):
    import secrets

    original = "synthetic-" + secrets.token_hex(32)
    replacement = "synthetic-" + secrets.token_hex(32)
    gate, links = setup(runtime, identity, (provider,), credentials={provider: original})
    run = submit(runtime, identity, links[0])
    job = claim(runtime, engine, run)
    slot = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[provider]
    monkeypatch.setenv(slot, replacement)
    monkeypatch.setattr(
        ai_runtime, "execute", lambda *_a, **_k: pytest.fail("Substituted credential dispatched")
    )
    assert execute_claim(engine, WA, "b1-substitution", job, None)
    with transaction(runtime, *A) as conn:
        detail = ai_gateway.inspect(conn, run["id"])
        assert detail["state"] == "uncertain" and detail["result"] is None
        assert len(detail["model_runs"]) == 1
        assert detail["model_runs"][0]["error_code"] == "PREFLIGHT_DISPATCH_DENIED"
        report = get(conn, "ai_preflight_routes", links[0])["report"]
        assert report["credential_binding"] == credential_binding(
            A[1], SelectedCredential(provider, original)
        )
        budget = rows(
            conn,
            "SELECT * FROM app.budgets WHERE id=:id",
            {"id": get(conn, "ai_preflight_gates", gate)["budget_id"]},
        )[0]
        assert budget["reserved_usd"] > 0 and budget["spent_usd"] == 0
    with pytest.raises((BusinessError, DBAPIError)), transaction(engine, *WA) as conn:
        ai_gateway.reserve_call(conn, job, run, AIRoute.model_validate(detail["route"]))
    visible = str(detail) + str(report) + caplog.text + str(capsys.readouterr())
    assert original not in visible and replacement not in visible


def test_rls_immutability_and_production_denial(runtime, engine, identity):
    gate, links = setup(runtime, identity)
    for db, scope in (
        (runtime, B),
        (engine, (WA[0], B[1], 1)),
        (runtime, (None, None, None)),
        (engine, (None, None, None)),
    ):
        with transaction(db, *scope) as conn:
            for table in ("ai_preflight_gates", "ai_preflight_routes"):
                assert not rows(
                    conn, f"SELECT id FROM app.{table} WHERE workspace_id=:w", {"w": A[1]}
                )
    for db, scope in ((runtime, A), (engine, WA)):
        with transaction(db, *scope) as conn:
            assert rows(conn, "SELECT id FROM app.ai_preflight_routes WHERE id=:i", {"i": links[0]})
            for sql in (
                "UPDATE app.ai_preflight_routes SET report='{}'",
                "DELETE FROM app.ai_preflight_gates",
                "UPDATE app.ai_provider_connections SET status='enabled' WHERE provider='openai'",
            ):
                with pytest.raises(DBAPIError), conn.begin_nested():
                    conn.execute(text(sql))
            route = get(conn, "ai_preflight_routes", links[0])["route_id"]
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(
                    text("UPDATE app.ai_route_states SET state='active' WHERE route_id=:r"),
                    {"r": route},
                )
    with pytest.raises((AccessDenied, BusinessError, DBAPIError)), transaction(runtime, *B) as conn:
        ai_preflight.submit(conn, identity, links[0], uuid4().hex, uuid4())
    with pytest.raises(DBAPIError), transaction(engine, *WA) as conn:
        conn.execute(
            text("SELECT app.preflight_gate(:s,5,clock_timestamp()+interval '1 minute')"),
            {"s": identity.session_id},
        )


@pytest.mark.parametrize(
    "scenario", ["malformed", "rate_limit", "overloaded", "uncertain", "revocation"]
)
def test_live_failure_never_repairs_retries_or_releases_uncertainty(
    runtime, engine, identity, monkeypatch, scenario
):
    from company_os.ai.contracts import ProviderReply
    from company_os.ai.providers import FakeOpenAIProvider
    from company_os.workflow.isolation import Outcome

    _, links = setup(runtime, identity, credentials={"openai": "synthetic-failure-canary"})
    run = submit(runtime, identity, links[0])
    job = claim(runtime, engine, run)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-failure-canary")
    seen = []

    def respond(call, control, **kwargs):
        seen.append(call.execution_id)
        if scenario == "revocation":
            with transaction(runtime, *A) as conn:
                source = get(conn, "context_packs", run["context_id"])["source_id"]
                ai_gateway.revoke(conn, source, 1)
        response = FakeOpenAIProvider().generate_typed(
            call.model_copy(
                update={"scenario": "success" if scenario == "revocation" else scenario}
            )
        )
        return Outcome(
            "RESULT",
            ProviderReply(
                execution_id=call.execution_id, input_hash=call.input_hash, response=response
            ),
            False,
            0,
            0,
            1,
            0,
            0,
        )

    monkeypatch.setattr(ai_runtime, "execute", respond)
    execute_claim(engine, WA, "b1-test", job, None)
    assert len(seen) == 1
    with transaction(runtime, *A) as conn:
        detail = ai_gateway.inspect(conn, run["id"])
        assert len(detail["model_runs"]) == 1
        assert detail["state"] not in {"accepted", "retry_wait"}
        reservation = rows(
            conn,
            "SELECT * FROM app.budget_reservations WHERE id=:id",
            {"id": detail["model_runs"][0]["reservation_id"]},
        )[0]
        if scenario in {"rate_limit", "overloaded", "uncertain"}:
            assert reservation["state"] == "uncertain"
        assert "synthetic-failure-canary" not in str(detail)


def test_fake_spend_and_stale_context_do_not_dispatch_live(runtime, engine, identity, monkeypatch):
    from tests.integration.test_ai_gateway import create, perform

    gate, links = setup(runtime, identity)
    perform(runtime, engine, create(runtime))
    with transaction(runtime, *A) as conn:
        b = rows(
            conn,
            "SELECT b.* FROM app.budgets b JOIN app.ai_preflight_gates g ON g.budget_id=b.id WHERE g.id=:id",
            {"id": gate},
        )[0]
        assert b["spent_usd"] == b["reserved_usd"] == 0
    run = submit(runtime, identity, links[0])
    with transaction(runtime, *A) as conn:
        ai_gateway.revoke(conn, get(conn, "context_packs", run["context_id"])["source_id"], 1)
    job = claim(runtime, engine, run)
    monkeypatch.setattr(
        ai_runtime,
        "resolve_selected",
        lambda *_: pytest.fail("Credential resolved before context gate"),
    )
    execute_claim(engine, WA, "b1-test", job, None)
    with transaction(runtime, *A) as conn:
        assert ai_gateway.inspect(conn, run["id"])["model_runs"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"billing_verified": False},
        {"retention_approved": False},
        {"region_approved": False},
        {"rates_verified": False},
        {"model_id": "wrong"},
        {"credential_ref": None},
        {"credential_ref": "OPENAI_API_KEY"},
        {"credential_ref": credential_reference(B[1], "openai")},
        {"credential_binding": None},
        {"credential_binding": "invalid"},
        {"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        {"checked_at": datetime.now(UTC) + timedelta(days=1)},
    ],
)
def test_unverified_configuration_rejected_before_persistence(runtime, identity, changes):
    with pytest.raises((BusinessError, DBAPIError)):
        setup(runtime, identity, report_changes=changes)


def test_populated_both_workspaces_and_cross_references(runtime, engine, identity, admin):
    from database.seeds.synthetic import key

    # Explicit disposable identity fixture: founder A is also assigned workspace B.
    # User B remains system administrator, with no founder authority.
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app.memberships(id,workspace_id,principal_id,role_id,status,created_by,updated_by) VALUES(:id,:w,:p,:r,'active',:p,:p)"
            ),
            {"id": uuid4(), "w": B[1], "p": A[0], "r": key("founder")},
        )
    ga, la = setup(runtime, identity)
    gb, lb = setup(runtime, identity, scope=(A[0], B[1], 1))
    for db in (runtime, engine):
        for scope in (A, B):
            actor = scope[0] if db is runtime else WA[0]
            with transaction(db, actor, scope[1], 1) as conn:
                role = rows(
                    conn,
                    "SELECT current_user name,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user",
                )[0]
                assert not role["rolsuper"] and not role["rolbypassrls"]
                for table in ("ai_preflight_gates", "ai_preflight_routes"):
                    found = rows(conn, f"SELECT workspace_id FROM app.{table}")
                    assert found and {r["workspace_id"] for r in found} == {scope[1]}
                    with pytest.raises(DBAPIError), conn.begin_nested():
                        conn.execute(text(f"INSERT INTO app.{table} DEFAULT VALUES"))
                    with pytest.raises(DBAPIError), conn.begin_nested():
                        conn.execute(text(f"DELETE FROM app.{table}"))
                    with pytest.raises(DBAPIError), conn.begin_nested():
                        conn.execute(
                            text(f"UPDATE app.{table} SET workspace_id=:w"),
                            {"w": B[1] if scope == A else A[1]},
                        )
    with transaction(runtime, *A) as conn:
        a = get(conn, "ai_preflight_routes", la[0])
        budget = get(conn, "ai_preflight_gates", ga)["budget_id"]
        own_gate = ai_preflight.authorize(
            conn, identity, Decimal(5), datetime.now(UTC) + timedelta(minutes=5)
        )
        own_route = get(conn, "ai_routes", a["route_id"])
    with transaction(runtime, *B) as conn:
        b = get(conn, "ai_preflight_routes", lb[0])
    for field in ("gate_id", "route_id", "connection_id"):
        with pytest.raises(DBAPIError, match="foreign key"), transaction(admin, *A) as conn:
            from company_os.ai.validation import digest
            from company_os.persistence.ai import insert

            clone_id = uuid4()
            body = {**own_route["body"], "route_id": str(clone_id)}
            insert(
                conn,
                "ai_routes",
                {**own_route, "id": clone_id, "body": body, "content_hash": digest(body)},
            )
            fields = {
                **a,
                "id": uuid4(),
                "gate_id": own_gate,
                "route_id": clone_id,
                field: b[field],
            }
            conn.execute(
                text(
                    "INSERT INTO app.ai_preflight_routes(id,workspace_id,created_by,gate_id,route_id,connection_id,connection_version,report,provider) VALUES(:id,:workspace_id,:created_by,:gate_id,:route_id,:connection_id,:connection_version,CAST(:report AS jsonb),:provider)"
                ),
                {**fields, "report": __import__("json").dumps(fields["report"])},
            )
    with pytest.raises(DBAPIError, match="foreign key"), admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app.ai_preflight_gates(id,workspace_id,created_by,session_id,budget_id,expires_at) VALUES(:id,:w,:p,:s,:b,clock_timestamp()+interval '5 minutes')"
            ),
            {"id": uuid4(), "w": B[1], "p": A[0], "s": identity.session_id, "b": budget},
        )


@pytest.mark.parametrize(
    "provider,status,reference",
    [
        ("openai", "enabled", None),
        ("fake_openai", "enabled", "preflight:x:openai"),
        ("openai", "testing", "arbitrary"),
        ("anthropic", "testing", credential_reference(A[1], "openai")),
    ],
)
def test_connection_constraints_even_for_owner(admin, provider, status, reference):
    with pytest.raises(DBAPIError, match="check constraint"), admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app.ai_provider_connections(id,workspace_id,created_by,provider,status,environment,credential_ref,report) VALUES(:id,:w,:p,:provider,:status,'technical',:ref,'{}')"
            ),
            {
                "id": uuid4(),
                "w": A[1],
                "p": A[0],
                "provider": provider,
                "status": status,
                "ref": reference,
            },
        )


def test_populated_downgrade_refuses_and_budget_cannot_be_forged(runtime, engine, identity, db_env):
    import subprocess
    import sys

    gate, _ = setup(runtime, identity)
    with transaction(runtime, *A) as conn:
        budget = get(conn, "ai_preflight_gates", gate)["budget_id"]
    for db, scope in ((runtime, A), (engine, WA)):
        for change in ("limit_usd=limit_usd+1", "reserved_usd=reserved_usd+0.001"):
            with pytest.raises(DBAPIError), transaction(db, *scope) as conn:
                conn.execute(
                    text(
                        f"UPDATE app.budgets SET {change},record_version=record_version+1,updated_by=app.current_principal_id() WHERE id=:id"
                    ),
                    {"id": budget},
                )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0026_phase6b_review_fixes"],
        env=db_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0 and "Preserve preflight authorization/history" in result.stderr
    with transaction(runtime, *A) as conn:
        assert get(conn, "ai_preflight_gates", gate)["budget_id"] == budget
        assert (
            rows(conn, "SELECT version_num FROM alembic_version")[0]["version_num"]
            == "0027_phase6b_live_preflight"
        )
