import json
import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import psycopg
import pytest
from company_os.config import Settings
from company_os.persistence.database import make_engine
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine

from apps.api.main import create_app


@pytest.fixture(scope="session")
def db_env() -> Iterator[dict[str, str]]:
    base = os.environ["MIGRATION_DATABASE_URL"]
    database = "company_os_test_" + uuid4().hex[:12]
    admin_url = base.rsplit("/", 1)[0] + "/postgres"
    conn = psycopg.connect(admin_url.replace("postgresql+psycopg:", "postgresql:"), autocommit=True)
    conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    env = {
        **os.environ,
        "COMPANY_ENV": "test",
        "AUTH_MODE": "development",
        "DEV_AUTH_SECRET": secrets.token_hex(32),
        "CONSOLE_SECRET": secrets.token_hex(32),
        "FAKE_WEBHOOK_SECRET": secrets.token_hex(32),
    }
    for key in ["MIGRATION_DATABASE_URL", "DATABASE_URL", "WORKER_DATABASE_URL"]:
        env[key] = os.environ[key].rsplit("/", 1)[0] + "/" + database
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0002_identity_guards"],
            env=env,
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                "-c",
                "from database.seeds.synthetic import seed; seed(include_business=False)",
            ],
            env=env,
            check=True,
        )
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0012_phase4_review_fixes"],
            env=env,
            check=True,
        )
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0011_runtime_event_payloads"],
            env=env,
            check=True,
        )
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0005_phase3_review_fixes"],
            env=env,
            check=True,
        )
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0002_identity_guards"],
            env=env,
            check=True,
        )
        with psycopg.connect(
            env["MIGRATION_DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:")
        ) as check:
            assert (
                check.execute("SELECT count(*) FROM pg_tables WHERE schemaname='app'").fetchone()[0]
                == 9
            )
            assert check.execute("SELECT count(*) FROM app.memberships").fetchone()[0] == 2
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0005_phase3_review_fixes"],
            env=env,
            check=True,
        )
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], env=env, check=True)
        with psycopg.connect(
            env["MIGRATION_DATABASE_URL"].replace("postgresql+psycopg:", "postgresql:")
        ) as check:
            assert check.execute("SELECT to_regnamespace('app')").fetchone()[0] is None
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0005_phase3_review_fixes"],
            env=env,
            check=True,
        )
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0005_phase3_review_fixes"],
            env=env,
            check=True,
        )
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        subprocess.run([sys.executable, "-m", "database.seeds.synthetic"], env=env, check=True)
        yield env
    finally:
        # Only the random test database created by this fixture is removed.
        assert database.startswith("company_os_test_")
        conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
        conn.close()


@pytest.fixture(scope="session")
def worker_env(db_env):
    # Exercise the actual launcher sanitizer, not a test-only credential remapping.
    env = json.loads(
        subprocess.check_output(
            [
                "node",
                "--input-type=module",
                "-e",
                "import {serviceEnvironments} from './scripts/local.mjs'; "
                "process.stdout.write(JSON.stringify(serviceEnvironments().workerEnv));",
            ],
            env=db_env,
            text=True,
            timeout=20,
        )
    )
    assert env["WORKER_DATABASE_URL"] == db_env["WORKER_DATABASE_URL"]
    for name in ["DATABASE_URL", "MIGRATION_DATABASE_URL", "DEV_AUTH_SECRET", "CONSOLE_SECRET"]:
        assert name not in env
    return env


@pytest.fixture(scope="session")
def admin(db_env):
    engine = create_engine(db_env["MIGRATION_DATABASE_URL"], hide_parameters=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def runtime(db_env):
    engine = make_engine(db_env["DATABASE_URL"], pool_size=1)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def settings(db_env):
    return Settings(
        _env_file=None,
        **{
            k.lower(): v
            for k, v in db_env.items()
            if k
            in {
                "COMPANY_ENV",
                "AUTH_MODE",
                "DATABASE_URL",
                "CONSOLE_ORIGIN",
                "CONSOLE_SECRET",
                "DEV_AUTH_SECRET",
                "FAKE_WEBHOOK_SECRET",
            }
        },
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as api:
        yield api


def identity_token(settings, subject="synthetic-user-a", **overrides):
    now = datetime.now(UTC)
    claims = {
        "sub": subject,
        "iss": "company-os-local",
        "aud": "company-os-api",
        "iat": now,
        "exp": now + timedelta(minutes=15),
        **overrides,
    }
    return jwt.encode(claims, settings.dev_auth_secret.get_secret_value(), algorithm="HS256")


@pytest.fixture
def login(client, settings):
    def do_login(letter="a"):
        csrf = secrets.token_hex(32)
        response = client.post(
            "/v1/auth/session",
            json={"csrf_token": csrf},
            headers={
                "Authorization": "Bearer " + identity_token(settings, "synthetic-user-" + letter),
                "X-Console-Secret": settings.console_secret.get_secret_value(),
            },
        )
        assert response.status_code == 200, response.text
        return {
            "Authorization": "Bearer " + response.json()["session_token"],
            "Origin": settings.console_origin,
            "X-CSRF-Token": csrf,
        }

    return do_login
