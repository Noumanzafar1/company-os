"""Fixed contained Gate A runner: scoped fake inference, never ambient secrets."""

import json
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from company_os.ai.contracts import ProviderCall, ProviderReply, ProviderResponse  # noqa: E402
from company_os.ai.providers import FakeAnthropicProvider, FakeOpenAIProvider  # noqa: E402


def main() -> None:
    raw = sys.stdin.buffer.readline(65537)
    if not raw or len(raw) > 65536:
        return
    call = ProviderCall.model_validate_json(raw)

    credential = None
    if call.route.primary_provider in {"openai", "anthropic"}:
        from company_os.ai.credentials import OfflineCredential

        raw_secret = sys.stdin.buffer.readline(2049)
        if len(raw_secret) > 2048:
            return
        value = json.loads(raw_secret)
        if (
            value.get("mode") != "offline-contract"
            or value.get("provider") != call.route.primary_provider
        ):
            return
        credential = OfflineCredential(value["provider"], value["key"])
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
