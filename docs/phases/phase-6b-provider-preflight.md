# Phase 6B provider research and live-preflight boundary

Research date: 2026-09-19 UTC. Gate A only. No real provider calls authorized or
performed. No account entitlement, billing, region, rate limit, retention approval
or live structured-output capability has been verified. Chat subscriptions do not
constitute API spending authority. No production route is provisioned.

## Documentation evidence

| Provider | Documented candidate snapshot | SDK pinned in requirements.lock | API translation |
| --- | --- | --- | --- |
| OpenAI | gpt-4.1-mini-2025-04-14 | openai 3.16.2 | Responses; text.format json_schema, strict=true; store=false; tools=[]; truncation=disabled |
| Anthropic | claude-haiku-4-5-20251001 | anthropic 1.7.0 | Messages; output_config.format json_schema; no tools |

These are exact documented candidates for a future bounded preflight, not claims
of account availability or production suitability. Both current SDKs use httpx2;
the explicitly pinned transport is 2.13.0. Automatic SDK and transport retries are
zero. HTTP redirects and ambient proxy use are disabled. Each adapter accepts only
its fixed model snapshot and first-party POST endpoint.

Pinned anthropic 1.7.0 uses an exact-type `_is_base_client` gate. The explicit-only
subclass therefore skips `default_credentials` and `_warn_env_shadow` (which probes
home/profile paths even with an explicit key). Its closed constructor permits no
profile/config/token-provider arguments. Tests intercept both discovery functions,
verify the base-client positive control, and run contained offline probes with parent
key/profile/config/home canaries. The probe checks the actual minimal child environment;
explicit synthetic auth reaches only the fixed mock transport header, never request
body, response or captured logs. It has no audit/database capability. Isolation also
requires stripped environment, post-containment key delivery and trust_env=False.
This behavior is specific to the pinned SDK and must be reverified on upgrades.
No live account behavior is proven by these offline tests.

Primary references checked during implementation:

- [OpenAI model](https://developers.openai.com/api/docs/models/gpt-4.1-mini): structured output, 1,047,576-token context, 32,768 maximum output; documented USD per million input/cached/output 0.40/0.10/1.60.
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs): constrained JSON is followed by local validation; refusals have separate handling.
- [OpenAI Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses): structured output through text.format.
- [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data): store=false does not itself mean zero data retention.
- [OpenAI limits](https://developers.openai.com/api/docs/guides/rate-limits) and [Python SDK](https://developers.openai.com/api/reference/python): account-specific limits and explicit retry configuration.
- [Anthropic model overview](https://platform.claude.com/docs/en/models/overview) and [pricing](https://platform.claude.com/docs/en/about-claude/pricing): Haiku 4.5 candidate, documented base USD per million input/output 1/5. Cache pricing is not configured for a live route.
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs): output_config.format; refusal and token-limit stops remain separate outcomes.
- [Anthropic Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python), [limits](https://platform.claude.com/docs/en/api/rate-limits), and [data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention).

Provider-neutral schemas omit provider-unsupported length/format keywords; Company
OS enforces the full bounded Pydantic schema, evidence membership and support,
forbidden capabilities, usage validity and current context locally. The mock HTTP
tests prove translation and normalization only. They do not prove provider schema
acceptance, model availability, billing or live quality.

## Required separate Gate B evidence

Founder authorization must name providers and a strict aggregate dollar cap before
any real call. A reviewed secret-delivery ADR is also required. Resolve only the
selected credential reference in the trusted parent. Record exact account/project,
environment, region, data/retention policy, entitlement, callable model snapshot,
limits, schema capabilities, current verified pricing including all cache/billable
units, SDK version and report expiry. Unknown fields deny dispatch.

The current database accepts real connection statuses only unconfigured/disabled,
and requires null credential references. The application and provider child have
no live-enable command. The separate stdin credential path is restricted to
synthetic credentials and a fixed no-network SDK probe. Enabling real credentials
requires a reviewed follow-on change and the founder's separate authorization;
setting an environment variable cannot enable it.

Future authorized preflight must use synthetic data, one explicitly chosen
provider at a time, independent measured calls, pessimistic reservations, no
automatic cross-provider fallback, explicit deadlines and bounded output. Save
request IDs, model versions, usage, actual spend, refusals/incomplete outcomes and
evaluation results. Do not infer business quality from the technical fixtures.

Live preflight status: **PROVIDER_PREFLIGHT_REQUIRED**.
Business quality status: **FOUNDER_LABELLED_DATASET_REQUIRED**.
