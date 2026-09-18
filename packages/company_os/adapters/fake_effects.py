"""Local-only fake external effect. No network client, URL or credential input."""

from datetime import timedelta
from typing import Any

from sqlalchemy import Connection

from company_os.application.runtime import digest
from company_os.persistence.database import rows
from company_os.persistence.runtime import clock, insert


def accept(conn: Connection, effect: dict[str, Any], scenario: str) -> dict[str, Any]:
    # Called in its own committed transaction, after durable dispatching intent.
    existing = rows(
        conn, "SELECT * FROM app.fake_receipts WHERE effect_id=:id", {"id": effect["id"]}
    )
    if existing:
        raise RuntimeError("Fake adapter invoked twice for one effect")
    outcome = "rejected" if scenario == "effect_rejected" else "confirmed"
    request_id = "fake-" + str(effect["id"])
    return insert(
        conn,
        "fake_receipts",
        {
            "effect_id": effect["id"],
            "outcome": outcome,
            "visible_after": clock(conn)
            + timedelta(
                seconds=30
                if scenario == "effect_lost"
                else 86400
                if scenario == "effect_unknown"
                else 0
            ),
            "provider_request_id": request_id,
            "receipt_hash": digest({"request": request_id, "outcome": outcome}),
        },
    )


def reconcile(conn: Connection, effect: dict[str, Any]) -> dict[str, Any] | None:
    found = rows(
        conn,
        "SELECT * FROM app.fake_receipts WHERE effect_id=:id AND visible_after<=now()",
        {"id": effect["id"]},
    )
    return found[0] if found else None


class FakeRateLimited(Exception):
    def __init__(self, retry_after: int = 30) -> None:
        self.retry_after = retry_after
        super().__init__("FAKE_RATE_LIMIT")


def read_page(
    cursor: str | None, *, rate_limited: bool = False
) -> tuple[list[str], str | None, int]:
    """Closed deterministic contract fixture, including an empty intermediate page."""
    if rate_limited:
        raise FakeRateLimited()
    pages = {
        None: (["synthetic-one"], "page-2", 1),
        "page-2": ([], "page-3", 1),
        "page-3": (["synthetic-two"], None, 1),
    }
    if cursor not in pages:
        raise ValueError("INVALID_FAKE_CURSOR")
    return pages[cursor]
