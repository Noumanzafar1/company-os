"""Real subprocess faults: no mocked process timeout or termination."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from company_os.long_contracts import ExecutionEnvelope, LongSpec
from company_os.workflow.isolation import execute


def envelope(handler="immediate_success", **settings):
    return ExecutionEnvelope(
        execution_id=uuid4(),
        workspace_id=uuid4(),
        job_id=uuid4(),
        attempt_id=uuid4(),
        fence=1,
        input_reference=uuid4(),
        input_hash="a" * 64,
        correlation_id=uuid4(),
        trace_id=uuid4(),
        spec=LongSpec(handler=handler, **settings),
    )


def alive(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


@pytest.mark.parametrize(
    "handler,code",
    [
        ("immediate_success", "RESULT"),
        ("child_crash", "CHILD_CRASH"),
        ("abrupt_exit", "CHILD_CRASH"),
        ("no_result", "MALFORMED_IPC"),
        ("malformed_result", "MALFORMED_IPC"),
        ("corrupted_result", "MALFORMED_IPC"),
        ("oversized_result", "MALFORMED_IPC"),
    ],
)
def test_child_result_failures(handler, code):
    result = execute(envelope(handler), lambda: None)
    assert result.code == code
    assert not alive(result.pid)
    assert result.elapsed_ms < 7000


@pytest.mark.parametrize("handler", ["infinite_cpu", "ignore_cancel", "process_tree"])
def test_hard_timeout_regains_capacity(handler):
    result = execute(
        envelope(handler, duration_seconds=120, hard_timeout_seconds=0.8), lambda: None
    )
    assert result.code == "HARD_TIMEOUT" and result.forced
    assert not alive(result.pid)
    assert result.elapsed_ms < 5000
    assert execute(envelope(), lambda: None).code == "RESULT"


@pytest.mark.parametrize("handler,forced", [("cooperative_cancel", False), ("ignore_cancel", True)])
def test_cancel_is_bounded(handler, forced):
    start = time.monotonic()
    result = execute(
        envelope(handler, duration_seconds=120, hard_timeout_seconds=5),
        lambda: "CANCELLED" if time.monotonic() - start > 0.8 else None,
    )
    assert result.code == "CANCELLED" and result.forced == forced
    assert result.elapsed_ms < 4000 and not alive(result.pid)


def test_secret_free_environment(monkeypatch):
    for key in (
        "DATABASE_URL",
        "WORKER_DATABASE_URL",
        "MIGRATION_DATABASE_URL",
        "FOUNDER_SESSION_TOKEN",
        "PROVIDER_API_KEY",
        "ARBITRARY_CANARY",
    ):
        monkeypatch.setenv(key, "synthetic-sensitive-canary")
    result = execute(envelope("inspect_environment"), lambda: None)
    assert result.code == "RESULT"
    assert {name.upper() for name in result.result.environment_names} <= {
        "SYSTEMROOT",
        "WINDIR",
        "LC_CTYPE",
    }
    assert "canary" not in str(result)


def test_success_arriving_during_timeout_grace_is_discarded():
    outcome = execute(
        envelope(
            "delayed_result_after_lease_loss",
            duration_seconds=0.9,
            hard_timeout_seconds=0.8,
            cancellation_grace_seconds=1,
        ),
        lambda: None,
    )
    assert outcome.code == "HARD_TIMEOUT"
    assert outcome.result is None and not outcome.forced
    assert not alive(outcome.pid)


@pytest.mark.parametrize("handler", ["infinite_cpu", "process_tree"])
def test_parent_death_kills_child(tmp_path, handler):
    pid_path = tmp_path / "child.json"
    script = """
import json,time
from pathlib import Path
from tests.unit.test_long_isolation import envelope
from company_os.workflow.isolation import execute
execute(envelope(__import__('sys').argv[2], duration_seconds=120, hard_timeout_seconds=120), lambda: None,
    lambda event,pid: Path(__import__('sys').argv[1]).write_text(json.dumps(pid)))
"""
    parent = subprocess.Popen(
        [sys.executable, "-c", script, str(pid_path), handler],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(Path("packages").resolve())},
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        until = time.monotonic() + 10
        while not pid_path.exists() and time.monotonic() < until and parent.poll() is None:
            time.sleep(0.05)
        assert pid_path.exists(), (
            parent.stderr.read().decode() if parent.poll() is not None else "No child"
        )
        pid = json.loads(pid_path.read_text())
        time.sleep(0.5)
        assert alive(pid)
        descendants = []
        if handler == "process_tree":
            if os.name == "nt":
                output = subprocess.check_output(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' | Select-Object -ExpandProperty ProcessId",
                    ],
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                descendants = [int(value) for value in output.split()]
            else:
                output = subprocess.check_output(["ps", "-eo", "pid=,ppid="], text=True)
                descendants = [
                    int(line.split()[0])
                    for line in output.splitlines()
                    if int(line.split()[1]) == pid
                ]
            assert descendants and all(alive(value) for value in descendants)
        parent.kill()
        parent.wait(timeout=5)
        until = time.monotonic() + 5
        while alive(pid) and time.monotonic() < until:
            time.sleep(0.05)
        assert not alive(pid)
        assert all(not alive(value) for value in descendants)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        parent.stderr.close()


def test_performance_sample():
    from dataclasses import asdict

    samples = []
    for handler in (
        "immediate_success",
        "sleep_success",
        "infinite_cpu",
        "cooperative_cancel",
        "ignore_cancel",
    ):
        start = time.monotonic()
        cancellation = handler in {"cooperative_cancel", "ignore_cancel"}
        result = execute(
            envelope(
                handler, duration_seconds=5 if cancellation else 0.2, hard_timeout_seconds=1.5
            ),
            lambda cancellation=cancellation, start=start: (
                "CANCELLED" if cancellation and time.monotonic() - start > 0.8 else None
            ),
        )
        sample = {
            key: value for key, value in asdict(result).items() if key not in {"result", "pid"}
        }
        samples.append({"handler": handler, **sample})
        assert not alive(result.pid)
    Path(".local").mkdir(exist_ok=True)
    Path(".local/phase6a-performance.json").write_text(json.dumps(samples, indent=2) + "\n")


@pytest.mark.parametrize("close_error", [BrokenPipeError, OSError, ValueError])
@pytest.mark.parametrize(
    "handler,code",
    [
        ("immediate_success", "RESULT"),
        ("no_result", "MALFORMED_IPC"),
        ("malformed_result", "MALFORMED_IPC"),
    ],
)
def test_exited_child_pipe_cleanup_is_expected(monkeypatch, close_error, handler, code):
    from company_os.workflow import isolation

    real_popen = subprocess.Popen
    closed = []

    class CloseFault:
        def __init__(self, stream, child, name):
            self.stream, self.child, self.name = stream, child, name

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def close(self):
            assert self.child.returncode is not None
            self.stream.close()
            closed.append(self.name)
            raise close_error("Synthetic exited pipe")

    class Child(real_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.stdin = CloseFault(self.stdin, self, "stdin")
            self.stdout = CloseFault(self.stdout, self, "stdout")

    monkeypatch.setattr(isolation.subprocess, "Popen", Child)
    result = execute(envelope(handler), lambda: None)
    assert result.code == code and not alive(result.pid)
    assert closed == ["stdin", "stdout"]


def test_repeated_short_lived_children():
    for _ in range(20):
        result = execute(envelope(), lambda: None)
        assert result.code == "RESULT" and result.result.status == "succeeded"
        assert not alive(result.pid)


@pytest.mark.parametrize("boundary", ["poll", "wait"])
@pytest.mark.parametrize("reason", ["HARD_TIMEOUT", "CANCELLED", "SHUTDOWN", "LEASE_LOST"])
def test_result_admission_rechecks_invalidation(monkeypatch, boundary, reason):
    from types import SimpleNamespace

    from company_os.workflow import isolation

    real_popen, monotonic = subprocess.Popen, time.monotonic
    invalidated = False

    class Child(real_popen):
        def poll(self):
            nonlocal invalidated
            value = super().poll()
            if boundary == "poll" and value is not None:
                invalidated = True
            return value

        def wait(self, *args, **kwargs):
            nonlocal invalidated
            value = super().wait(*args, **kwargs)
            if boundary == "wait":
                invalidated = True
            return value

    # A real valid child exits first. Hold the exit observation or final reap
    # boundary, then advance only the supervisor clock/control before returning.
    monkeypatch.setattr(isolation.subprocess, "Popen", Child)
    monkeypatch.setattr(
        isolation,
        "time",
        SimpleNamespace(
            monotonic=lambda: monotonic() + (60 if invalidated and reason == "HARD_TIMEOUT" else 0),
            sleep=time.sleep,
        ),
    )
    result = execute(
        envelope(hard_timeout_seconds=30),
        lambda: reason if invalidated and reason != "HARD_TIMEOUT" else None,
    )
    assert invalidated and result.code == reason and result.result is None
    assert not alive(result.pid)


def test_containment_failure_is_not_pipe_cleanup(monkeypatch):
    from company_os.workflow import isolation

    original_attach = isolation.ProcessTree.attach
    children = []

    def reject(tree, child):
        original_attach(tree, child)
        children.append(child)
        raise OSError("CONTAINMENT_UNAVAILABLE")

    monkeypatch.setattr(isolation.ProcessTree, "attach", reject)
    with pytest.raises(OSError, match="CONTAINMENT_UNAVAILABLE"):
        execute(envelope("infinite_cpu"), lambda: None)
    assert len(children) == 1 and not alive(children[0].pid)
