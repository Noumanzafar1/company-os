"""Offline contract, cost, capability and hard-output controls."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx2 as httpx
import pytest
from company_os.ai.contracts import (
    AIRequest,
    AIRoute,
    AITask,
    ContextPack,
    Evidence,
    ProviderCall,
    ResourceRef,
    Usage,
)
from company_os.ai.providers import FakeAnthropicProvider, FakeOpenAIProvider
from company_os.ai.sdk_providers import AnthropicProvider, FixedTransport, OpenAIProvider
from company_os.ai.validation import PROMPT, cost, schema, validate_output
from company_os.workflow.isolation import child_environment, execute


def envelope(scenario="success", provider="fake_openai"):
    now = datetime.now(UTC)
    evidence = Evidence(
        ref=ResourceRef(type="synthetic_evidence", id=uuid4(), version=1, observed_at=now)
    )
    context = ContextPack(
        id=uuid4(),
        workspace_id=uuid4(),
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        authz_epoch=1,
        document_permission_epochs={},
        policy_version=uuid4(),
        selected_records=(),
        evidence=(evidence,),
        document_excerpts=("UNTRUSTED: fixture_colour blue",),
        token_estimate=2000,
        content_hash="fixture",
    )
    route = AIRoute(
        route_id=uuid4(),
        version=1,
        primary_provider=provider,
        primary_model_id=OpenAIProvider.model
        if provider == "openai"
        else AnthropicProvider.model
        if provider == "anthropic"
        else "fake-openai-v1",
        prompt_version=uuid4(),
        schema_version=uuid4(),
        price_config_version=uuid4(),
    )
    task = AITask(
        id=uuid4(),
        workspace_id=context.workspace_id,
        subject_refs=(),
        allowed_providers=(provider,),
        context_pack_id=context.id,
        evidence_refs=(evidence.ref,),
        policy_version_id=context.policy_version,
        evaluation_policy_id=uuid4(),
        deadline_at=now + timedelta(minutes=5),
    )
    return ProviderCall(
        execution_id=uuid4(),
        input_hash="fixture",
        task=task,
        context=context,
        route=route,
        scenario=scenario,
        ordinal=1,
        prompt=PROMPT,
        output_schema=schema(),
        hard_timeout_seconds=10,
    )


@pytest.mark.parametrize("adapter", [FakeOpenAIProvider, FakeAnthropicProvider])
@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "injection",
        "forged_evidence",
        "unsupported_claim",
        "secret",
        "tool_url",
        "tool_shell",
        "cross_workspace",
        "authority",
        "oversized",
        "malformed",
        "invalid_schema",
    ],
)
def test_hard_validation(adapter, scenario):
    call = envelope(scenario)
    response = adapter().generate_typed(call)
    result, validation, repair = validate_output(response.output, call.context)
    assert bool(result) == (scenario in {"success", "injection"})
    if scenario in {"forged_evidence", "unsupported_claim"}:
        assert validation.schema_valid and not validation.evidence and not repair
    if scenario in {
        "secret",
        "tool_url",
        "tool_shell",
        "cross_workspace",
        "authority",
        "oversized",
    }:
        assert not repair


def test_request_cannot_supply_authority():
    for key in [
        "provider",
        "model_id",
        "api_key",
        "workspace_id",
        "route_id",
        "tools",
        "url",
        "system_prompt",
    ]:
        with pytest.raises(ValueError):
            AIRequest.model_validate({key: "untrusted"})


def test_nonempty_actions_and_extra_capabilities_never_repair():
    call = envelope()
    output = json.loads(FakeOpenAIProvider().generate_typed(call).output)
    for changed in [{**output, "proposed_actions": [{"send": True}]}, {**output, "admin": True}]:
        proposal, validation, repairable = validate_output(json.dumps(changed), call.context)
        assert proposal is None and not validation.policy and not repairable


def test_usage_cache_and_unknown_safety():
    price = {"input": "1", "output": "2", "cached": "0.1", "cache_creation": "1.25"}
    assert cost(
        Usage(input_tokens=100, output_tokens=50, cached_tokens=20, cache_creation_tokens=10), price
    ) == Decimal("0.00019450")
    with pytest.raises(ValueError, match="INVALID_USAGE"):
        cost(Usage(input_tokens=1, output_tokens=1, cached_tokens=2), price)


@pytest.mark.parametrize(
    "adapter,provider", [(OpenAIProvider, "openai"), (AnthropicProvider, "anthropic")]
)
def test_official_sdk_request_and_success(adapter, provider):
    call = envelope(provider=provider)
    proposal = FakeOpenAIProvider().generate_typed(call).output
    requests = []
    credential = "synthetic-provider-canary"

    def respond(request):
        requests.append(request)
        body = json.loads(request.content)
        assert credential not in request.content.decode()
        assert body["model"] == adapter.model
        if provider == "openai":
            assert body["store"] is False and body["tools"] == []
            assert body["text"]["format"]["strict"] is True
            data = {
                "id": "resp_fixture",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": adapter.model,
                "output": [
                    {
                        "type": "message",
                        "id": "msg_fixture",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": proposal, "annotations": []}],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            }
        else:
            assert "tools" not in body and body["output_config"]["format"]["type"] == "json_schema"
            data = {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "model": adapter.model,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "content": [{"type": "text", "text": proposal}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        return httpx.Response(
            200, json=data, headers={"x-request-id": "req_fixture", "request-id": "req_fixture"}
        )

    result = adapter(credential, httpx.MockTransport(respond)).generate_typed(call)
    assert result.status == "completed", result
    assert result.usage.input_tokens == 100
    assert len(requests) == 1 and credential not in result.model_dump_json()
    assert validate_output(result.output, call.context)[0]


@pytest.mark.parametrize(
    "adapter,provider", [(OpenAIProvider, "openai"), (AnthropicProvider, "anthropic")]
)
@pytest.mark.parametrize(
    "status,category",
    [
        (400, "invalid_request"),
        (401, "auth"),
        (403, "permission"),
        (404, "unsupported_capability"),
        (429, "rate_limit"),
        (529, "provider_overloaded"),
    ],
)
def test_sdk_errors_never_retry_or_leak(adapter, provider, status, category):
    calls = []

    def respond(request):
        calls.append(1)
        return httpx.Response(
            status,
            json={"error": {"type": "error", "message": "synthetic-secret-canary"}},
            headers={"retry-after": "7"},
        )

    response = adapter("synthetic-secret-canary", httpx.MockTransport(respond)).generate_typed(
        envelope(provider=provider)
    )
    assert response.error == category and response.retry_after == 7
    assert len(calls) == 1 and "canary" not in response.model_dump_json()


def test_fixed_transport_ssrf_and_child_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "database-canary")
    monkeypatch.setenv("SESSION_TOKEN", "session-canary")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-canary")
    assert set(child_environment()) <= {"SystemRoot", "WINDIR"}
    transport = FixedTransport(
        "api.openai.com",
        "/v1/responses",
        httpx.MockTransport(lambda _: pytest.fail("network reached")),
    )
    for url in [
        "http://169.254.169.254/",
        "https://api.openai.com/v1/files",
        "https://api.openai.com/v1/responses?leak=1",
    ]:
        with pytest.raises(ValueError, match="DESTINATION_DENIED"):
            transport.handle_request(httpx.Request("POST", url))


def test_real_contained_provider_process_and_deadline():
    call = envelope()
    result = execute(call, lambda: None)
    assert result.code == "RESULT" and result.result.response.status == "completed"
    timed = execute(
        envelope("timeout").model_copy(update={"hard_timeout_seconds": 0.5}), lambda: None
    )
    assert timed.code == "HARD_TIMEOUT" and timed.result is None and timed.elapsed_ms < 4000


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("scenario", ["success", "secret"])
def test_selected_secret_after_containment(
    provider, scenario, monkeypatch, tmp_path, caplog, capsys
):
    from company_os.ai.credentials import OfflineCredential

    monkeypatch.setenv("DATABASE_URL", "synthetic-database-password-canary")
    monkeypatch.setenv("SESSION_TOKEN", "synthetic-session-canary")
    monkeypatch.setenv("UNRELATED_SECRET", "synthetic-unrelated-canary")
    profile = tmp_path / "anthropic"
    (profile / "configs").mkdir(parents=True)
    (profile / "credentials").mkdir()
    (profile / "active_config").write_text("canary", encoding="utf-8")
    for folder in ("configs", "credentials"):
        (profile / folder / "canary.json").write_text(
            '{"api_key":"synthetic-profile-key-canary"}', encoding="utf-8"
        )
    for name in ("HOME", "USERPROFILE", "APPDATA", "XDG_CONFIG_HOME", "ANTHROPIC_CONFIG_DIR"):
        monkeypatch.setenv(name, str(profile))
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_PROFILE",
        "ARBITRARY_CONFIG",
        "ARBITRARY_PROFILE",
        "ANTHROPIC_CUSTOM_HEADERS",
    ):
        monkeypatch.setenv(name, "synthetic-parent-profile-canary")
    assert set(child_environment()) <= {"SystemRoot", "WINDIR"}
    call = envelope(scenario, provider)
    key = "synthetic-selected-provider-key-canary"
    credential = OfflineCredential(provider, key)
    observations = []
    result = execute(
        call,
        lambda: None,
        lambda event, pid: observations.append(event),
        offline_credential=credential,
    )
    assert observations[0] == "child_started"
    assert result.code == "RESULT" and result.result.response.status == "completed"
    assert key not in repr(credential) + call.model_dump_json() + result.result.model_dump_json()
    captured = capsys.readouterr()
    visible = result.result.model_dump_json() + caplog.text + captured.out + captured.err
    for value in (
        key,
        "database-password-canary",
        "synthetic-parent-profile-canary",
        "synthetic-profile-key-canary",
    ):
        assert value not in visible
    if scenario == "secret":
        assert not validate_output(result.result.response.output, call.context)[0]
    wrong = "anthropic" if provider == "openai" else "openai"
    with pytest.raises(ValueError, match="CREDENTIAL_PROVIDER_MISMATCH"):
        execute(call, lambda: None, offline_credential=OfflineCredential(wrong, key))
    with pytest.raises(ValueError, match="LIVE_AUTHORIZATION_REQUIRED"):
        execute(call, lambda: None)


def test_secret_metadata_and_provider_precheck_fail_closed():
    from company_os.ai.preflight import precheck

    credential = "synthetic-key-canary"
    for adapter in (OpenAIProvider, AnthropicProvider):
        instance = adapter(credential)
        assert instance.safe_metadata(credential) is None
        assert instance.safe_metadata("prefix-" + credential) is None
        assert instance.safe_metadata("response_valid") == "response_valid"
    assert precheck(envelope(provider="openai"), None) == "LIVE_AUTHORIZATION_REQUIRED"
    assert (
        precheck(envelope(provider="openai"), None, Decimal("1")) == "PROVIDER_PREFLIGHT_REQUIRED"
    )


@pytest.mark.parametrize(
    "adapter,provider", [(OpenAIProvider, "openai"), (AnthropicProvider, "anthropic")]
)
def test_exhausted_billing_quota_is_not_transient_rate_limit(adapter, provider):
    requests = []

    def respond(request):
        requests.append(1)
        return httpx.Response(
            429,
            json={
                "error": {
                    "type": "insufficient_quota",
                    "code": "insufficient_quota",
                    "message": "synthetic-secret-canary",
                }
            },
        )

    result = adapter("synthetic-secret-canary", httpx.MockTransport(respond)).generate_typed(
        envelope(provider=provider)
    )
    assert result.error == "quota" and len(requests) == 1
    assert "canary" not in result.model_dump_json()


def test_pinned_anthropic_explicit_client_skips_both_discovery_paths(monkeypatch):
    import anthropic
    import anthropic._client as sdk
    from company_os.ai.sdk_providers import ExplicitAnthropic

    assert anthropic.__version__ == "1.7.0"
    attempted = []

    def forbidden(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("ambient discovery attempted")

    monkeypatch.setattr(sdk, "default_credentials", forbidden)
    monkeypatch.setattr(sdk, "_warn_env_shadow", forbidden)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("network")), trust_env=False
    ) as transport:
        with ExplicitAnthropic(
            api_key="synthetic-explicit-canary", http_client=transport, timeout=httpx.Timeout(1)
        ) as client:
            assert not sdk._is_base_client(client)
            assert client.api_key == "synthetic-explicit-canary" and client.credentials is None
        assert not attempted
        # Positive control: the pinned base client DOES enter the warning/profile
        # probe even with an explicit key. This is why the subclass is required.
        with pytest.raises(AssertionError, match="ambient discovery"):
            anthropic.Anthropic(api_key="synthetic-explicit-canary", http_client=transport)
        assert attempted == [True]
