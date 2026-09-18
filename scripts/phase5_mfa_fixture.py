"""Explicit offline signed-MFA demonstration, never a production login route."""

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import jwt
from company_os.adapters.auth import JWTIdentityProvider
from company_os.application.identity import IdentityService
from company_os.config import Settings
from company_os.persistence.database import make_engine
from cryptography.hazmat.primitives.asymmetric import ec


def main() -> None:
    config = Settings()
    if config.company_env not in {"development", "test"} or config.auth_mode != "development":
        raise RuntimeError("Offline fixture requires an explicitly local synthetic environment")
    offline = config.model_copy(
        update={"auth_mode": "supabase", "supabase_url": "https://offline-identity.example"}
    )
    provider = JWTIdentityProvider(offline)
    private = ec.generate_private_key(ec.SECP256R1())
    provider.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    now = int(datetime.now(UTC).timestamp())
    assertion = jwt.encode(
        {
            "sub": "synthetic-user-a",
            "iss": "https://offline-identity.example/auth/v1",
            "aud": "authenticated",
            "iat": now,
            "exp": now + 600,
            "aal": "aal2",
            "amr": [{"method": "totp", "timestamp": now}],
        },
        private,
        algorithm="ES256",
    )
    engine = make_engine(config.database_url.get_secret_value())
    try:
        csrf = secrets.token_hex(32)
        session = IdentityService(engine, provider).start(assertion, csrf)
        jar = [
            {
                "name": name,
                "value": value,
                "domain": "localhost",
                "path": "/",
                "expires": now + 600,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Strict",
            }
            for name, value in (("company_session", session), ("company_csrf", csrf))
        ]
        output = Path(".local/phase5-browser.json")
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps({"cookies": jar, "origins": []}), encoding="utf-8")
        print("Offline signed MFA browser fixture ready for ten minutes; ignored local file only.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
