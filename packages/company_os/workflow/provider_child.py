"""Fixed contained Gate A runner: scoped fake inference, never ambient secrets."""

import json
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from company_os.ai.contracts import ProviderCall, ProviderReply, ProviderResponse  # noqa: E402
from company_os.ai.credentials import (  # noqa: E402
    OfflineCredential,
    SelectedCredential,
    verify_credential_binding,
)
from company_os.ai.providers import FakeAnthropicProvider, FakeOpenAIProvider  # noqa: E402


def main() -> None:
    raw = sys.stdin.buffer.readline(65537)
    if not raw or len(raw) > 65536:
        return
    call = ProviderCall.model_validate_json(raw)

    credential: OfflineCredential | SelectedCredential | None = None
    mode = "offline-contract"
    if call.route.primary_provider in {"openai", "anthropic"}:
        from decimal import Decimal

        from company_os.ai.preflight import CapabilityReport, live_precheck

        raw_secret = sys.stdin.buffer.readline(8193)
        if len(raw_secret) > 8192:
            return
        value = json.loads(raw_secret)
        if (
            value.get("mode") not in {"offline-contract", "live-preflight", "preflight-contract"}
            or value.get("provider") != call.route.primary_provider
        ):
            return
        mode = value["mode"]
        if mode == "offline-contract":
            credential = OfflineCredential(value["provider"], value["key"])
        else:
            credential = SelectedCredential(value["provider"], value["key"])
            report = CapabilityReport.model_validate(value["report"])
            if live_precheck(call, report, Decimal(value["limit"])):
                return
            verify_credential_binding(
                call.task.workspace_id,
                report.provider,
                report.credential_ref,
                report.credential_binding,
                credential,
            )
            if mode == "preflight-contract" and not credential.value.startswith("synthetic-"):
                return
            if mode == "live-preflight" and credential.value.startswith("synthetic-"):
                return
        del raw_secret, value

    def control() -> None:
        # Parent death and cancellation close the whole POSIX group via parent;
        # EOF also prevents a surviving trusted child from continuing a call.
        sys.stdin.buffer.readline(1024)
        os._exit(2)

    threading.Thread(target=control, daemon=True).start()
    provider = call.route.primary_provider
    if provider == "fake_openai":
        response = FakeOpenAIProvider().generate_typed(call)
    elif provider == "fake_anthropic":
        response = FakeAnthropicProvider().generate_typed(call)
    elif credential is not None and mode == "live-preflight":
        from company_os.ai.sdk_providers import AnthropicProvider, OpenAIProvider

        adapter = OpenAIProvider if provider == "openai" else AnthropicProvider
        response = adapter(
            credential.value, verified_model=call.route.primary_model_id
        ).generate_typed(call)
    elif credential is not None:
        from company_os.ai.offline_probe import probe

        response = probe(call, credential)
    else:
        response = ProviderResponse(status="failed", error="permission")
    result = ProviderReply(
        execution_id=call.execution_id, input_hash=call.input_hash, response=response
    )
    sys.stdout.buffer.write(result.model_dump_json().encode())
    sys.stdout.buffer.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
