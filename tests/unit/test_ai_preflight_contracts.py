"""B1: synthetic credentials and mock transports only."""

import secrets
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.metadata import version

import pytest
from company_os.ai.credentials import (
    SelectedCredential,
    credential_binding,
    credential_reference,
    resolve_selected,
    verify_credential_binding,
)
from company_os.ai.preflight import CapabilityReport, live_precheck
from company_os.workflow.isolation import execute

from tests.unit.test_ai_contracts import envelope


def live_call(provider="openai"):
    call = envelope(provider=provider)
    return call.model_copy(
        update={
            "task": call.task.model_copy(
                update={"execution_mode": "live_preflight", "max_model_calls": 1}
            ),
            "route": call.route.model_copy(
                update={"selection": "preflight", "region_policy": "preflight_required"}
            ),
        }
    )


def report_for(call, secret=None):
    selected = SelectedCredential(
        call.route.primary_provider,
        secret or "synthetic-selected-" + call.route.primary_provider + "-canary",
    )
    return CapabilityReport(
        provider=call.route.primary_provider,
        environment="test",
        model_id=call.route.primary_model_id,
        checked_at=datetime.now(UTC) - timedelta(seconds=1),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        account_verified=True,
        structured_output=True,
        billing_verified=True,
        retention_approved=True,
        region_approved=True,
        rates_verified=True,
        requests_per_minute=1,
        input_token_limit=8000,
        output_token_limit=1500,
        sdk_version=version(call.route.primary_provider),
        external_account_id="synthetic-account",
        credential_ref=credential_reference(call.task.workspace_id, call.route.primary_provider),
        credential_binding=credential_binding(call.task.workspace_id, selected),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_verified", False),
        ("structured_output", False),
        ("billing_verified", False),
        ("retention_approved", False),
        ("region_approved", False),
        ("rates_verified", False),
        ("model_id", "wrong"),
        ("credential_ref", None),
        ("credential_ref", "arbitrary"),
        ("credential_binding", None),
        ("credential_binding", "invalid"),
        ("external_account_id", None),
        ("sdk_version", "wrong"),
        ("requests_per_minute", 0),
        ("input_token_limit", 1),
        ("output_token_limit", 1),
        ("checked_at", datetime.now(UTC) + timedelta(days=1)),
        ("expires_at", datetime.now(UTC) - timedelta(days=1)),
    ],
)
def test_required_capabilities_fail_closed(field, value):
    call = live_call()
    assert live_precheck(call, report_for(call), Decimal(5)) is None
    assert live_precheck(call, report_for(call).model_copy(update={field: value}), Decimal(5))


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_selected_canary_in_contained_preflight(provider, monkeypatch, tmp_path, capsys, caplog):
    call = live_call(provider)
    secret = "synthetic-" + secrets.token_hex(32)
    other = "synthetic-" + secrets.token_hex(32)
    report = report_for(call, secret)
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "UNRELATED_SECRET",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_PROFILE",
        "ANTHROPIC_CUSTOM_HEADERS",
    ):
        monkeypatch.setenv(name, other)
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "config.json").write_text(other)
    for name in ("HOME", "USERPROFILE", "APPDATA", "XDG_CONFIG_HOME", "ANTHROPIC_CONFIG_DIR"):
        monkeypatch.setenv(name, str(profile))
    monkeypatch.setenv(
        {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[provider], secret
    )
    selected = resolve_selected(call.task.workspace_id, provider, report.credential_ref)
    assert secret not in repr(selected) + str(selected) + call.model_dump_json()
    result = execute(
        call,
        lambda: None,
        selected_credential=selected,
        capability_report=report,
        live_limit=Decimal(5),
        contract_only=True,
    )
    assert result.code == "RESULT", result
    assert result.result.response.status == "completed"
    visible = result.result.model_dump_json() + caplog.text + str(capsys.readouterr())
    assert secret not in visible and other not in visible


def test_resolver_is_closed_and_provider_bound(monkeypatch):
    call = live_call()
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-selected-key")
    for ref in (
        "HOME",
        "OPENAI_API_KEY",
        "/tmp/key",
        credential_reference(call.task.workspace_id, "anthropic"),
    ):
        with pytest.raises(ValueError, match="CREDENTIAL_REFERENCE_DENIED"):
            resolve_selected(call.task.workspace_id, "openai", ref)
    with pytest.raises(ValueError):
        execute(
            call,
            lambda: None,
            selected_credential=SelectedCredential("anthropic", "synthetic-key"),
            capability_report=report_for(call, "synthetic-key-canary"),
            live_limit=Decimal(5),
        )


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("change", ["value", "provider", "workspace", "missing_binding"])
def test_credential_substitution_denied_before_child(provider, change, monkeypatch):
    import subprocess
    from uuid import uuid4

    call = live_call(provider)
    secret = "synthetic-" + secrets.token_hex(32)
    selected = SelectedCredential(provider, secret)
    report = report_for(call, secret)
    verify_credential_binding(
        call.task.workspace_id, provider, report.credential_ref, report.credential_binding, selected
    )
    if change == "value":
        selected = SelectedCredential(provider, "synthetic-" + secrets.token_hex(32))
    elif change == "provider":
        other = SelectedCredential("anthropic" if provider == "openai" else "openai", secret)
        report = report.model_copy(
            update={"credential_binding": credential_binding(call.task.workspace_id, other)}
        )
    elif change == "workspace":
        report = report.model_copy(
            update={"credential_ref": credential_reference(uuid4(), provider)}
        )
    else:
        report = report.model_copy(update={"credential_binding": None})
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pytest.fail("Child launched"))
    with pytest.raises(ValueError, match="BINDING"):
        execute(
            call,
            lambda: None,
            selected_credential=selected,
            capability_report=report,
            live_limit=Decimal(5),
            contract_only=True,
        )


def test_binding_is_versioned_and_workspace_provider_scoped():
    from uuid import uuid4

    workspace = uuid4()
    secret = "synthetic-" + secrets.token_hex(32)
    selected = SelectedCredential("openai", secret)
    binding = credential_binding(workspace, selected)
    assert binding.startswith("sha256-v1:") and len(binding) == 74
    assert secret not in binding and secret not in repr(selected)
    assert binding == credential_binding(workspace, selected)
    assert binding != credential_binding(uuid4(), selected)
    assert binding != credential_binding(workspace, SelectedCredential("anthropic", secret))


@pytest.mark.parametrize(
    "change", ["ordinary", "two_calls", "fallback", "ordinary_route", "second_call", "zero_budget"]
)
def test_closed_preflight_dispatch(change):
    call = live_call()
    if change == "ordinary":
        call = call.model_copy(
            update={"task": call.task.model_copy(update={"execution_mode": "ordinary"})}
        )
    if change == "two_calls":
        call = call.model_copy(update={"task": call.task.model_copy(update={"max_model_calls": 2})})
    if change == "fallback":
        call = call.model_copy(
            update={"route": call.route.model_copy(update={"fallback_provider": "anthropic"})}
        )
    if change == "ordinary_route":
        call = call.model_copy(
            update={"route": call.route.model_copy(update={"selection": "ordinary"})}
        )
    if change == "second_call":
        call = call.model_copy(update={"ordinal": 2})
    assert live_precheck(call, report_for(call), Decimal(0 if change == "zero_budget" else 5))


@pytest.mark.parametrize("host", ["api.openai.com", "api.anthropic.com", "203.0.113.10"])
def test_live_network_is_forbidden(host):
    with pytest.raises(AssertionError, match="EXTERNAL_TEST_NETWORK_FORBIDDEN"):
        socket.create_connection((host, 443), timeout=0.1)


def test_synthetic_credential_cannot_select_live_child_transport(monkeypatch):
    import subprocess

    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("Child launched with synthetic live key")
    )
    call = live_call()
    with pytest.raises(ValueError, match="SYNTHETIC_CREDENTIAL_NETWORK_DENIED"):
        execute(
            call,
            lambda: None,
            selected_credential=SelectedCredential("openai", "synthetic-key-canary"),
            capability_report=report_for(call, "synthetic-key-canary"),
            live_limit=Decimal(5),
        )
