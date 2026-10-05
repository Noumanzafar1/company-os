# ADR-025 — Closed live-provider technical preflight

Status: implemented under the founder's reviewed B1 enablement request; independent
review remains required. Verification results are recorded in the phase handoff.
No real provider request or credential resolution is authorized in B1.

## Context and authority

Gate A intentionally implemented fake technical execution and offline SDK probes.
Gate B correctly stopped at GB-001–GB-007: the normal application, database and
contained child had no authorized live path. Core remains closed. This decision
extends ADR-024's deferred selected-secret design, without production enablement.

## Closed command and route

`application.ai_preflight` exposes narrow in-process authorize, provision and
submit commands. Each requires the current founder with recent verified MFA in
the assigned workspace. There is no generic connection PATCH or activation API.
Gate authorization creates an immutable expiring gate backed by an existing
budget row. Configuration provisioning is version checked against the connection,
uses existing closed prompt/schema records, and records immutable route, price and
capability evidence. An ordinary worker cannot provision any of these objects.

The application calls fixed-search-path security-definer functions owned by the
existing non-login `company_auth` role. They verify founder authority themselves,
derive workspace/actor from transaction-local context, and operate under FORCE
RLS. API/worker roles cannot assume this role. New gates and route/report bindings
are append-only and use composite workspace foreign keys. Commands append audit.

Ordinary submission remains fake-only. A preflight route is explicitly selected,
remains draft, and cannot be promoted to active. A preflight task is synthetic,
has no tools, no fallback, and exactly one model call. A unique task per provider
binding prevents a new key from replaying a completed or uncertain test.

## Capability and selected-secret flow

The existing CapabilityReport binds test environment, provider, exact model,
account/project, selected reference, installed SDK, verification booleans,
request/token limits and validity interval. Required unknowns fail closed.
Documentation alone is not authenticated account evidence. B1 uses synthetic
reports; B2 must obtain current real account/model/price evidence separately.

Each approved reference is exactly `preflight:<workspace UUID>:openai` or
`preflight:<workspace UUID>:anthropic`. The closed parent resolver maps only these
references to `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`, respectively. It never scans
profiles, paths, home directories or caller-selected variable names. Future B2
provisioning must securely supply only the selected process-scoped value after
independent review and explicit live authorization. No key belongs in chat or Git.

The worker commits ModelRun and pessimistic reservation, rechecks current
authority/context/report, then resolves one credential. Its typed value has a
redacted repr and is absent from the envelope. The existing supervisor attaches
OS process containment before releasing the envelope and the separately bounded
one-time stdin message. The child inherits only the existing OS environment
allowlist and rechecks preflight bindings. Revocation/timeout wins over late output.

Real SDK translation uses fixed official endpoints, disabled redirects/proxies,
zero SDK retries, bounded output and timeout. Current model IDs come from verified
configuration; historical adapter candidates do not become B2 selections.
An explicit synthetic-only contract mode uses the same contained child with a
mock HTTP transport. It cannot accept a non-synthetic credential, and the live
mode explicitly refuses synthetic credentials before launch and in the child. No B1 test may
use the live transport. Python tests also deny non-loopback socket/DNS access.

## Accounting and failure

The dedicated gate budget is shared across both providers. It uses the existing
reservation and settlement infrastructure, global reservation lock, row locks and
database budget ceiling constraints. Deferred database checks bind counters to
actual reservations and ModelRuns; arbitrary counter edits cannot free exposure.
The non-login helper receives scoped ModelRun reads and budget row-lock permission;
API and worker roles gain no configuration-write grants. Synthetic technical budgets remain separate.
Maximum exposure includes the most expensive supported input token class and
bounded output. Unknown usage, timeout or process loss keeps the reservation.
Known bounded usage settles once. There is no automatic live repair, retry,
fallback or uncertain replay, even when the generic job runtime retries a lease.

## Migration and review boundary

One additive revision, `0027_phase6b_live_preflight`, preserves 0001–0026.
Real connections may be testing with an exact tenant/provider reference; they
cannot be generally enabled. New preflight history prevents downgrade. A
disposable database without preflight history may return to 0026 and re-upgrade.

This decision does not authorize B2 execution, production routes, deployment,
business data, outbound or Phase 7. The handoff must report actual test evidence
and any incomplete work; this ADR is not acceptance evidence by itself.

## Unreleased migration exception for this cycle

The founder explicitly authorized revising unpublished 0027 only after verifying
six conditions: not on protected main, never pushed, not in a merged PR, applied
only locally, rollback limited to disposable no-history data, and 0001–0026 byte
integrity. All conditions were recorded before edits. A newly created loopback
B1 database had 98 empty application tables and was rolled back to 0026 first.
The existing development database was not rolled back or changed by this cycle.
This is a one-time exception, not a general policy change. Published 0027 becomes
immutable. B2 must use a database freshly migrated from the reviewed source, not
the earlier development database containing an obsolete unreviewed draft of 0027.

## Independent review corrections: credential version and rollback grants

The capability report now requires `credential_binding`, formatted as
`sha256-v1:` followed by 64 lowercase hex digits. Its SHA-256 input is the fixed
ASCII domain `company-os/preflight-credential/v1`, a NUL separator, the exact
workspace/provider reference, another NUL separator, and the selected credential
bytes. SHA-256 preimage resistance is appropriate for high-entropy provider API
keys; this is not password hashing or encryption. The reference scopes comparisons
to a workspace/provider, and the version prefix allows a future reviewed change.

During future authorized account verification, the trusted verifier must compute
this binding from the SAME selected key used to verify the reported account and
include it in the founder-authorized immutable report. B1 only does this with
synthetic canaries. A digest does not prove account ownership, validity, entitlement
or billing by itself. Low-entropy keys permit offline guessing; binding metadata
may correlate use within its workspace/provider scope. Protect report access with
existing RLS, and do not expose the digest through ordinary health/UI responses.
A compromised trusted parent or dishonest verifier is outside this substitution
check; it is not remote attestation.

After durable reservation and fresh report checks, the parent resolves only the
closed selected environment slot, recomputes the digest and compares in constant
time. A mismatch stops before supervisor dispatch. The supervisor verifies again
before creating the child; the fixed child verifies again before SDK translation.
The immutable typed selected value is dispatched, not a later environment lookup.
Key rotation therefore requires fresh account verification and a new report/binding.
Old reports without a binding fail closed. The raw key never enters persisted
report/configuration or the serializable ProviderCall; secondary stdin delivery
still happens only after containment. A mismatch retains the conservative durable
reservation and cannot replay automatically.

The migration regression measures every company_auth application-table grant at
0026, upgrades, downgrades, compares the exact privilege/grant-option set and
re-upgrades. Historical authority_test_targets SELECT/UPDATE are preserved;
0027 adds and revokes only INSERT there. No historical migration was edited.
B2 MUST use a freshly created/migrated database from the finally reviewed 0027
source, or one whose schema equivalence has been independently proven. The obsolete
local draft database is not evidence and must not be silently reused.
