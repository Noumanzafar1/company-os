from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from company_os.adapters.auth import JWTIdentityProvider
from company_os.config import Settings
from company_os.domain.identity import AccessDenied, AuthenticationFailed, SessionIdentity
from company_os.policy.access import require_permission, require_recent_mfa
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import ValidationError

from scripts.boundaries import import_findings, secret_findings
from tests.conftest import identity_token


def config(**updates):
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        console_secret="c" * 64,
        dev_auth_secret="d" * 64,
        **updates,
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"company_env": "staging"},
        {"company_env": "production"},
        {"console_origin": "https://remote.example"},
        {"live_sending_enabled": True},
        {"live_budget_usd": 1},
    ],
)
def test_environment_containment(updates):
    with pytest.raises(ValidationError):
        config(**updates)


def test_fresh_mfa_required_and_admin_not_approver():
    for aal, mfa in [
        ("aal1", None),
        ("aal2", None),
        ("aal2", datetime.now(UTC) - timedelta(minutes=11)),
        ("aal2", datetime.now(UTC) + timedelta(minutes=1)),
    ]:
        with pytest.raises(AccessDenied):
            require_recent_mfa(SessionIdentity(uuid4(), uuid4(), aal, mfa, ""))
    require_recent_mfa(SessionIdentity(uuid4(), uuid4(), "aal2", datetime.now(UTC), ""))
    with pytest.raises(AccessDenied):
        require_permission(["system.read"], "approval.grant")


def test_fake_identity_cannot_assert_mfa():
    settings = config()
    token = identity_token(
        settings, aal="aal2", amr=[{"method": "totp", "timestamp": datetime.now(UTC).timestamp()}]
    )
    identity = JWTIdentityProvider(settings).verify(token)
    assert identity.assurance == "aal1" and identity.mfa_at is None


def test_managed_auth_verifies_asymmetric_signature_and_mfa_without_network():
    settings = Settings(
        _env_file=None,
        company_env="staging",
        auth_mode="supabase",
        database_url="postgresql+psycopg://localhost/test?sslmode=verify-full",
        console_origin="https://console.example",
        console_secret="c" * 64,
        supabase_url="https://identity.example",
    )
    provider = JWTIdentityProvider(settings)
    private_key = ec.generate_private_key(ec.SECP256R1())
    provider.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private_key.public_key())
    )
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "iss": "https://identity.example/auth/v1",
        "aud": "authenticated",
        "sub": "invited-subject",
        "iat": now,
        "exp": now + 900,
        "aal": "aal2",
        "amr": [{"method": "totp", "timestamp": now}],
    }
    token = jwt.encode(claims, private_key, algorithm="ES256")
    verified = provider.verify(token)
    assert verified.subject == "invited-subject" and verified.assurance == "aal2"
    assert verified.mfa_at is not None
    invalid = jwt.encode(claims, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256")
    with pytest.raises(AuthenticationFailed):
        provider.verify(invalid)


def test_guard_detects_secret_and_prohibited_import():
    assert secret_findings(".env", "anything")
    assert secret_findings("source.py", "ghp_" + "a" * 30)
    assert import_findings("packages/company_os/domain/model.py", "import sqlalchemy")
    assert import_findings("apps/api/main.py", "import celery")
    assert import_findings(
        "packages/company_os/application/use_case.py",
        "from company_os.adapters.auth import JWTIdentityProvider",
    )
