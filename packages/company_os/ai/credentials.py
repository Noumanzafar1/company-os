"""One explicitly selected synthetic credential for offline containment tests."""

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID


def credential_reference(workspace: UUID, provider: str) -> str:
    if provider not in {"openai", "anthropic"}:
        raise ValueError("CREDENTIAL_PROVIDER_MISMATCH")
    return f"preflight:{workspace}:{provider}"


@dataclass(frozen=True)
class SelectedCredential:
    """Transient parent/child value, never a serializable application contract."""

    provider: Literal["openai", "anthropic"]
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.provider not in {"openai", "anthropic"} or not 10 <= len(self.value) <= 512:
            raise ValueError("INVALID_SELECTED_CREDENTIAL")
        if not self.value.isascii() or any(c.isspace() for c in self.value):
            raise ValueError("INVALID_SELECTED_CREDENTIAL")


def credential_binding(workspace: UUID, credential: SelectedCredential) -> str:
    """Domain-separated one-way binding for high-entropy provider keys, not passwords."""
    reference = credential_reference(workspace, credential.provider)
    material = b"company-os/preflight-credential/v1\0" + reference.encode("ascii")
    return (
        "sha256-v1:"
        + hashlib.sha256(material + b"\0" + credential.value.encode("ascii")).hexdigest()
    )


def valid_credential_binding(binding: str | None) -> bool:
    return isinstance(binding, str) and re.fullmatch(r"sha256-v1:[0-9a-f]{64}", binding) is not None


def verify_credential_binding(
    workspace: UUID,
    provider: str,
    reference: str | None,
    binding: str | None,
    credential: SelectedCredential,
) -> None:
    if (
        credential.provider != provider
        or reference != credential_reference(workspace, provider)
        or not valid_credential_binding(binding)
        or not hmac.compare_digest(credential_binding(workspace, credential), binding or "")
    ):
        raise ValueError("CREDENTIAL_CAPABILITY_BINDING_MISMATCH")


def resolve_selected(workspace: UUID, provider: str, reference: str) -> SelectedCredential:
    """Future B2 process-scoped resolution; never called with real values in B1."""
    import os

    if reference != credential_reference(workspace, provider):
        raise ValueError("CREDENTIAL_REFERENCE_DENIED")
    name = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[provider]
    value = os.environ.get(name)
    if value is None:
        raise ValueError("SELECTED_CREDENTIAL_UNAVAILABLE")
    return SelectedCredential(provider, value)  # type: ignore[arg-type]


@dataclass(frozen=True)
class OfflineCredential:
    provider: Literal["openai", "anthropic"]
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.value.startswith("synthetic-") or not 10 <= len(self.value) <= 512:
            raise ValueError("SYNTHETIC_CREDENTIAL_REQUIRED")
