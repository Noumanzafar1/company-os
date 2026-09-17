from datetime import UTC, datetime
from typing import Any, Literal

import jwt

from company_os.config import Settings
from company_os.domain.identity import AuthenticationFailed, VerifiedIdentity


class JWTIdentityProvider:
    """Supabase-compatible verifier; subject mapping never provisions app users."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jwks = (
            jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json", timeout=5)
            if settings.auth_mode == "supabase"
            else None
        )

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            if self.jwks is None:
                key: Any = self.settings.dev_auth_secret.get_secret_value()
                algorithms = ["HS256"]
                issuer = "company-os-local"
                audience = "company-os-api"
            else:
                key = self.jwks.get_signing_key_from_jwt(token).key
                algorithms = ["ES256", "RS256"]
                issuer = f"{self.settings.supabase_url}/auth/v1"
                audience = self.settings.supabase_jwt_audience
            claims = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=audience,
                issuer=issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            if claims["exp"] - claims["iat"] > 900:
                raise AuthenticationFailed("Access token lifetime exceeds policy")
            subject = str(claims["sub"])
            if self.jwks is None and subject not in {"synthetic-user-a", "synthetic-user-b"}:
                raise AuthenticationFailed("Uninvited identity")
            # Development identity can never assert elevated MFA.
            assurance: Literal["aal1", "aal2"] = "aal1"
            mfa_at = None
            if self.jwks is not None and claims.get("aal") == "aal2":
                times = [
                    entry["timestamp"]
                    for entry in claims.get("amr", [])
                    if entry.get("method") in {"totp", "webauthn"}
                ]
                if times:
                    assurance = "aal2"
                    mfa_at = datetime.fromtimestamp(max(times), UTC)
            return VerifiedIdentity(subject, assurance, mfa_at)
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise AuthenticationFailed("Invalid identity") from exc
