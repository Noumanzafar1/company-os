"""Fixed no-network SDK probe. This is not a live-provider execution switch."""

import json
import os

import httpx2 as httpx

from company_os.ai.contracts import ProviderCall, ProviderResponse
from company_os.ai.credentials import OfflineCredential
from company_os.ai.providers import FakeOpenAIProvider
from company_os.ai.sdk_providers import AnthropicProvider, OpenAIProvider


def probe(call: ProviderCall, credential: OfflineCredential) -> ProviderResponse:
    # Assert the actual child environment, not merely the launcher's dictionary.
    # POSIX Python may add LC_CTYPE while coercing its startup locale.
    allowed = {"SYSTEMROOT", "WINDIR"}
    if os.name != "nt" and os.environ.get("LC_CTYPE") in {"C.UTF-8", "UTF-8"}:
        allowed.add("LC_CTYPE")
    if {name.upper() for name in os.environ} - allowed:
        raise ValueError("UNEXPECTED_CHILD_ENVIRONMENT")
    if call.route.primary_provider != credential.provider:
        return ProviderResponse(status="failed", error="permission")
    output = FakeOpenAIProvider().generate_typed(call).output
    if call.scenario == "secret":
        output = json.dumps({"secret": credential.value})

    def respond(request: httpx.Request) -> httpx.Response:
        if credential.value in request.content.decode():
            raise ValueError("SECRET_IN_REQUEST_BODY")
        if credential.provider == "openai":
            if request.headers.get("authorization") != "Bearer " + credential.value:
                raise ValueError("AUTH_BINDING")
            data = {
                "id": "resp_fixture",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": OpenAIProvider.model,
                "output": [
                    {
                        "type": "message",
                        "id": "msg_fixture",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": output, "annotations": []}],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            }
        else:
            if request.headers.get("x-api-key") != credential.value:
                raise ValueError("AUTH_BINDING")
            data = {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "model": AnthropicProvider.model,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "content": [{"type": "text", "text": output}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        return httpx.Response(
            200, json=data, headers={"x-request-id": "req_fixture", "request-id": "req_fixture"}
        )

    adapter = OpenAIProvider if credential.provider == "openai" else AnthropicProvider
    return adapter(credential.value, httpx.MockTransport(respond)).generate_typed(call)
