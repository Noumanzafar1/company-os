import secrets
import subprocess
import sys
import time

import httpx

from tests.conftest import identity_token


def test_process_restart_preserves_session_and_worker_shuts_down(
    db_env, worker_env, settings, tmp_path
):
    stop_api = tmp_path / "api.stop"
    stop_worker = tmp_path / "worker.stop"
    api_args = [
        sys.executable,
        "-m",
        "apps.api.run",
        "--port",
        "18001",
        "--stop-file",
        str(stop_api),
    ]
    session_headers = None
    for _ in range(2):
        api = subprocess.Popen(
            api_args, env=db_env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        try:
            for _attempt in range(60):
                try:
                    if (
                        httpx.get("http://127.0.0.1:18001/health/ready", timeout=1).status_code
                        == 200
                    ):
                        break
                except httpx.HTTPError:
                    pass
                if api.poll() is not None:
                    raise AssertionError("API exited before readiness")
                time.sleep(0.1)
            else:
                raise AssertionError("API did not become ready")
            if session_headers is None:
                result = httpx.post(
                    "http://127.0.0.1:18001/v1/auth/session",
                    json={"csrf_token": secrets.token_hex(32)},
                    headers={
                        "Authorization": "Bearer " + identity_token(settings),
                        "X-Console-Secret": settings.console_secret.get_secret_value(),
                    },
                )
                assert result.status_code == 200
                session_headers = {"Authorization": "Bearer " + result.json()["session_token"]}
            profile = httpx.get("http://127.0.0.1:18001/v1/me", headers=session_headers)
            assert profile.status_code == 200
            assert [w["name"] for w in profile.json()["data"]["workspaces"]] == ["Workspace A"]
            stop_api.write_text("stop")
            assert api.wait(timeout=10) == 0
        finally:
            if api.poll() is None:
                api.kill()
                api.wait(timeout=5)
    for _ in range(2):
        worker = subprocess.Popen(
            [sys.executable, "-m", "apps.worker.main", "--stop-file", str(stop_worker)],
            env=worker_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            line = worker.stdout.readline()
            assert '"status": "healthy"' in line
            stop_worker.write_text("stop")
            output, errors = worker.communicate(timeout=10)
            assert worker.returncode == 0, errors
            assert '"status":"stopped"' in output
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
