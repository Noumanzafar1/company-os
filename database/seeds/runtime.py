"""Explicit idempotent Phase 4 synthetic fixtures; never application startup DDL."""

from datetime import UTC, datetime, timedelta

from company_os.application.runtime import digest
from company_os.application.scheduler import next_daily
from company_os.persistence.database import transaction
from company_os.persistence.runtime import insert
from sqlalchemy import Engine, text

from database.seeds.synthetic import key


def seed_runtime(engine: Engine) -> None:
    founder = key("user-a")
    with engine.begin() as conn:
        for period in ("day", "month"):
            conn.execute(
                text(
                    "INSERT INTO app.company_runtime_caps(id,period_start,period_end,category,limit_usd) VALUES(:id,date_trunc(:period,now()),date_trunc(:period,now())+CAST(:span AS interval),'synthetic',100) ON CONFLICT DO NOTHING"
                ),
                {"id": key("company-cap-" + period), "period": period, "span": "1 " + period},
            )
        conn.execute(
            text(
                "UPDATE app.service_identities SET capability_profile='phase-4-fake-runtime',record_version=record_version+1 WHERE name='foundation-worker' AND capability_profile='heartbeat-only'"
            )
        )
        for letter in ("a", "b"):
            conn.execute(
                text(
                    "INSERT INTO app.memberships(id,workspace_id,principal_id,role_id,status,created_by,updated_by) VALUES(:id,:w,:p,:r,'active',:actor,:actor) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": key("runtime-member-" + letter),
                    "w": key("workspace-" + letter),
                    "p": key("worker"),
                    "r": key("system_administrator"),
                    "actor": founder,
                },
            )
    for letter in ("a", "b"):
        with transaction(engine, key("user-" + letter), key("workspace-" + letter), 1) as conn:
            if conn.execute(
                text(
                    "SELECT count(*) FROM app.fake_endpoints WHERE workspace_id=app.current_workspace_id()"
                )
            ).scalar_one():
                continue
            insert(
                conn,
                "fake_endpoints",
                {
                    "id": key("fake-endpoint-" + letter),
                    "adapter": "fake_local_v1",
                    "name": "Synthetic endpoint " + letter.upper(),
                    "enabled": True,
                },
            )
            now = datetime.now(UTC)
            insert(
                conn,
                "budgets",
                {
                    "period_start": now - timedelta(days=1),
                    "period_end": now + timedelta(days=365),
                    "category": "synthetic",
                    "limit_usd": "10",
                    "status": "active",
                },
            )
            insert(
                conn,
                "quota_buckets",
                {
                    "connection_id": key("fake-endpoint-" + letter),
                    "dimension": "requests",
                    "window_start": now,
                    "window_end": now + timedelta(days=1),
                    "limit_units": 100,
                    "safety_reserve": 10,
                },
            )
            request = {"scenario": "success", "logical_key": "runtime_health_demo"}
            item = insert(conn, "runtime_inputs", {**request, "content_hash": digest(request)})
            insert(
                conn,
                "schedules",
                {
                    "name": "runtime_health_demo",
                    "timezone": "Asia/Karachi",
                    "rule": "daily:08:00",
                    "next_due_at": next_daily(now, "Asia/Karachi", "daily:08:00"),
                    "enabled": True,
                    "missed_policy": "one_catchup",
                    "input_ref": item["id"],
                },
            )
    for letter in ("a", "b"):
        with transaction(engine, key("user-" + letter), key("workspace-" + letter), 1) as conn:
            for period in ("day", "month"):
                period_start = conn.execute(
                    text("SELECT date_trunc(:period,now())"), {"period": period}
                ).scalar_one()
                period_end = conn.execute(
                    text("SELECT date_trunc(:period,now())+CAST(:span AS interval)"),
                    {"period": period, "span": "1 " + period},
                ).scalar_one()
                if not conn.execute(
                    text(
                        "SELECT id FROM app.budgets WHERE workspace_id=app.current_workspace_id() AND category=:category AND period_start=:start"
                    ),
                    {"category": "synthetic_" + period, "start": period_start},
                ).first():
                    insert(
                        conn,
                        "budgets",
                        {
                            "period_start": period_start,
                            "period_end": period_end,
                            "category": "synthetic_" + period,
                            "limit_usd": "10",
                            "status": "active",
                        },
                    )
