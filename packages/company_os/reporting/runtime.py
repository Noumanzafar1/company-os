"""Deterministic runtime health. Missing observations are UNKNOWN, never healthy."""

from typing import Any

from sqlalchemy import Connection

from company_os.persistence.database import rows
from company_os.persistence.runtime import clock


def health(conn: Connection) -> dict[str, Any]:
    now = clock(conn)
    counts = rows(
        conn,
        "SELECT state,priority,count(*) AS count,min(created_at) AS oldest FROM app.jobs GROUP BY state,priority",
    )
    beats = rows(
        conn,
        "SELECT component,max(measured_at) AS last_seen FROM app.runtime_heartbeats GROUP BY component",
    )
    components = []
    pools = rows(
        conn,
        "SELECT instance FROM app.runtime_heartbeats WHERE component='long_pool' AND measured_at>clock_timestamp()-interval '60 seconds'",
    )
    pool_capacity = sum(
        int(p["instance"].rsplit(":", 1)[-1])
        for p in pools
        if p["instance"].rsplit(":", 1)[-1] in {"1", "2", "3", "4"}
    )
    components.append(
        {
            "name": "long_pool_capacity",
            "status": "GREEN" if pools else "UNKNOWN",
            "count": pool_capacity if pools else None,
        }
    )
    components.append(
        {
            "name": "long_safety_reserved_slots",
            "status": "GREEN" if pools else "UNKNOWN",
            "count": len(pools) if pools else None,
        }
    )
    executions = rows(
        conn,
        """SELECT count(*) FILTER(WHERE x.state='active' AND j.fence=x.fence AND j.lease_expires_at>clock_timestamp()) AS active,
        min(x.created_at) FILTER(WHERE x.state='active') AS oldest,
        count(*) FILTER(WHERE x.outcome='HARD_TIMEOUT') AS timed_out,
        count(*) FILTER(WHERE x.details->>'forced'='true') AS escalated,
        (SELECT count(*) FROM app.audit_entries WHERE action_type='job.long_stale_completion') AS stale,
        count(*) FILTER(WHERE x.state='abandoned' OR (x.state='active' AND (j.fence<>x.fence OR j.lease_expires_at IS NULL OR j.lease_expires_at<=clock_timestamp()))) AS orphaned
        FROM app.long_executions x JOIN app.jobs j ON j.workspace_id=x.workspace_id AND j.id=x.job_id""",
    )[0]
    for name, count in (
        ("long_active", executions["active"]),
        ("long_timeouts", executions["timed_out"]),
        ("long_cancellation_escalations", executions["escalated"]),
        ("long_stale_completions", executions["stale"]),
        ("long_orphan_cleanup_unconfirmed", executions["orphaned"]),
    ):
        components.append(
            {
                "name": name,
                "status": "RED"
                if name == "long_orphan_cleanup_unconfirmed" and count
                else "AMBER"
                if count and name != "long_active"
                else "GREEN",
                "count": count,
                "age_seconds": (now - executions["oldest"]).total_seconds()
                if name == "long_active" and executions["oldest"]
                else None,
            }
        )
    for name in ("worker", "scheduler", "fake_adapter"):
        seen = next((x["last_seen"] for x in beats if x["component"] == name), None)
        age = (now - seen).total_seconds() if seen else None
        components.append(
            {
                "name": name,
                "status": "UNKNOWN"
                if age is None
                else "GREEN"
                if age <= 30
                else "AMBER"
                if age <= 60
                else "RED",
                "age_seconds": age,
            }
        )
    for name, safety, amber, red in [
        ("safety_queue", True, 5, 10),
        ("ordinary_queue", False, 60, 300),
    ]:
        active = [
            x
            for x in counts
            if x["state"] in {"queued", "retry_wait"} and (x["priority"] == "safety") == safety
        ]
        age = max(((now - x["oldest"]).total_seconds() for x in active), default=0)
        components.append(
            {
                "name": name,
                "status": "RED" if age > red else "AMBER" if age > amber else "GREEN",
                "age_seconds": age,
            }
        )
    effects = rows(
        conn,
        "SELECT id,state,dispatch_started_at,reconcile_after,job_id FROM app.external_effects WHERE state IN ('dispatching','uncertain') ORDER BY created_at LIMIT 200",
    )
    dead = rows(
        conn,
        "SELECT count(*) AS count FROM app.incidents WHERE kind='dead_letter' AND state<>'resolved'",
    )[0]["count"]
    components.append({"name": "dead_letters", "status": "RED" if dead else "GREEN", "count": dead})
    components.append(
        {
            "name": "uncertain_effects",
            "status": "RED" if effects else "GREEN",
            "count": len(effects),
        }
    )
    reconcile = rows(
        conn,
        "SELECT count(*) AS count,min(created_at) AS oldest FROM app.jobs WHERE job_type='reconcile_effect' AND state NOT IN ('succeeded','cancelled')",
    )[0]
    reconcile_age = (now - reconcile["oldest"]).total_seconds() if reconcile["oldest"] else 0
    components.append(
        {
            "name": "reconciliation_lag",
            "status": "RED" if reconcile_age > 300 else "AMBER" if reconcile["count"] else "GREEN",
            "count": reconcile["count"],
            "age_seconds": reconcile_age,
        }
    )
    budgets = rows(
        conn,
        "SELECT id,category,limit_usd,reserved_usd,spent_usd,status FROM app.budgets WHERE period_start<=now() AND period_end>now()",
    )
    for budget in budgets:
        total = budget["reserved_usd"] + budget["spent_usd"]
        status = (
            "RED"
            if total >= budget["limit_usd"] or budget["status"] == "frozen"
            else "AMBER"
            if total * 100 >= budget["limit_usd"] * 80
            else "GREEN"
        )
        components.append({"name": "budget:" + budget["category"], "status": status})
    inbox = rows(
        conn,
        "SELECT count(*) AS count,min(received_at) AS oldest FROM app.webhook_inbox WHERE state IN ('received','processing','quarantined')",
    )[0]
    lag = (now - inbox["oldest"]).total_seconds() if inbox["oldest"] else 0
    components.append(
        {
            "name": "webhook_inbox",
            "status": "RED" if lag > 300 else "AMBER" if inbox["count"] else "GREEN",
            "count": inbox["count"],
            "age_seconds": lag,
        }
    )
    authority = rows(
        conn,
        "SELECT (SELECT count(*) FROM app.authority_freezes) AS freezes,(SELECT count(*) FROM app.approval_requests WHERE state='pending' AND expires_at>clock_timestamp() AND expires_at<clock_timestamp()+interval '1 hour') AS expiring,(SELECT count(*) FROM app.approval_requests WHERE state='pending' AND expires_at<=clock_timestamp()) AS stale",
    )[0]
    components.append(
        {
            "name": "authority_freeze",
            "status": "RED" if authority["freezes"] else "GREEN",
            "count": authority["freezes"],
        }
    )
    components.append(
        {
            "name": "approvals_nearing_expiry",
            "status": "AMBER" if authority["expiring"] or authority["stale"] else "GREEN",
            "count": authority["expiring"] + authority["stale"],
        }
    )
    overall = (
        "RED"
        if any(x["status"] == "RED" for x in components)
        else "AMBER"
        if any(x["status"] == "AMBER" for x in components)
        else "UNKNOWN"
        if any(x["status"] == "UNKNOWN" for x in components)
        else "GREEN"
    )
    for budget in budgets:
        for field in ("limit_usd", "reserved_usd", "spent_usd"):
            budget[field] = format(budget[field], ".8f")
    return {
        "threshold_version": "phase-4-v1",
        "as_of": now,
        "status": overall,
        "components": components,
        "queues": counts,
        "uncertain_effects": effects,
        "budgets": budgets,
        "incidents": rows(
            conn,
            "SELECT id,record_version,severity,kind,state,opened_at,resolved_at,owner_id FROM app.incidents WHERE state<>'resolved' ORDER BY opened_at LIMIT 200",
        ),
        "integrations": "NOT CONFIGURED — fake local adapter only",
    }
