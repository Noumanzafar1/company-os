import pytest
from company_os.adapters.local_documents import FakeDocumentStore
from company_os.adapters.local_source import FakeSourceProvider
from company_os.business_contracts import FactValue, ICPVersionInput, Record

from scripts.boundaries import import_findings, phase_findings


@pytest.mark.parametrize(
    "dependency",
    [
        "openai",
        "anthropic",
        "apollo",
        "zerobounce",
        "smartlead",
        "pipedrive",
        "n8n",
        "redis",
        "celery",
        "temporalio",
        "smtplib",
    ],
)
def test_later_phase_dependencies_rejected(dependency):
    assert import_findings("packages/company_os/adapters/example.py", f"import {dependency}")


def test_phase_modules_routes_and_network_rejected():
    assert phase_findings("packages/company_os/workflow/jobs.py", "pass")
    assert phase_findings("apps/api/later.py", 'route="/campaigns/release"')
    assert phase_findings("packages/company_os/adapters/provider.py", "import httpx")
    assert not phase_findings(
        "packages/company_os/adapters/local_documents.py", "from pathlib import Path"
    )


def test_fake_document_store_rejects_path_input_and_verifies_hash(tmp_path):
    store = FakeDocumentStore(tmp_path)
    key = store.save_snapshot(b"Synthetic immutable snapshot")
    assert store.read_snapshot(key) == b"Synthetic immutable snapshot"
    assert store.save_snapshot(b"Synthetic immutable snapshot") == key
    for value in ["../secrets", "C:/private/file", "https://provider.example/file"]:
        with pytest.raises(ValueError):
            store.read_snapshot(value)
        with pytest.raises(ValueError):
            store.read_fixture(value)
    (tmp_path / key).write_bytes(b"modified")
    with pytest.raises(ValueError):
        store.read_snapshot(key)


def test_fact_values_are_closed_and_unknown_is_explicit():
    assert FactValue(type="unknown", value=None).value is None
    for payload in [
        {"type": "boolean", "value": "true"},
        {"type": "integer", "value": True},
        {"type": "unknown", "value": 0},
        {"type": "decimal", "value": "NaN"},
        {"type": "string", "value": "x", "sql": "SELECT 1"},
    ]:
        with pytest.raises(ValueError):
            FactValue.model_validate(payload)
    with pytest.raises(ValueError):
        FakeSourceProvider.facts("real-company-industry")
    with pytest.raises(ValueError):
        ICPVersionInput.model_validate({"criteria": {"sql": "SELECT * FROM app.people"}})


def test_business_timestamps_normalize_to_utc():
    record = Record.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "schema_version": 1,
            "record_version": 1,
            "created_at": "2026-09-17T09:00:00-04:00",
        }
    )
    assert record.model_dump(mode="json")["created_at"] == "2026-09-17T13:00:00Z"
    with pytest.raises(ValueError):
        Record.model_validate({**record.model_dump(), "created_at": "2026-09-17T13:00:00"})
