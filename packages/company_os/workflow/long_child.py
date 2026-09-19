"""Fixed executable entry point. JSON only; no dynamic imports from task input."""

import json
import os
import socket
import subprocess
import sys
import threading
import time

# Executed by absolute path with -I; only the repository package root is added.
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from company_os.long_contracts import MAX_MESSAGE, ExecutionEnvelope, ExecutionResult  # noqa: E402


def main() -> None:
    raw = sys.stdin.buffer.readline(MAX_MESSAGE + 1)
    if len(raw) > MAX_MESSAGE or not raw.endswith(b"\n"):
        return
    envelope = ExecutionEnvelope.model_validate_json(raw)
    cancelled = threading.Event()

    def control() -> None:
        message = sys.stdin.buffer.readline(32)
        cancelled.set()
        if not message:
            # Parent disappeared. Windows Job Object is the independent hard guard.
            if os.name != "nt":
                os.killpg(os.getpgrp(), 9)  # type: ignore[attr-defined]
            os._exit(71)

    threading.Thread(target=control, daemon=True).start()
    start = time.monotonic()
    spec = envelope.spec
    handler = spec.handler
    status = "succeeded"
    error = None
    receipt = None
    if handler == "child_crash":
        sys.exit(23)
    if handler == "abrupt_exit":
        os._exit(24)
    if handler == "no_result":
        return
    if handler == "malformed_result":
        sys.stdout.buffer.write(b"{broken\n")
        return
    if handler == "oversized_result":
        sys.stdout.buffer.write(b"x" * (MAX_MESSAGE + 1))
        sys.stdout.buffer.flush()
        time.sleep(120)
    if handler == "infinite_cpu":
        while True:
            pass
    if handler == "process_tree":
        subprocess.Popen(
            [sys.executable, "-I", "-c", "import time; time.sleep(120)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=dict(os.environ),
            close_fds=True,
        )
    if handler in {"ignore_cancel", "process_tree", "delayed_result_after_lease_loss"}:
        time.sleep(spec.duration_seconds)
    elif handler in {"sleep_success", "cooperative_cancel"}:
        if cancelled.wait(spec.duration_seconds):
            status = "cancelled"
    elif envelope.loopback_port:
        connected = False
        try:
            with socket.create_connection(
                ("127.0.0.1", envelope.loopback_port), spec.connect_timeout_seconds
            ) as sock:
                connected = True
                sock.settimeout(spec.read_timeout_seconds)
                sock.sendall(
                    f"GET /{envelope.execution_id} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode(
                        "ascii"
                    )
                )
                data = bytearray()
                while len(data) <= MAX_MESSAGE:
                    part = sock.recv(min(1024, MAX_MESSAGE + 1 - len(data)))
                    if not part:
                        break
                    data.extend(part)
                body = bytes(data).split(b"\r\n\r\n", 1)[-1]
                if not data:
                    raise ConnectionError("CONNECTION_DROP")
                parsed = json.loads(body)
                if set(parsed) != {"outcome", "receipt"} or parsed["outcome"] not in {
                    "confirmed",
                    "rejected",
                }:
                    raise ValueError("INVALID_RESPONSE")
                status = "succeeded" if parsed["outcome"] == "confirmed" else "rejected"
                receipt = parsed["receipt"]
        except TimeoutError:
            status, error = "transient_failure", "READ_TIMEOUT" if connected else "CONNECT_TIMEOUT"
        except ConnectionError:
            status, error = "transient_failure", "CONNECTION_DROP"
        except (OSError, ValueError, KeyError):
            status, error = "permanent_failure", "INVALID_RESPONSE"
    result = ExecutionResult.model_validate(
        dict(
            execution_id=uuid4() if handler == "corrupted_result" else envelope.execution_id,
            input_hash=envelope.input_hash,
            status=status,
            output_reference=envelope.input_reference,
            error_code=error,
            duration_seconds=time.monotonic() - start,
            receipt_reference=receipt,
            environment_names=sorted(os.environ) if handler == "inspect_environment" else [],
        )
    )
    sys.stdout.buffer.write(result.model_dump_json().encode() + b"\n")
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
        sys.stdout.buffer.flush()
    except SystemExit as error:
        os._exit(int(error.code or 0))
    # The control reader can remain blocked on stdin. Avoid interpreter shutdown
    # waiting for its buffered-reader lock; all result bytes were flushed above.
    os._exit(0)
