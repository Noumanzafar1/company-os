from datetime import UTC, datetime

import pytest
from company_os.adapters.fake_effects import FakeRateLimited, read_page
from company_os.runtime_contracts import FakeCallback


def test_fake_paging_empty_intermediate_and_limits():
    cursor = None
    records = []
    usage = 0
    for _ in range(3):
        page, cursor, units = read_page(cursor)
        records.extend(page)
        usage += units
    assert records == ["synthetic-one", "synthetic-two"] and cursor is None and usage == 3
    with pytest.raises(FakeRateLimited) as error:
        read_page(None, rate_limited=True)
    assert error.value.retry_after == 30
    with pytest.raises(ValueError, match="INVALID_FAKE_CURSOR"):
        read_page("expired-cursor")


def test_runtime_timestamps_are_aware_and_utc():
    body = {
        "event_key": "synthetic",
        "schema_version": 1,
        "external_id": "00000000-0000-0000-0000-000000000001",
        "version": 1,
        "observation": "stopped",
        "occurred_at": "2026-09-17T09:00:00-04:00",
    }
    assert FakeCallback.model_validate(body).occurred_at == datetime(2026, 9, 17, 13, tzinfo=UTC)
    with pytest.raises(ValueError):
        FakeCallback.model_validate({**body, "occurred_at": "2026-09-17T09:00:00"})
