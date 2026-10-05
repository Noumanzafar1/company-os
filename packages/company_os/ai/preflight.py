"""Documentation evidence is never account permission. Gate A has no live authority."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from company_os.ai.contracts import Frozen, ProviderCall
from company_os.ai.credentials import credential_reference, valid_credential_binding
from company_os.runtime_contracts import UtcTime


class CapabilityReport(Frozen):
    provider: Literal["openai", "anthropic"]
    environment: Literal["test"]
    model_id: str
    checked_at: UtcTime
    expires_at: UtcTime
    account_verified: bool = False
    structured_output: bool = False
    billing_verified: bool = False
    retention_approved: bool = False
    region_approved: bool = False
    rates_verified: bool = False
    requests_per_minute: int = 0
    input_token_limit: int = 0
    output_token_limit: int = 0
    sdk_version: str
    external_account_id: str | None = None
    credential_ref: str | None = None
    credential_binding: str | None = Field(
        default=None, pattern=r"^sha256-v1:[0-9a-f]{64}$", repr=False
    )


def precheck(
    call: ProviderCall, report: CapabilityReport | None, live_limit: Decimal = Decimal(0)
) -> str | None:
    if live_limit <= 0:
        return "LIVE_AUTHORIZATION_REQUIRED"
    if report is None:
        return "PROVIDER_PREFLIGHT_REQUIRED"
    if (
        not all(
            (
                report.account_verified,
                report.structured_output,
                report.billing_verified,
                report.retention_approved,
                report.region_approved,
                report.rates_verified,
            )
        )
        or not report.checked_at <= datetime.now(UTC) < report.expires_at
        or report.model_id != call.route.primary_model_id
        or report.provider != call.route.primary_provider
        or not report.credential_ref
        or not report.external_account_id
        or report.requests_per_minute <= 0
        or call.task.max_input_tokens > report.input_token_limit
        or call.task.max_output_tokens > report.output_token_limit
    ):
        return "PROVIDER_PREFLIGHT_REQUIRED"
    return None


def live_precheck(call: ProviderCall, report: CapabilityReport, limit: Decimal) -> str | None:
    """Closed dispatch distinction in addition to account capability evidence."""
    from importlib.metadata import version

    if (
        call.task.execution_mode != "live_preflight"
        or call.task.max_model_calls != 1
        or call.ordinal != 1
        or call.scenario != "success"
        or call.route.selection != "preflight"
        or call.route.region_policy != "preflight_required"
        or call.route.fallback_provider is not None
        or call.route.fallback_model_id is not None
        or call.task.allowed_providers != (report.provider,)
        or report.credential_ref != credential_reference(call.task.workspace_id, report.provider)
        or not valid_credential_binding(report.credential_binding)
        or report.sdk_version != version(report.provider)
    ):
        return "LIVE_PREFLIGHT_BINDING_REQUIRED"
    return precheck(call, report, limit)
