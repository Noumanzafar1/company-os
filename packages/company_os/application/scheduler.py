"""Closed daily calendar scheduling; database UTC clock, IANA local slots."""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Connection, text

from company_os.application.runtime import audit, enqueue
from company_os.persistence.database import rows
from company_os.persistence.runtime import clock, get, insert, update


def next_daily(after: datetime, zone: str, rule: str) -> datetime:
    if not re.fullmatch(r"daily:([01][0-9]|2[0-3]):[0-5][0-9]", rule):
        raise ValueError("Invalid daily schedule")
    tz = ZoneInfo(zone)
    _, h, m = rule.split(":")
    local = after.astimezone(tz)
    for days in range(3):
        candidate = (local + timedelta(days=days)).replace(
            hour=int(h), minute=int(m), second=0, microsecond=0, fold=0
        )
        utc = candidate.astimezone(UTC)
        # Missing DST wall times are skipped; repeated times use the first fold.
        if utc.astimezone(tz).replace(tzinfo=None) != candidate.replace(tzinfo=None):
            continue
        if utc > after:
            return utc
    raise ValueError("Invalid daily schedule")


def tick(conn: Connection) -> int:
    if not conn.execute(
        text(
            "SELECT pg_try_advisory_xact_lock(hashtextextended(app.current_workspace_id()::text,15))"
        )
    ).scalar_one():
        return 0
    now = clock(conn)
    count = 0
    for schedule in rows(
        conn,
        "SELECT * FROM app.schedules WHERE enabled AND next_due_at<=now() ORDER BY next_due_at LIMIT 50 FOR UPDATE SKIP LOCKED",
    ):
        try:
            next_due = next_daily(now, schedule["timezone"], schedule["rule"])
            tz = ZoneInfo(schedule["timezone"])
        except (ValueError, ZoneInfoNotFoundError):
            update(conn, "schedules", schedule, enabled=False, last_error_code="INVALID_SCHEDULE")
            audit(
                conn,
                "schedule.quarantined",
                schedule["id"],
                schedule["id"],
                outcome="INVALID_SCHEDULE",
            )
            continue
        slot = (
            schedule["next_due_at"].astimezone(tz).strftime("%Y-%m-%dT%H:%M")
            + "@"
            + schedule["timezone"]
        )
        late = (now - schedule["next_due_at"]).total_seconds() > 60
        if not late or schedule["missed_policy"] == "one_catchup":
            if not rows(
                conn,
                "SELECT id FROM app.schedule_slots WHERE schedule_id=:id AND slot=:slot",
                {"id": schedule["id"], "slot": slot},
            ):
                item = get(conn, "runtime_inputs", schedule["input_ref"])
                job = enqueue(conn, item, f"schedule:{schedule['id']}:{slot}", schedule["id"])
                insert(
                    conn,
                    "schedule_slots",
                    {
                        "schedule_id": schedule["id"],
                        "slot": slot,
                        "job_id": job["id"],
                        "late": late,
                    },
                )
                count += 1
        update(
            conn,
            "schedules",
            schedule,
            last_emitted_slot=slot,
            next_due_at=next_due,
        )
    return count
