"""Explicit synthetic configuration provisioning; never runs at API startup."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from company_os.ai.contracts import AIRoute
from company_os.ai.validation import PROMPT, digest, schema
from company_os.persistence.ai import insert
from company_os.persistence.authority import insert as authority_insert
from company_os.persistence.database import rows, transaction
from company_os.persistence.runtime import insert as runtime_insert
from sqlalchemy import Engine

from database.seeds.synthetic import key

CASES = {
    "seed": ["success", "refusal"],
    "development": ["repair", "incomplete", "invalid_schema"],
    "holdout": ["delayed", "forged_evidence", "unsupported_claim"],
    "adversarial": [
        "injection",
        "secret",
        "tool_url",
        "tool_shell",
        "cross_workspace",
        "authority",
        "oversized",
        "incorrect_usage",
    ],
}


def seed_ai(engine: Engine) -> None:
    for letter in ("a", "b"):
        with transaction(engine, key("user-" + letter), key("workspace-" + letter), 1) as conn:
            if rows(
                conn,
                "SELECT id FROM app.ai_registry WHERE workspace_id=app.current_workspace_id() LIMIT 1",
            ):
                continue
            now = datetime.now(UTC)
            insert(
                conn,
                "ai_fixture_sources",
                {
                    "document_id": uuid4(),
                    "evidence_id": uuid4(),
                    "expires_at": now + timedelta(days=90),
                    "observed_at": now,
                    "excerpt": "Synthetic engineering document: fixture_colour is blue. No business facts are available.",
                },
            )
            prompt = insert(
                conn,
                "ai_registry",
                {
                    "kind": "prompt",
                    "name": "gateway-contract",
                    "version": 1,
                    "body": {
                        "text": PROMPT,
                        "allowed_sections": ["evidence", "excerpts", "omissions"],
                        "task_version": 1,
                    },
                    "content_hash": digest(
                        {
                            "text": PROMPT,
                            "allowed_sections": ["evidence", "excerpts", "omissions"],
                            "task_version": 1,
                        }
                    ),
                },
            )
            output = insert(
                conn,
                "ai_registry",
                {
                    "kind": "schema",
                    "name": "gateway-output",
                    "version": 1,
                    "body": schema(),
                    "content_hash": digest(schema()),
                },
            )
            for split, cases in CASES.items():
                body = {
                    "split": split,
                    "cases": cases,
                    "label_source": "synthetic engineering fixtures",
                    "business_quality": "FOUNDER_LABELLED_DATASET_REQUIRED",
                }
                insert(
                    conn,
                    "ai_registry",
                    {
                        "kind": "dataset",
                        "name": split,
                        "version": 1,
                        "body": body,
                        "content_hash": digest(body),
                    },
                )
            for provider in ("fake_openai", "fake_anthropic", "openai", "anthropic"):
                fake = provider.startswith("fake_")
                insert(
                    conn,
                    "ai_provider_connections",
                    {
                        "provider": provider,
                        "status": "enabled" if fake else "unconfigured",
                        "environment": "technical",
                        "report": {
                            "capability": "verified_offline_fixture" if fake else "unverified",
                            "account_verified": False,
                            "live_authorized": False,
                        },
                    },
                )
                if not fake:
                    continue
                model = "fake-openai-v1" if provider == "fake_openai" else "fake-anthropic-v1"
                price = {
                    "provider": provider,
                    "model_id": model,
                    "input": "1",
                    "output": "2",
                    "cached": "0.1",
                    "cache_creation": "2",
                    "expires_at": (now + timedelta(days=90)).isoformat(),
                    "verified_at": now.isoformat(),
                    "source": "synthetic engineering rate; not live provider pricing",
                }
                rate = insert(
                    conn,
                    "ai_registry",
                    {
                        "kind": "price",
                        "name": provider,
                        "version": 1,
                        "body": price,
                        "content_hash": digest(price),
                    },
                )
                target = authority_insert(
                    conn, "authority_test_targets", {"label": "Synthetic AI route " + provider}
                )
                identifier = uuid4()
                route = AIRoute(
                    route_id=identifier,
                    version=1,
                    primary_provider=provider,
                    primary_model_id=model,
                    prompt_version=prompt["id"],
                    schema_version=output["id"],
                    price_config_version=rate["id"],
                )
                body = route.model_dump(mode="json")
                insert(
                    conn,
                    "ai_routes",
                    {
                        "id": identifier,
                        "version": 1,
                        "body": body,
                        "content_hash": digest(body),
                        "prompt_id": prompt["id"],
                        "schema_id": output["id"],
                        "price_id": rate["id"],
                        "target_id": target["id"],
                    },
                )
                insert(
                    conn,
                    "ai_route_states",
                    {
                        "route_id": identifier,
                        "state": "active" if provider == "fake_openai" else "draft",
                    },
                )
            for period in ("day", "month"):
                runtime_insert(
                    conn,
                    "budgets",
                    {
                        "category": "ai_technical_" + period,
                        "period_start": now.replace(
                            hour=0,
                            minute=0,
                            second=0,
                            microsecond=0,
                            day=now.day if period == "day" else 1,
                        ),
                        "period_end": (
                            now.replace(hour=0, minute=0, second=0, microsecond=0)
                            + timedelta(days=1)
                        )
                        if period == "day"
                        else (
                            (now.replace(day=28) + timedelta(days=4)).replace(
                                day=1, hour=0, minute=0, second=0, microsecond=0
                            )
                        ),
                        "limit_usd": "10",
                        "status": "active",
                    },
                )
