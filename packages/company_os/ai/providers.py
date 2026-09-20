"""AIProvider port and deterministic offline providers. No network or secrets."""

import json
import time
from typing import Protocol
from uuid import UUID

from company_os.ai.contracts import ProviderCall, ProviderResponse, Usage


class AIProvider(Protocol):
    def generate_typed(self, call: ProviderCall) -> ProviderResponse: ...
    def normalize_usage(self, response: dict) -> Usage: ...
    def normalize_error(self, response: Exception) -> ProviderResponse: ...
    def capabilities(self, model_id: str) -> dict[str, bool]: ...


class FakeOpenAIProvider:
    provider = "fake_openai"
    model = "fake-openai-v1"

    def capabilities(self, model_id: str) -> dict[str, bool]:
        return {"structured_output": model_id == self.model, "tools": False}

    def normalize_usage(self, response: dict) -> Usage:
        return Usage.model_validate(response)

    def normalize_error(self, response: Exception) -> ProviderResponse:
        return ProviderResponse(status="uncertain", error="uncertain")

    def generate_typed(self, call: ProviderCall) -> ProviderResponse:
        scenario = call.scenario
        usage = Usage(input_tokens=100, output_tokens=70)
        request_id = "fake_" + call.execution_id.hex
        if scenario in {"timeout", "delayed"}:
            time.sleep(120 if scenario == "timeout" else 1)
        if scenario == "refusal":
            return ProviderResponse(
                status="refused", error="refused", usage=usage, request_id=request_id
            )
        if scenario == "incomplete":
            return ProviderResponse(
                status="incomplete", error="incomplete", usage=usage, request_id=request_id
            )
        errors = {
            "connection_failure": "timeout_connect",
            "rate_limit": "rate_limit",
            "overloaded": "provider_overloaded",
            "uncertain": "uncertain",
            "unsupported_schema": "unsupported_capability",
            "unsupported_model": "unsupported_capability",
            "fallback_denied": "provider_overloaded",
        }
        if scenario in errors:
            return ProviderResponse.model_validate(
                {
                    "status": "uncertain"
                    if scenario in {"uncertain", "connection_failure"}
                    else "failed",
                    "error": errors[scenario],
                    "request_id": request_id,
                    "retry_after": 5 if scenario == "rate_limit" else 0,
                    "usage": None,
                }
            )
        output = {
            "claims": [
                {
                    "evidence_id": str(call.context.evidence[0].ref.id),
                    "key": "fixture_colour",
                    "value": "blue",
                }
            ],
            "unknowns": ["business facts unavailable"],
            "uncertainties": ["synthetic fixture only"],
            "proposed_actions": [],
        }
        raw = json.dumps(output)
        if scenario in {"malformed", "max_calls"} or (scenario == "repair" and call.ordinal == 1):
            raw = "{"
        elif scenario == "invalid_schema":
            raw = '{"claims":5}'
        elif scenario == "forged_evidence":
            output["claims"][0]["evidence_id"] = str(UUID(int=1))  # type: ignore[index]
            raw = json.dumps(output)
        elif scenario == "unsupported_claim":
            raw = raw.replace('"blue"', '"red"')
        elif scenario in {"secret", "tool_url", "tool_shell", "cross_workspace", "authority"}:
            raw = json.dumps({"secret": "SYNTHETIC_CANARY", "tool": scenario})
        elif scenario == "oversized":
            raw = "x" * 13000
        if scenario == "incorrect_usage":
            usage = Usage(input_tokens=1, output_tokens=1000000)
        return ProviderResponse(
            status="completed",
            output=raw,
            usage=usage,
            request_id=request_id,
            reported_model=self.model,
        )


class FakeAnthropicProvider(FakeOpenAIProvider):
    provider = "fake_anthropic"
    model = "fake-anthropic-v1"
