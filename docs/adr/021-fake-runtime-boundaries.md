# ADR-021 — Phase 4 fake runtime boundaries

Status: implementation proposal under explicit Phase 4 authority; independent
review required before commit/push.

Preserve ADR-006/009/010/017. PostgreSQL remains the durable coordinator. API and
worker invoke shared application commands. No real business-provider calls.

Use workspace-scoped `fake_endpoints`, constrained to adapter `fake_local_v1`,
as DATA-052's connection target. It contains no credentials, provider scopes,
preflight or authorization claims. Future migration can map these references to
canonical connections; fake identifiers must never activate a real adapter.
Approval and policy UUIDs remain null with database checks. A fixed versioned
`phase-4-fake-v1` contract identifies synthetic authority and rate configuration;
it does not grant external business authority. No approval-use table exists.

Fake receipt storage commits independently of command transactions to model
remote acceptance followed by local response loss. It is synthetic adapter state,
not a new system of record for real effects. Reconciliation reads this ledger;
missing or delayed receipts remain unknown. It never dispatches.

Job attempts use immutable start and finish records, with one finish per attempt.
The API combines them into attempt history. This preserves append-only DATA-051
without mutable attempt history. Synthetic inputs are closed immutable records.
Runtime subjects reference those inputs; no fake account or business authority
is inferred. Events use typed aggregate references validated by runtime commands.

Runtime service grants are scoped to explicitly seeded workspaces. A narrow
fixed-search-path helper exposes authorized workspace/epoch metadata only;
all payload operations use transaction-local context and existing membership RLS.
Runtime roles remain non-owner, NOSUPERUSER and NOBYPASSRLS. Existing business
table permissions are unchanged. Technical control permission does not imply
business approval permission.

FAKE PHASE 4 TEST AUTHENTICATION — NOT A PROVIDER GUARANTEE.
Fake callbacks use a local/test-only HMAC key from ignored environment config,
a signed delivery timestamp, and a registered endpoint. No callback payload can
choose the workspace. Raw bodies are bounded and encrypted with the existing
cryptography dependency; retention metadata is explicit. Future providers require
their own documented authenticity and reconciliation contracts.

## Accounting and scoped callback refinements

Company daily/monthly caps live in a restricted global `company_runtime_caps`
configuration. Runtime roles cannot read it. A fixed-search-path boolean helper
checks current spend and outstanding logical reservations while a company-level
transaction lock serializes new reservations. It returns no other workspace's
cost data. Workspace daily/monthly and synthetic fixture caps are locked in UUID
order; `reservation_budget_caps` attaches additional caps to one logical
reservation. Settlement updates all attached counters and writes one usage entry.
The caps are synthetic fixtures, never authorization for real spending.

`runtime_completions` records authenticated, fenced, idempotent fake completion
receipts. They can resume only a matching synthetic external wait, never set an
arbitrary status or resolve an effect. Attention snooze is founder-only and cannot
hide P0/P1 incidents. Existing command receipts provide HTTP request idempotency
for technical controls, independently of logical effect keys.

## Event schema and finite workflow refinements

The initial Phase 4 fixture emitted ID-only event schema v1. Revision 0011 adds
schema v2 with named job/attempt/error, effect/receipt, budget and incident fields,
validated against the typed aggregate snapshot by a database trigger. Immutable v1
rows remain readable; both versions use the same consumer identity, so a schema
change does not authorize duplicate processing. Replay remains a separate namespace
with effects disabled. No historical migration or event is rewritten.

Handlers renew their lease every 15 seconds using a separate short scoped
transaction; each execution process has at most two connections. All writes still
check owner, fence and database-clock expiry. Reconciliation and cancellation
recompute the finite parent workflow. Reconciliation lag becomes red after five
minutes; fake adapter health remains UNKNOWN until an actual fixture observation.

## Independent Phase 4 review corrections

Revision `0012_phase4_review_fixes` preserves the originating effect `job_id` as
the sole execution authority. The effect's identity and reservation references
are immutable at the database boundary. A synthetic job may hold `effect_id`
only for its own effect; duplicate jobs instead hold `coalesced_effect_id`, with
the same request hash and no reservation. They never dispatch, cancel or settle
the canonical effect. Maintenance projects its confirmed, rejected or cancelled
result onto waiting followers, including legacy followers backfilled by 0012.
The API and console expose the canonical job reference. Request hash conflicts
remain `EFFECT_KEY_CONFLICT`; `begin_dispatch()` retains its ownership check.

First creation is serialized before the effect lookup with a transaction-level
PostgreSQL advisory lock over the server-derived workspace, fake connection UUID
and logical effect key (hash namespace 53). The lock lasts through commit or
rollback, including budget/quota reservation. A waiter re-reads the effect after
the winner commits and follows it without reserving resources. The endpoint uses
a shared row lock to keep its configuration stable without serializing all effect
keys on an exclusive endpoint lock. Hash collisions can add contention but cannot
permit duplicate creation. Job/input hash consistency is checked before creation;
existing-effect hash conflicts remain rejected. No schema change is required.

Successful recovery resolves dead-letter incidents and attention along its
`recovery_of_id` ancestry, emitting the registered incident-resolved event once.
Original failed jobs, attempts and incident opening evidence remain intact.
Current dead-letter health counts unresolved incidents; queue/history views
retain historical failures. Failed recovery leaves the original incident open
and creates its own current failure. This is technical recovery, not approval.

New event insertion checks the current typed aggregate version in PostgreSQL:
immutable runtime inputs use 1; jobs, effects, budgets and incidents use their
current `record_version`. Mutable aggregate rows are locked through payload
validation, closing the version/state race. Immutable schema-v1/v2 history is
neither updated nor retroactively validated.

Schedule writes require a strict 00:00–23:59 daily clock and a zone present in
PostgreSQL's installed IANA timezone catalog. Runtime validation uses Python's
IANA data too. A malformed legacy row, including a zone unavailable to Python,
is disabled with `INVALID_SCHEDULE` and a technical audit entry before emitting
work; other due schedules continue. The database permits only this narrow
quarantine transition without changing invalid legacy configuration. DST gaps
are skipped and repeated wall times use the first fold. No scheduling UI or
administration workflow is introduced.

Generic blocking-handler termination remains technical debt. No long-running,
provider or AI handler may be admitted until timeout/fencing behavior and
cancellation are explicitly validated. This is a prerequisite for the first
phase introducing network/model workloads, especially Phase 6. Synthetic local
fairness/performance measurements are bounded evidence, not production claims;
this correction adds no supervisor, broker or scaling redesign.
