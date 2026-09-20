"""One explicitly selected synthetic credential for offline containment tests."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class OfflineCredential:
    provider: Literal["openai", "anthropic"]
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.value.startswith("synthetic-") or not 10 <= len(self.value) <= 512:
            raise ValueError("SYNTHETIC_CREDENTIAL_REQUIRED")
