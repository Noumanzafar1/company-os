"""Bounded parent-owned execution supervisor; handler goodwill is unnecessary."""

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from pydantic import ValidationError

from company_os.ai.contracts import ProviderCall, ProviderReply
from company_os.ai.credentials import OfflineCredential
from company_os.long_contracts import MAX_MESSAGE, ExecutionEnvelope, ExecutionResult
from company_os.workflow.process_tree import ProcessTree


@dataclass(frozen=True)
class Outcome:
    code: str
    result: Any
    forced: bool
    pid: int
    startup_ms: float
    elapsed_ms: float
    cleanup_ms: float
    ipc_read_ms: float


def child_environment() -> dict[str, str]:
    # Allowlist, never copy the worker environment and remove selected secrets.
    return {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}


def close_pipe(stream: IO[bytes] | None) -> None:
    # Called only after containment termination/reaping. A buffered close may
    # flush into an exited peer; that lifecycle condition is not a task failure.
    if stream is not None:
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def execute(
    envelope: ExecutionEnvelope | ProviderCall,
    control: Callable[[], str | None],
    observe: Callable[[str, int], None] = lambda *_: None,
    *,
    offline_credential: OfflineCredential | None = None,
) -> Outcome:
    if offline_credential and (
        not isinstance(envelope, ProviderCall)
        or envelope.route.primary_provider != offline_credential.provider
    ):
        raise ValueError("CREDENTIAL_PROVIDER_MISMATCH")
    if (
        isinstance(envelope, ProviderCall)
        and envelope.route.primary_provider in {"openai", "anthropic"}
        and offline_credential is None
    ):
        raise ValueError("LIVE_AUTHORIZATION_REQUIRED")
    started = time.monotonic()
    provider_call = isinstance(envelope, ProviderCall)
    limits = envelope if isinstance(envelope, ProviderCall) else envelope.spec
    deadline = started + limits.hard_timeout_seconds
    max_message = 65536 if provider_call else MAX_MESSAGE
    entrypoint = "provider_child.py" if provider_call else "long_child.py"

    def invalidation() -> str | None:
        return control() or ("HARD_TIMEOUT" if time.monotonic() >= deadline else None)

    tree = ProcessTree()
    child = None
    forced = False
    result: Any = None
    code = "CHILD_CRASH"
    startup = 0.0
    cleanup = started
    data = bytearray()
    overflow = threading.Event()
    reader = None
    receive_times: list[float] = []
    try:
        child = subprocess.Popen(
            [sys.executable, "-I", str(Path(__file__).with_name(entrypoint))],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=child_environment(),
            close_fds=True,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,  # type: ignore[attr-defined]
        )
        # No execution envelope is released before containment succeeds. Parent
        # death before attach closes stdin, so the child exits without starting.
        tree.attach(child)
        assert child.stdin is not None and child.stdout is not None
        raw = envelope.model_dump_json().encode() + b"\n"
        if len(raw) > max_message:
            raise ValueError("ENVELOPE_TOO_LARGE")

        def read() -> None:
            assert child is not None and child.stdout is not None
            while len(data) <= max_message:
                chunk = child.stdout.read(1)
                if not chunk:
                    return
                data.extend(chunk)
                if not receive_times:
                    receive_times.extend([time.monotonic(), time.monotonic()])
                else:
                    receive_times[1] = time.monotonic()
            overflow.set()

        reader = threading.Thread(target=read, daemon=True, name="bounded-result-reader")
        reader.start()
        observe("child_started", child.pid)
        child.stdin.write(raw)
        if offline_credential:
            # Separate bounded one-time channel after tree.attach; never part of envelope.
            secret = (
                json.dumps(
                    {
                        "provider": offline_credential.provider,
                        "key": offline_credential.value,
                        "mode": "offline-contract",
                    }
                ).encode()
                + b"\n"
            )
            child.stdin.write(secret)
            del secret
        child.stdin.flush()
        startup = (time.monotonic() - started) * 1000
        reason = None
        while True:
            # Invalidation wins even if a late success is already in the pipe.
            reason = control()
            if reason or time.monotonic() >= deadline or overflow.is_set():
                cleanup = time.monotonic()
                reason = reason or ("MALFORMED_IPC" if overflow.is_set() else "HARD_TIMEOUT")
                code = reason
                observe(reason.lower(), child.pid)
                try:
                    child.stdin.write(b'{"cancel":true}\n')
                    child.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                try:
                    child.wait(timeout=limits.cancellation_grace_seconds)
                except subprocess.TimeoutExpired:
                    forced = True
                    observe("forced_termination", child.pid)
                    tree.terminate(child)
                break
            if child.poll() is not None:
                cleanup = time.monotonic()
                code = invalidation() or ("RESULT" if child.returncode == 0 else "CHILD_CRASH")
                break
            time.sleep(0.025)
        child.wait(timeout=5)
        reader.join(timeout=1)
        if reader.is_alive() or overflow.is_set():
            code = "MALFORMED_IPC"
        if code == "RESULT":
            code = invalidation() or code
        if code == "RESULT":
            try:
                if isinstance(envelope, ProviderCall):
                    result = ProviderReply.model_validate_json(bytes(data))
                else:
                    result = ExecutionResult.model_validate_json(bytes(data))
                    if (
                        result.handler_version != envelope.spec.handler_version
                        or result.output_reference != envelope.input_reference
                    ):
                        raise ValueError("RESULT_BINDING")
                if (
                    result.execution_id != envelope.execution_id
                    or result.input_hash != envelope.input_hash
                ):
                    raise ValueError("RESULT_BINDING")
            except (ValueError, ValidationError):
                result, code = None, "MALFORMED_IPC"
            if reason := invalidation():
                result, code = None, reason
    finally:
        if child is not None:
            # Also remove descendants after a clean child exit.
            tree.terminate(child)
            child.wait(timeout=5)
            tree.close()
            close_pipe(child.stdin)
            if child.stdout:
                if reader:
                    reader.join(timeout=1)
                close_pipe(child.stdout)
        else:
            tree.close()
    ended = time.monotonic()
    return Outcome(
        code,
        result,
        forced,
        child.pid,
        startup,
        (ended - started) * 1000,
        (ended - cleanup) * 1000,
        (receive_times[1] - receive_times[0]) * 1000 if receive_times else 0.0,
    )
