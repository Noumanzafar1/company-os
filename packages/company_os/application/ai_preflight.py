"""Founder-only technical provisioning, with no credential or network access."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from company_os.ai.contracts import AIRequest, AIRoute, AITask, ContextPack, ProviderCall, Usage
from company_os.ai.preflight import CapabilityReport, live_precheck
from company_os.ai.validation import cost, digest
from company_os.application import authority, runtime
from company_os.domain.identity import SessionIdentity
from company_os.persistence.ai import get
from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows
from company_os.persistence.runtime import clock


def authorize(
    conn: Connection, identity: SessionIdentity, maximum: Decimal, expires: datetime
) -> UUID:
    authority.gate(conn)
    authority.founder(conn, identity)
    identifier: UUID = conn.execute(
        text("SELECT app.preflight_gate(:s,:m,:e)"),
        {"s": identity.session_id, "m": maximum, "e": expires},
    ).scalar_one()
    runtime.audit(conn, "ai.preflight_authorized", identifier, identifier)
    return identifier


def provision(
    conn: Connection,
    identity: SessionIdentity,
    gate_id: UUID,
    connection_id: UUID,
    expected_version: int,
    route: AIRoute,
    price: dict[str, Any],
    report: CapabilityReport,
) -> UUID:
    authority.gate(conn)
    authority.founder(conn, identity)
    # Persist no caller-selected prompt or schema: reuse the accepted closed contract.
    from company_os.ai.validation import PROMPT, schema

    if (
        get(conn, "ai_registry", route.prompt_version)["body"]["text"] != PROMPT
        or get(conn, "ai_registry", route.schema_version)["body"] != schema()
        or route.selection != "preflight"
        or route.primary_provider != report.provider
        or route.primary_model_id != report.model_id
        or route.fallback_provider is not None
        or route.fallback_model_id is not None
        or not 1 <= route.max_input_tokens <= 8000
        or not 1 <= route.max_output_tokens <= 1500
        or not 1 <= route.timeout_seconds <= 60
    ):
        raise BusinessError("LIVE_PREFLIGHT_BINDING_REQUIRED", 423)
    now = clock(conn)
    if set(price) != {
        "provider",
        "model_id",
        "input",
        "output",
        "cached",
        "cache_creation",
        "verified_at",
        "expires_at",
        "source",
    }:
        raise BusinessError("INVALID_PRICE", 423)
    for field in ("input", "output", "cached", "cache_creation"):
        rate = Decimal(str(price[field]))
        if not rate.is_finite() or not Decimal(0) <= rate <= Decimal(10000):
            raise BusinessError("INVALID_PRICE", 423)
    if (
        datetime.fromisoformat(price["verified_at"]) > now
        or datetime.fromisoformat(price["expires_at"]) <= now
        or cost(
            Usage(input_tokens=route.max_input_tokens, output_tokens=route.max_output_tokens), price
        )
        <= 0
    ):
        raise BusinessError("INVALID_PRICE", 423)
    body = route.model_dump(mode="json")
    conn.execute(
        text(
            "SELECT set_config('app.preflight_route_hash',:r,true),set_config('app.preflight_price_hash',:p,true)"
        ),
        {"r": digest(body), "p": digest(price)},
    )
    identifier: UUID = conn.execute(
        text(
            "SELECT app.preflight_provision(:s,:g,:c,:v,CAST(:r AS jsonb),CAST(:p AS jsonb),CAST(:report AS jsonb))"
        ),
        {
            "s": identity.session_id,
            "g": gate_id,
            "c": connection_id,
            "v": expected_version,
            "r": json.dumps(body),
            "p": json.dumps(price),
            "report": report.model_dump_json(),
        },
    ).scalar_one()
    runtime.audit(conn, "ai.preflight_provisioned", identifier, identifier)
    return identifier


def submit(
    conn: Connection, identity: SessionIdentity, preflight_id: UUID, key: str, correlation: UUID
) -> dict[str, Any]:
    from company_os.application.ai_gateway import _submit

    authority.gate(conn)
    authority.founder(conn, identity)
    link = get(conn, "ai_preflight_routes", preflight_id)
    if not current(conn, preflight_id):
        raise BusinessError("PROVIDER_PREFLIGHT_REQUIRED", 423)
    conn.execute(
        text("SELECT set_config('app.preflight_session',:s,true)"), {"s": str(identity.session_id)}
    )
    return _submit(
        conn, AIRequest(), "preflight:" + str(preflight_id) + ":" + key, correlation, preflight=link
    )


def current(conn: Connection, identifier: UUID) -> bool:
    return bool(
        conn.execute(text("SELECT app.preflight_current(:id)"), {"id": identifier}).scalar_one()
    )


def check(conn: Connection, run: dict[str, Any], route: AIRoute) -> dict[str, Any]:
    link = get(conn, "ai_preflight_routes", run["preflight_id"])
    gate = get(conn, "ai_preflight_gates", link["gate_id"])
    budget = rows(conn, "SELECT * FROM app.budgets WHERE id=:id", {"id": gate["budget_id"]})[0]
    task = AITask.model_validate(run["task"])
    registry = get(conn, "ai_registry", route.price_config_version)
    price = registry["body"]
    if (
        registry["content_hash"] != digest(price)
        or price["provider"] != route.primary_provider
        or price["model_id"] != route.primary_model_id
        or not datetime.fromisoformat(price["verified_at"])
        <= clock(conn)
        < datetime.fromisoformat(price["expires_at"])
    ):
        raise BusinessError("PRICE_EXPIRED_OR_UNVERIFIED", 423)
    call = ProviderCall(
        execution_id=run["id"],
        input_hash="precheck",
        task=task,
        context=ContextPack.model_validate(get(conn, "context_packs", run["context_id"])["body"]),
        route=route,
        scenario="success",
        ordinal=1,
        prompt="",
        output_schema={},
        hard_timeout_seconds=task.timeout_seconds,
    )
    code = live_precheck(call, CapabilityReport.model_validate(link["report"]), budget["limit_usd"])
    if code or not current(conn, link["id"]):
        raise BusinessError(code or "PROVIDER_PREFLIGHT_REQUIRED", 423)
    return {"link": link, "gate": gate, "budget": budget}
