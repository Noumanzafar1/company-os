"""Fixed provider transports; callable only by trusted bounded provider execution.

No environment key discovery, arbitrary base URL, tool loop or automatic retries.
Offline contract tests pass httpx.MockTransport explicitly. The application has
no live activation command in Gate A.
"""

import json
import re
from typing import Any

import anthropic
import httpx2 as httpx
import openai

from company_os.ai.contracts import Error, ProviderCall, ProviderResponse, Usage


class FixedTransport(httpx.BaseTransport):
    def __init__(self, host: str, path: str, inner: httpx.BaseTransport | None = None) -> None:
        self.host, self.path = host, path
        self.inner = inner if inner is not None else httpx.HTTPTransport(retries=0, trust_env=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if (request.url.scheme, request.url.host, request.url.path, request.method) != (
            "https",
            self.host,
            self.path,
            "POST",
        ) or request.url.query:
            raise ValueError("PROVIDER_DESTINATION_DENIED")
        response = self.inner.handle_request(request)
        # Bound decompressed provider body before the SDK deserializes it.
        data = bytearray()
        try:
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 65536:
                    raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
        finally:
            response.close()
        return httpx.Response(
            response.status_code, headers=response.headers, content=bytes(data), request=request
        )

    def close(self) -> None:
        self.inner.close()


def error_response(error: Exception) -> ProviderResponse:
    status = getattr(error, "status_code", None)
    category: Error = {
        400: "invalid_request",
        401: "auth",
        403: "permission",
        404: "unsupported_capability",
        408: "uncertain",
        409: "uncertain",
        429: "rate_limit",
        529: "provider_overloaded",
    }.get(status or 0, "uncertain")  # type: ignore[assignment]
    body = getattr(error, "body", None)
    body_error = body.get("error", body) if isinstance(body, dict) else {}
    if isinstance(body_error, dict) and (
        body_error.get("code") in {"insufficient_quota", "billing_hard_limit_reached"}
        or body_error.get("type") in {"insufficient_quota", "billing_error"}
    ):
        category = "quota"
    if isinstance(error.__cause__, httpx.ConnectTimeout):
        category = "timeout_connect"
    elif isinstance(error.__cause__, httpx.ReadTimeout):
        category = "timeout_read"
    elif status is not None and status >= 500:
        category = "provider_overloaded"
    retry_after = 0
    response = getattr(error, "response", None)
    if response is not None:
        hint = response.headers.get("retry-after", "")
        if hint.isdigit():
            retry_after = min(int(hint), 3600)
    return ProviderResponse(
        status="uncertain"
        if category in {"uncertain", "timeout_connect", "timeout_read"}
        else "failed",
        error=category,
        retry_after=retry_after,
    )


def permitted_input(call: ProviderCall) -> str:
    # Material scope is selected by the parent; no envelope IDs or capability leak.
    return json.dumps(
        {
            "untrusted_data": {
                "evidence": [e.model_dump(mode="json") for e in call.context.evidence],
                "excerpts": call.context.document_excerpts,
                "omissions": call.context.omissions,
            }
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class OpenAIProvider:
    model = "gpt-4.1-mini-2025-04-14"

    def __init__(self, credential: str, transport: httpx.BaseTransport | None = None) -> None:
        self.credential = credential
        self.transport = transport

    def capabilities(self, model_id: str) -> dict[str, bool]:
        return {
            "structured_output": model_id == self.model,
            "account_verified": False,
            "tools": False,
        }

    def normalize_usage(self, response: dict) -> Usage:
        return Usage(
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            cached_tokens=(response.get("input_tokens_details") or {}).get("cached_tokens", 0),
        )

    def normalize_error(self, response: Exception) -> ProviderResponse:
        return error_response(response)

    def safe_metadata(self, value: Any) -> str | None:
        if not isinstance(value, str) or self.credential in value:
            return None
        return value if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value) else None

    def generate_typed(self, call: ProviderCall) -> ProviderResponse:
        if not self.capabilities(call.route.primary_model_id)["structured_output"]:
            return ProviderResponse(status="failed", error="unsupported_capability")
        timeout = httpx.Timeout(
            call.hard_timeout_seconds, connect=1, read=min(5, call.hard_timeout_seconds)
        )
        try:
            with openai.OpenAI(
                api_key=self.credential,
                base_url="https://api.openai.com/v1",
                max_retries=0,
                timeout=timeout,
                http_client=httpx.Client(
                    transport=FixedTransport("api.openai.com", "/v1/responses", self.transport),
                    timeout=timeout,
                    trust_env=False,
                    follow_redirects=False,
                ),
            ) as client:
                response = client.responses.create(
                    model=call.route.primary_model_id,
                    instructions=call.prompt,
                    input=permitted_input(call),
                    max_output_tokens=call.task.max_output_tokens,
                    store=False,
                    tools=[],
                    truncation="disabled",
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "gateway_output",
                            "strict": True,
                            "schema": call.output_schema,
                        }
                    },
                )
            payload = response.model_dump()
            usage = self.normalize_usage(payload["usage"]) if payload.get("usage") else None
            status: Any = (
                "completed"
                if response.status == "completed"
                else "incomplete"
                if response.status == "incomplete"
                else "uncertain"
            )
            refusal = any(
                c.get("type") == "refusal"
                for item in payload.get("output", [])
                for c in item.get("content", [])
            )
            if refusal:
                status = "refused"
            output = response.output_text if status == "completed" else None
            if output and self.credential in output:
                output = '{"secret":"redacted"}'
            return ProviderResponse(
                status=status,
                output=output,
                usage=usage,
                request_id=self.safe_metadata(response._request_id),
                reported_model=self.safe_metadata(response.model),
                error="refused" if refusal else "incomplete" if status == "incomplete" else None,
            )
        except Exception as error:
            return self.normalize_error(error)


class ExplicitAnthropic(anthropic.Anthropic):
    """Explicit-only client for pinned anthropic 1.7.0.

    Its _client._is_base_client uses exact type identity, so subclasses skip
    both default_credentials and _warn_env_shadow's home/profile probe. The
    constructor below also excludes profile/config/token-provider arguments.
    Contract tests pin this SDK behavior; upgrades must reverify it. Parent
    environment isolation remains the contained runner's responsibility.
    """

    def __init__(self, *, api_key: str, http_client: httpx.Client, timeout: httpx.Timeout):
        if not api_key:
            raise ValueError("EXPLICIT_CREDENTIAL_REQUIRED")
        super().__init__(
            api_key=api_key,
            base_url="https://api.anthropic.com",
            max_retries=0,
            timeout=timeout,
            http_client=http_client,
        )


class AnthropicProvider(OpenAIProvider):
    model = "claude-haiku-4-5-20251001"

    def normalize_usage(self, response: dict) -> Usage:
        read = response.get("cache_read_input_tokens", 0) or 0
        return Usage(
            input_tokens=response["input_tokens"] + read,
            output_tokens=response["output_tokens"],
            cached_tokens=read,
            cache_creation_tokens=response.get("cache_creation_input_tokens", 0) or 0,
        )

    def generate_typed(self, call: ProviderCall) -> ProviderResponse:
        if not self.capabilities(call.route.primary_model_id)["structured_output"]:
            return ProviderResponse(status="failed", error="unsupported_capability")
        timeout = httpx.Timeout(
            call.hard_timeout_seconds, connect=1, read=min(5, call.hard_timeout_seconds)
        )
        try:
            with ExplicitAnthropic(
                api_key=self.credential,
                timeout=timeout,
                http_client=httpx.Client(
                    transport=FixedTransport("api.anthropic.com", "/v1/messages", self.transport),
                    timeout=timeout,
                    trust_env=False,
                    follow_redirects=False,
                ),
            ) as client:
                response = client.messages.create(
                    model=call.route.primary_model_id,
                    max_tokens=call.task.max_output_tokens,
                    system=call.prompt,
                    messages=[{"role": "user", "content": permitted_input(call)}],
                    output_config={"format": {"type": "json_schema", "schema": call.output_schema}},
                )
            payload = response.model_dump()
            status: Any = {
                "end_turn": "completed",
                "refusal": "refused",
                "max_tokens": "incomplete",
                "model_context_window_exceeded": "incomplete",
            }.get(response.stop_reason or "", "uncertain")
            output = (
                "".join(b["text"] for b in payload["content"] if b["type"] == "text")
                if status == "completed"
                else None
            )
            if output and self.credential in output:
                output = '{"secret":"redacted"}'
            return ProviderResponse(
                status=status,
                output=output,
                usage=self.normalize_usage(payload["usage"]),
                request_id=self.safe_metadata(response._request_id),
                reported_model=self.safe_metadata(response.model),
                error="refused"
                if status == "refused"
                else "incomplete"
                if status == "incomplete"
                else None,
            )
        except Exception as error:
            return self.normalize_error(error)
