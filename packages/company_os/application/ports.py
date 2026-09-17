from typing import Protocol

from company_os.domain.identity import VerifiedIdentity


class IdentityProvider(Protocol):
    def verify(self, token: str) -> VerifiedIdentity: ...
