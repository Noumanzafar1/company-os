# PHASE 4 FINAL CORRECTION HANDOFF

## Phase 4 Final Correction Gate

**PASS — effect-creation serialization and the complete regression gate passed.**

Verified on 18 September 2026 with the explicitly authorized elevated Windows
process/temp/browser/network environment. The previous review accepted the other
four correction areas with this one remaining fix. This report supplies correction
evidence for Nouman's acceptance; it does not infer independent FINAL PASS or
authorization to commit. Previous correction and environmental history is retained
verbatim below and in the manifest's historical verification records.

## Effect-Creation Race

`prepare_effect()` validates the claimed job's hash against its immutable input,
then takes a shared row lock on the selected enabled fake endpoint. It acquires
`pg_advisory_xact_lock(hashtextextended(workspace_uuid || ':' || connection_uuid ||
':' || effect_key, 53))` before querying effects or reserving budget/quota.
Workspace is server-derived from transaction-local context. Fixed-width UUIDs and
separators make the identity unambiguous. The transaction-level lock is released
only on commit/rollback; a waiter performs a fresh effect lookup after acquiring it.
This explicitly serializes missing-row creation instead of relying on an exclusive
endpoint lock or on a row that does not exist. Endpoint configuration remains stable
through the shared lock. A hash collision adds contention, never duplicate authority.

The first compatible contender creates the canonical effect and its sole logical
budget/quota reservation. Later compatible contenders attach only
`coalesced_effect_id`, with no `effect_id` or budget reservation. Existing follower
completion, dispatch ownership and cancellation/settlement semantics are unchanged.
Different hashes return `EFFECT_KEY_CONFLICT` before resource allocation. The earlier
job/input check closes the first-creation case too; a malformed contender cannot
become owner merely because no effect exists yet. Existing-effect request hashes
are still validated after the locked lookup.

No unique constraints or ownership guards were removed or weakened. No schema or
migration change was needed: head remains `0012_phase4_review_fixes`; migrations
0001–0012 and their manifest match the previous correction byte-for-byte.
Requirements remain SYS-007/014; DATA-051/052/053; OPS-016/017; TEST-004/007/009.

## Concurrency Tests

Four new cases use actual PostgreSQL worker-role transactions, independent backend
PIDs and barriers. Same-input races use **2 and 5 simultaneous contenders**. Each
transaction proves no effect or reservation exists before the barrier. A query hook
inspects real `pg_locks` before each effect lookup, proving an advisory lock is held
before creation; reliance only on missing-row locking or the later budget lock fails
this assertion. Both races passed.

Assertions establish exactly one effect and canonical owner, one logical budget
reservation, one reserved quota unit, correct follower references, no follower
reservation, no early fake call, all jobs succeeding after canonical completion,
exactly one fake receipt and usage entry, exactly-once budget/quota settlement,
and no false dead-letter incident or RED dead-letter health. Repeating follower
refresh leaves those results unchanged.

Two hash-conflict races place the incompatible hash in each contender position.
Synthetic inputs are already immutable and unique by logical key, so this fixture
uses two jobs for that same input with different job request hashes. The mismatched
request is rejected regardless of arrival order; the compatible request alone can
be canonical. No database uniqueness rule is bypassed to invent two conflicting
immutable inputs. The rejected job has no canonical reference or reservation;
cancelling it leaves the winning effect and resources unchanged. The winner still
dispatches once and settles once. Both cases passed with `EFFECT_KEY_CONFLICT`,
never `RESERVATION_CONFLICT`.

## Full Regression

All required commands completed with exit 0 on the final corrected implementation:

| Exact command | Result |
|---|---|
| `npm.cmd run db:start` | PASS; PostgreSQL and non-owner runtime roles ready |
| `npm.cmd run check` | PASS; 216 Python tests (149.68s), 2 Vitest tests (244ms), all static checks |
| `npm.cmd run build` | PASS; 21 routes, 18 generated pages |
| `$env:PLAYWRIGHT_CHANNEL='chrome'; node scripts/ci-services.mjs e2e` | PASS; 5 tests (17.3s) against running API, worker and production console |
| `npm.cmd audit --audit-level=moderate` | PASS; 0 vulnerabilities |
| `.\.venv\Scripts\python.exe scripts/audit_python.py --online` | PASS; 49 packages, no findings |
| `git diff --check` | PASS; 0 whitespace errors |
| `$env:PYTEST_ADDOPTS='-p no:cacheprovider'; node scripts/phase4-demo.mjs all` | PASS; 55 tests (137.55s) |

All 212 previous Python tests plus the four new cases passed; no complete-gate tests
were skipped, deselected or weakened. The preliminary focused run passed 4 cases
with 25 unrelated cases deselected. Python reports the same two Starlette/httpx and
anyio deprecation warnings. Browser execution reports two NO_COLOR/FORCE_COLOR
warnings; Git reports seven existing CRLF normalization advisories.
The full fixture retained successful migration round trips through 0011, Phase 3,
Phase 2 and base, plus repeated upgrade/seed. No new migration was applied.

Only handoff/manifest/inventory documentation changed after the implementation gate.
The production build's generated Next type reference was restored exactly from the
reviewed source baseline. Existing recovery/health, event-version, schedule/timezone
and timeout-debt decisions remain unchanged. No long-running/provider/AI handler may
be admitted until timeout/fencing and cancellation are explicitly validated,
especially before Phase 6 workloads. Local synthetic performance remains bounded
evidence, not sustained fairness or production-capacity evidence.

## Git, Rollback and Phase Boundary

Branch remains `phase-4-events-jobs-health`; HEAD, `main` and `origin/main` remain
`e8c896a8fd7669472d9488b83840526ce847ce20`. No commit, push, PR or merge. Changes
remain uncommitted and unstaged. All seven previous ZIPs are preserved unchanged.

This correction has no database rollback. If reverting application code, stop
workers first and restore the prior reviewed application file; this also removes
the explicit creation-serialization guarantee. Migration 0012's prior rollback
limitations remain as documented below. No production provisioning/deployment.

No real provider, OpenAI, Anthropic, AI, outbound, CRM, campaign runtime, n8n Cloud
or full Phase 5 approval engine. **Phase 5 has NOT begun.** Synthetic data and
non-owner NOSUPERUSER/NOBYPASSRLS runtime roles remain the only execution scope.

## Changed Files and Archive

`company-os-phase-4-final-correction-delta.zip` contains only these six changed files.
No unchanged source, previous ZIPs, secrets, dependencies, builds, caches or database
files are included. Its SHA-256 is delivered separately to avoid self-reference.
The correction baseline is `company-os-phase-4-correction-delta.zip`, SHA-256 `ac7d518668a92a282bbb01fc9e3956a848a63dd077b9625aea8bad3f22bc608b`.

- `CORRECTION_FILE_LIST.txt`
- `docs/adr/021-fake-runtime-boundaries.md`
- `docs/phases/phase-4-handoff.md`
- `docs/phases/phase-4-manifest.json`
- `packages/company_os/application/runtime.py`
- `tests/integration/test_phase4_review_fixes.py`

# Previous Correction Handoff — Historical Evidence

The following entire prior report is preserved; its gate and path inventory describe the earlier correction cycle.

# PHASE 4 CORRECTION HANDOFF

## Phase 4 Correction Gate

**PASS — all four bounded corrections implemented and the complete regression gate passed.**

Verified on 18 September 2026 using the authorized elevated Windows process,
temporary-directory, browser and HTTPS environment. The review result was PASS
WITH FIXES; these corrections are ready for Nouman's acceptance review. This
report does not infer independent FINAL PASS or permission to commit. The prior
successful rerun and superseded environmental-failure history are retained below.

## Fix 1 — Logical Effect Ownership

The originating `external_effects.job_id` remains the sole dispatch authority.
Database guards freeze effect ownership, request and reservation references and
reject a synthetic job's attachment to another job's effect. Duplicate jobs use
`coalesced_effect_id`, with matching request hash and no reservation authority.
Their cancellation/failure cannot cancel the canonical effect or release its
budget/quota. `begin_dispatch()` keeps its ownership check. Prepared, dispatching
and uncertain duplicates do not resend; maintenance projects terminal canonical
results onto waiting followers. The API/console expose the canonical job link.
Legacy duplicate references are backfilled without rewriting attempts or outcomes.

Five new test cases cover three concurrent followers after A prepares an effect,
success/rejection/lost-response reconciliation, follower cancellation and failure,
direct ownership-guard rejection, differing input hash (`EFFECT_KEY_CONFLICT`),
a duplicate arriving during dispatch, and a legacy wait code. Assertions prove one
fake receipt, one settlement, truthful terminal outcomes and no remaining follower
wait after reconciliation. Budget and quota counters settle/release once.
Requirements: DATA-051/052/053; OPS-013/016/017; TEST-004/007/009.

## Fix 2 — Recovery / Health Resolution

Successful recovery resolves dead-letter incidents and their attention items along
`recovery_of_id`, recording the registered resolution event once. It preserves
original failed jobs, every original attempt, opening timestamps and evidence.
This also runs when reconciliation or a canonical result completes recovery.
Current dead-letter health counts unresolved incidents; historical queue counts
continue to show failed jobs. Failed recovery leaves the original incident open
and records its own failure.

Two new success/failure tests use the authenticated founder retry API, replay its
idempotency key, compare complete original job/attempt rows, verify incident and
attention states, and repeat resolution. Success removes the historical failure
from current dead-letter health; failed recovery remains RED with two incidents.
Requirements: DATA-051/057; OPS-014/018/019; API-059/060; UI-015.

## Fix 3 — Event Aggregate Version

A BEFORE INSERT database trigger validates immutable runtime input version 1 and
the exact current `record_version` for jobs, effects, budgets and incidents. Mutable
aggregate rows are locked through payload validation. Existing v1/v2 events remain
immutable and are not rewritten or retroactively validated; schema bounds remain.

Ten new cases exercise all five aggregate types using each actual API and worker
database role: correct version, lower/higher version with otherwise correct payload,
foreign workspace, normal `emit()`, and immutable history. Existing event schema,
outbox, replay and tenancy regressions also pass.
Requirements: DATA-050; EVT-001/002/027/029/030/035/038/039; SEC-001/003.

## Fix 4 — Scheduler Integrity

Database validation accepts only `daily:00:00` through `daily:23:59` and a timezone
in PostgreSQL's installed IANA catalog, for inserts and configuration updates.
Runtime validation quarantines corrupt/legacy-invalid rows as disabled with
`INVALID_SCHEDULE` and an audit entry before creating work. Other valid schedules
continue. The database permits only the narrow metadata-only quarantine transition
for an already-invalid configuration; there is no scheduling administration UI.

Seven input cases cover Karachi, New York, invalid zones, hours 23/24/27/99 and
minute 60. An eighth case injects two corrupt schedules through the owner fixture,
reenables validation, runs ordinary maintenance and proves valid work still emits,
both invalid rows are disabled, audit entries exist and a repeat emits no duplicate.
It also verifies the spring gap, first fall fold and next-day behavior after that fold.
Requirements: DATA-051; OPS-013/015; TEST-007/012/014.

## Migration and Rollback

The only new revision is `0012_phase4_review_fixes`, after
`0011_runtime_event_payloads`. Migrations 0001–0011 are byte-for-byte identical to
the reviewed baseline; their immutable hashes are unchanged. The migration manifest
includes 0012. Local synthetic database migration also passed with `npm.cmd run migrate`.

The test fixture successfully runs head → 0011 → head, head → Phase 3 (0005) → head,
head → Phase 2 (0002) → head, and head → base → head, plus repeated upgrade/seed.
These round trips run in both the complete Python suite and the runtime demos.

Rollback requires stopped API/worker processes and a synthetic-data snapshot.
Downgrading to 0011 removes the new guards, follower reference and schedule error
metadata; it does not reconstruct unsafe legacy ownership. Follower metadata would
be lost, so restore the snapshot for an exact data rollback. Its legacy schedule
check is restored NOT VALID so already-quarantined corrupt rows do not block the
downgrade. Downgrading to Phase 3 drops runtime data as previously documented.
No production migration or deployment occurred.

## Full Regression Results

All commands returned exit 0 against the final corrected implementation:

| Command | Result |
|---|---|
| `npm.cmd run db:start` | PASS; local PostgreSQL and non-owner runtime roles ready |
| `npm.cmd run check` | PASS; 212 Python tests (133.52s, 2 warnings), 2 Vitest tests (0.298s); total 151.677s |
| `npm.cmd run build` | PASS; 21 routes, 18 generated pages; 30.719s |
| `$env:PLAYWRIGHT_CHANNEL='chrome'; node scripts/ci-services.mjs e2e` | PASS; 5 browser tests against running services (19.0s); total 25.759s |
| `npm.cmd audit --audit-level=moderate` | PASS; 0 vulnerabilities; 2.320s |
| `.\.venv\Scripts\python.exe scripts/audit_python.py --online` | PASS; 49 packages, no OSV findings; 1.297s |
| `git diff --check` | PASS; no whitespace errors; seven existing CRLF advisories |
| `$env:PYTEST_ADDOPTS='-p no:cacheprovider'; node scripts/phase4-demo.mjs all` | PASS; 51 tests (125.69s, 2 warnings); total 128.020s |

The full suite includes all 25 new correction cases and all 187 prior Python cases.
Contract drift, Ruff, formatting (127 files), mypy (40 files), boundary/security/
immutable-migration checks, frontend lint and TypeScript all passed. No tests were
skipped or weakened. The two Python warnings are existing Starlette/httpx and anyio
deprecations; the two browser warnings concern NO_COLOR/FORCE_COLOR. The build's
generated Next type reference was restored byte-for-byte from the reviewed baseline.
Only handoff/manifest/inventory documentation changed after the complete gate.

## Non-Blocking Debt and Limitations

Generic termination of a long/blocking handler is not implemented. **No long-running,
provider or AI handler may be admitted until timeout/fencing behavior and cancellation
are explicitly validated.** ADR-021 now states this prerequisite for the first network/
model-workload phase, especially Phase 6. No process supervisor or broker was added.

Synthetic local performance remains bounded evidence, not a production fairness or
capacity claim. This run exercised five workspaces, 50,000 additional accounts,
100,000 additional people and ten concurrent users; read/command p95 was 0.187/0.141s.
The 10,000-jobs/day-equivalent fixture executed 40 normal jobs in 0.891s with a 0.157s
safety claim. Sustained multi-workspace fairness/performance remains future validation.

## Git and Phase Boundary

Branch remains `phase-4-events-jobs-health`. HEAD, `main` and `origin/main` remain
`e8c896a8fd7669472d9488b83840526ce847ce20`. Changes remain uncommitted and unstaged.
No commit, push, PR or merge was performed. All six earlier review/correction ZIPs
are preserved unchanged.

No real provider; no OpenAI; no Anthropic; no AI; no outbound; no CRM; no campaign
runtime; no n8n Cloud; no full Phase 5 approval engine; no production deployment.
Phase 5 has NOT begun. Runtime roles remain non-owner, NOSUPERUSER and NOBYPASSRLS,
with transaction-local, server-derived tenant context and synthetic data only.

## Changed Files and Review Archive

Only `company-os-phase-4-correction-delta.zip` is produced for this correction.
It contains these 20 repository-relative paths, including `CORRECTION_FILE_LIST.txt`.
Unchanged source, prior ZIPs, secrets, dependencies, caches, builds and local database
files are excluded. SHA-256 is reported separately to avoid archive self-reference.
The baseline is `company-os-phase-4-review-final.zip`, SHA-256
`20932d6dea8b85f49045d7e5ae4aae34410aea4f54b18e9c6d0ca8ffc2846ec2`.

- `CORRECTION_FILE_LIST.txt`
- `apps/api/runtime.py`
- `apps/console/components/runtime.tsx`
- `database/migrations/manifest.json`
- `database/migrations/versions/0012_phase4_review_fixes.py`
- `docs/adr/021-fake-runtime-boundaries.md`
- `docs/phases/phase-4-handoff.md`
- `docs/phases/phase-4-manifest.json`
- `packages/company_os/application/runtime.py`
- `packages/company_os/application/scheduler.py`
- `packages/company_os/persistence/database.py`
- `packages/company_os/reporting/runtime.py`
- `packages/company_os/runtime_contracts.py`
- `packages/company_os/workflow/runtime.py`
- `packages/contracts/api.d.ts`
- `packages/contracts/openapi.json`
- `scripts/phase4-demo.mjs`
- `tests/conftest.py`
- `tests/contract/test_contracts.py`
- `tests/integration/test_phase4_review_fixes.py`

# Historical Phase 4 Handoff — Superseded by the Correction Gate Above

The following previous report is preserved as historical evidence. Its current-status and migration-head statements refer to that earlier source revision.

# PHASE 4 HANDOFF

## Gate Status

**PASS — implementation gates passed; awaiting independent review.**

On 18 September 2026, every requested final-source command completed successfully
with the required Windows process/temp and outbound HTTPS permissions. No application,
test, migration, CI, dependency or runtime change was made. Only this handoff and the
manifest were updated after verification. This is not independent acceptance.
Nouman remains the acceptance reviewer; no commit, push, PR, merge, deployment or
Phase 5 work is authorized.

### Previous gate — superseded by the final-source rerun

The following 17 September report is retained as historical evidence. Its environment
blockers were resolved by the explicitly authorized elevated verification on 18 September.

**FAIL — PHASE 4 NOT READY.** Implementation and local evidence are supplied for
independent technical review, not acceptance. The final complete check/build/browser
gate has not passed on the final source, and the Python online dependency audit is
blocked. Earlier successful gates are explicitly distinguished below. No security
assertion was removed or weakened to produce a pass. Nouman remains the acceptance
reviewer. No commit, push, PR, merge, deployment or Phase 5 work is authorized.

## Git

- Branch: `phase-4-events-jobs-health`, created from fetched `origin/main`.
- Accepted Phase 3 baseline, local `main`, `origin/main`, and branch HEAD:
  `e8c896a8fd7669472d9488b83840526ce847ce20`.
- Implementation is uncommitted and unstaged. Main is unchanged.
- The four existing Phase 2/3 review and correction ZIPs remain in place, untracked.
- Exact changed paths and source hashes are in `phase-4-manifest.json`; the path
  inventory is also appended below. Archive creation reads implementation files
  and verifies that their bytes remain unchanged.

## Objective

PostgreSQL now represents immutable synthetic inputs and events, transactional
outbox/consumer receipts, finite workflows, durable jobs and attempts, schedules,
fake effect intent and uncertainty, cost reservations, callback receipts, incidents
and runtime health. API and worker call shared application commands. The console
shows health, jobs/dead letters, attempt history, event trace, effects and incidents.

## Requirements Implemented

These are Phase 4 subsets, not claims to satisfy future provider/AI/approval clauses.

| Canonical IDs | Implementation / evidence |
|---|---|
| DATA-050; EVT-001/002/027/029/030/035/038/039 | Envelope, explicit registry, typed payload guard, outbox, receipts, separate replay namespace; atomic rollback/dedupe tests |
| DATA-051; OPS-013/014/015 | Finite workflows, SKIP LOCKED claims, leases/fences, append attempts, bounded retries, waits, dependencies, cancellation, controlled recovery; process-exit tests |
| DATA-052; OPS-016; TEST-004/007 | Fake endpoint, logical effect key/hash, intent before dispatch, uncertainty and read-only reconciliation; no resend |
| DATA-053; OPS-017; TEST-009 | Decimal workspace/company caps, reservations, single settlement, usage and quotas; 50 contenders for cap ten |
| DATA-057; OPS-018/019; UI-015 | Runtime audit references, heartbeat/queue/budget/reconciliation health, incidents and founder visibility |
| API-051–053/059–063 | Workspace job/event/health/attention APIs, versioned technical controls, fake completion receipt boundary |
| SYS-001/002/007/014/019/022/024; SEC-001/003/008/009 | Shared command boundary, tenant context, role separation, no browser DB access; Phase 2/3 controls retained |
| TEST-012/013/014/018/019/027/029/031 | Fault, atomicity, fake webhook, tenancy, phase containment, capacity and drift evidence; limitations below |

## Architecture Decisions

ADR-021 is a proposal awaiting independent review. It documents a strictly fake
endpoint registry in place of future provider connections; null future approval/
policy references; fixed `phase-4-fake-v1` authority/rate metadata; immutable attempt
start/finish records; a synthetic remote ledger; minimal workspace discovery;
encrypted callbacks; cap links; and event schema evolution. It grants no business
approval authority. Accepted architecture remains the governing design.

## Database

One Alembic history; current head `0011_runtime_event_payloads`.

| Revision | Purpose |
|---|---|
| 0006_durable_runtime | Tenant runtime tables, composite foreign keys, RLS, grants, typed actor/dependency guards and narrow service context helpers |
| 0007_runtime_integrity | Event registry/aggregate validation, effect quota reference, restricted company cap configuration/helper |
| 0008_runtime_actor_guard | Correct polymorphic trigger field access for immutable records |
| 0009_runtime_callbacks | Fenced completion receipts and runtime audit links |
| 0010_runtime_budget_caps | Additional cap links attached to one logical reservation |
| 0011_runtime_event_payloads | Named schema-v2 payloads while retaining immutable v1 history |

Previously applied revisions, including 0001–0005 and earlier revisions applied
during this work, were not edited. Corrective changes use new revisions. Normalized
LF SHA-256 values are in `database/migrations/manifest.json` and the phase manifest.
No application startup schema creation exists.

Tenant tables: `fake_endpoints`, `runtime_inputs`, `workflow_runs`, `events`,
`outbox`, `consumer_receipts`, `jobs`, `job_attempts`, `job_dependencies`,
`schedules`, `schedule_slots`, `external_effects`, `budgets`, `budget_reservations`,
`usage_entries`, `quota_buckets`, `fake_receipts`, `webhook_inbox`,
`fake_observations`, `runtime_heartbeats`, `incidents`, `incident_evidence`,
`runtime_attention`, `runtime_completions`, `reservation_budget_caps`.
`company_runtime_caps` is restricted global synthetic configuration.

All new tenant tables enforce FORCE RLS. Composite tenant foreign keys prevent
cross-workspace links; unique constraints cover logical input/effect/job keys,
consumer identity, attempt phase, schedule slot, receipt and settlement. Checks
bound states, payloads, versions, fake-only adapter/action types and cost counters.
Claim/outbox/due/trace foreign-key indexes support bounded access. Runtime roles
have no DELETE or ownership rights. Immutable records reject UPDATE/DELETE.

The disposable PostgreSQL fixture exercises Phase 3→head→Phase 3→head, rollback to
Phase 2, base rollback, clean upgrade and repeated upgrade. Foundation rows are
checked across rollback. This proves schema round trips; it is not a backup/restore
test of populated Phase 4 operational history. Downgrade intentionally drops Phase 4
runtime data; rollback details below include separately seeded membership cleanup.

## Event Runtime

Events carry workspace, aggregate/version, schema/type, local occurrence/receipt
times, actor, correlation/causation, origin, classification, bounded payload/reference
and trace ID. Database triggers validate typed aggregate identity/version and
registered payload shape. New rows use schema v2; old v1 rows remain immutable.
Commands commit state, audit, event and outbox together. Consumer receipts and job
creation commit together under an event lock. Receipt identity is stable across code
versions. Delivery is at least once; distributed exactly-once is not claimed.
Explicit replay names a separate namespace and cannot prepare an effect.

## Webhook Inbox

**FAKE PHASE 4 TEST AUTHENTICATION — NOT A PROVIDER GUARANTEE.**

Local/test HMAC covers delivery timestamp plus exact bytes. Requests over 16 KiB,
invalid signatures and delivery timestamps outside five minutes are rejected.
Endpoint lookup supplies the service principal, workspace and epoch; payload
workspace cannot select authority. Raw bytes are encrypted, hash-addressed in the
receipt metadata and assigned 30-day expiry metadata before a success response.
Duplicate keys require the same hash. Unknown mapping/schema quarantines; older
ordinary observations cannot reverse a protective stopped state. Delayed authentic
provider occurrence timestamps are retained independently of delivery freshness.
The completion endpoint is a separate closed, fenced, matching-result receipt;
it cannot directly resolve effects or assign arbitrary job states.

## Job Runtime

States are queued, leased, running, retry_wait, waiting_approval, waiting_external,
cancel_requested, succeeded, dead_letter and cancelled. Claims honor readiness,
deadline, dependency conditions, cancellation and priority under SKIP LOCKED.
Each claim increments the fence. Mutations check current owner, state, fence and
database-clock lease expiry. Leases are 60 seconds; a separate scoped transaction
renews every 15 seconds. Handler processes use two connections at most: command
and lease renewal. Durable waits release leases and worker slots.

Attempt start/finish rows are append-only and retain errors, fence, worker and
effect/reservation references. Retries preserve history, use at most three ordinary
attempts and jittered 5–30 then 30–120 second delays, and respect deadlines. Reconcile
jobs use at most ten attempts. Invalid requests and effect ambiguity do not enter
ordinary retry. Failed jobs create deduplicated incident/attention records.
Manual recovery creates a new linked job, requires current version, role, reason
and changed-cause assertion, and rejects permanent fixtures and any effect-bearing
job. It does not erase or reset the original history.

Dependencies support succeeded/terminal conditions and reject cycles. Workflow state
is recomputed after completion, cancellation, deadline failure and reconciliation.
Cancellation before dispatch releases proven-unused resources; dispatched ambiguity
retains reservations and reconciliation. Dispatch rechecks the fence, cancellation,
deadline and endpoint immediately before the fake call.

## Scheduler

The worker performs a scheduler pass every 15 seconds independently of the browser.
Database UTC determines due work. Daily HH:MM schedules use explicit IANA zones;
DST gaps skip and repeated wall times use the first fold. A workspace advisory lock
coordinates emitters; unique schedule/slot keys remain the final duplicate guard.
`skip` and `one_catchup` bound missed-run behavior; a pass examines at most 50 due
schedules. `runtime_health_demo` is synthetic, not the future founder daily brief.

## External Effects

Fake-only effects persist prepared intent, target, logical key/hash, immutable input,
expected version, authority/rate version and budget/quota reservation before dispatch.
The fake ledger commits separately to model remote acceptance followed by response
loss. Confirmed/rejected receipts settle only once. Response loss or process exit
after dispatch produces uncertainty, retains cost/quota, opens an incident and queues
safety reconciliation. The adapter rejects a second dispatch for an existing effect.
Read-only reconciliation supports confirmed, rejected and still unknown; delayed
visibility alone cannot prove non-execution. No uncertain-to-prepared reset exists.

## Budgets / Quotas

Costs use numeric(20,8)/Decimal. Workspace fixture/day/month caps are locked in UUID
order under a company reservation lock; extra cap links share one logical reservation
and one usage entry. A narrowly scoped boolean helper checks company day/month caps
without exposing other tenants' spend. Reservations retain pessimistic maximums
through uncertainty. Settlement is idempotent and rejects conflicting actual usage.
Confirmed non-use releases exactly once. Quota consumption and retained reservations
are distinct; ordinary admission leaves ten seeded units reserved for safety.
Fake read-only safety/reconciliation itself incurs no discretionary charge.

## System Health

Threshold version `phase-4-v1`: runtime heartbeat GREEN ≤30 s, AMBER ≤60 s, then RED;
safety queue AMBER >5 s / RED >10 s; ordinary queue AMBER >60 s / RED >300 s;
dead letters and uncertain effects RED; budget AMBER at 80%, RED at exhaustion or
freeze; inbox pending/quarantine AMBER, RED after 300 s; unresolved reconciliation
AMBER, RED after 300 s. Missing runtime observations are UNKNOWN. Future integrations
remain NOT CONFIGURED. The existing API/DB readiness display is retained.

Console routes: `/system`, `/system/jobs`, `/system/jobs/[identifier]`,
`/system/events`, `/system/incidents`. Technical retry/cancel controls carry explicit
reason, version, idempotency and CSRF. Founder snooze cannot hide P0/P1 items.
Structured worker output contains sanitized handler/job/event/correlation/fence/
attempt/effect/outcome/duration data and a pseudonymous workspace identifier.
Audit rows link available event, causation, job, effect, attempt and provider receipt.

## Synthetic Demo

Prerequisites and installation remain in `docs/local-development.md`. From the
repository in an ordinary local terminal with required Windows process permissions:

```powershell
npm.cmd run dev
```

Open `http://localhost:3000`, sign in as Synthetic User A, and open System Health.
Allow one scheduler tick for heartbeats. Fake adapter UNKNOWN before any call is
expected. Use a unique logical key for each new synthetic scenario.

1. Trigger `success`; open Jobs, its detail, origin event and immutable attempt pair.
2. Trigger `transient`; observe retry_wait, then successful later attempt. Trigger
   `invalid` or `exhausted` for a permanent/exhausted dead letter with full history.
3. Retry controls require an eligible transient/lease failure, changed cause and
   reason; invalid/exhausted/effect work is intentionally not eligible.
4. Trigger `effect_lost`; inspect uncertainty, reservation and incident. After the
   fake receipt becomes visible at 30 seconds, the safety reconciler confirms it
   without another dispatch. `effect_unknown` stays held when proof is unavailable.
5. Trigger distinct `effect_success` keys until the synthetic cap is exhausted.
   Further paid fixtures wait with BUDGET_EXHAUSTED. Trigger `safety`; it still runs.
   Synthetic budget history is preserved; restarting does not refill an exhausted cap.
6. Trigger `wait` and queued work, stop with `npm.cmd run stop`, then restart with
   `npm.cmd run dev`. Queued work resumes; waits remain durable without a lease.
7. Sign out and use User B. Workspace A jobs/events/effects are inaccessible.

The following deterministic demonstrations operate in their own disposable database,
preserving the interactive demo state. PostgreSQL must be running. They cover the
duplicate-event, eligible recovery, stale-fence, authenticated callback, dependency,
crash/restart, quota/budget/safety and tenant-isolation steps that lack a console form:

```powershell
node scripts/phase4-demo.mjs events
node scripts/phase4-demo.mjs faults
node scripts/phase4-demo.mjs webhooks
node scripts/phase4-demo.mjs effects
node scripts/phase4-demo.mjs budgets
node scripts/phase4-demo.mjs schedules
node scripts/phase4-demo.mjs isolation
node scripts/phase4-demo.mjs load
# Run the complete runtime demonstration in one disposable database:
node scripts/phase4-demo.mjs all
```

All assertions remain enabled. No provider is contacted. Full acceptance still
requires the independent review and outstanding gate runs below.

## Tests

Final runtime demonstration: **26 passed, 2 dependency deprecation warnings, 112.79 s**.
The last source-only change renamed an optional local variable for mypy; no behavior
changed. Final static checks and the two fake-adapter/UTC unit tests passed after it.
Five-workspace/10-user API sample: read p95 **188 ms**, command p95 **141 ms**.
The 10,000/day-equivalent fixture executed 40 normal jobs in **0.750 s**; a separate
Workspace B safety claim completed in **0.187 s** while A's discretionary budgets
were frozen. These are bounded local samples, with the limits described below.

| Command / gate | Observed result |
|---|---|
| `git fetch origin` | Passed before branch creation; local and remote main matched accepted SHA |
| Earlier elevated `npm.cmd run check` | 172 Python tests and 2 Vitest tests passed on an earlier revision; **not final-source evidence** |
| Later full check before load-fixture fix | 185 passed, one fixture login failure; corrected by provisioning test sessions through the existing DB identity mapping boundary, without broadening JWT login |
| `$env:PYTEST_ADDOPTS='-p no:cacheprovider'; node scripts/phase4-demo.mjs all` | Final Phase 4 integration demonstration: 26 passed, 2 warnings in 112.79 s; no tests skipped |
| `npm.cmd run check` after load fix | 183 passed, one worker pipe failure, two temp-directory errors; all three were WinError 5 sandbox restrictions; 132.43 s |
| Full check with workspace `--basetemp` | Static gates passed; pytest reached 100%, then access-denied temp cleanup prevented a reliable final summary; no pass claimed |
| `python -m ruff check .`; `python -m ruff format --check .`; `python -m mypy packages/company_os apps/api apps/worker` | Final: passed; 125 Python files formatted, 40 typed source files |
| `python scripts/contracts.py --check`; `python scripts/boundaries.py` | Final: OpenAPI matches; phase/dependency/migration/secret checks passed across 189 files before adding the manifest |
| `python -m pytest -q -p no:cacheprovider tests/unit/test_runtime_contracts.py` | Final: 2 passed, 2 dependency deprecation warnings, 0.02 s |
| Frontend ESLint / `tsc --noEmit` | Passed in direct final run |
| Direct final Vitest | Blocked: fork worker `spawn EPERM`; no tests executed in that run |
| Earlier `npm.cmd run build` | Passed; 21 routes. Last console implementation matched this run |
| Final `npm.cmd run build` | Blocked: build child-process `spawn EPERM` |
| `$env:PLAYWRIGHT_CHANNEL='chrome'; node scripts/ci-services.mjs e2e` | Earlier running API, worker and production console: all 5 Phase 2/3/4 tests passed in 16.5 s; before the final backend corrections |
| `npm.cmd audit --audit-level=moderate` | Passed on retry: zero vulnerabilities |
| `.venv\Scripts\python.exe scripts/audit_python.py --online` | Not completed: earlier DNS error for api.osv.dev, final sandbox connection refused (WinError 10061); no clean-audit claim |
| `git diff --check` | Passed after removing three trailing blank lines |

Automatic approval review timed out twice before launching the requested elevated
full-check rerun; this was not a determination that the commands were unsafe.
The sandboxed alternative could execute database tests but could not launch the
Windows process-pool/build/Vitest workers or access pytest-owned temp directories.
The final full gate must be rerun in a permitted environment, without skipping tests:

```powershell
npm.cmd run db:start
npm.cmd run check
npm.cmd run build
$env:PLAYWRIGHT_CHANNEL='chrome'
node scripts/ci-services.mjs e2e
npm.cmd audit --audit-level=moderate
.\.venv\Scripts\python.exe scripts/audit_python.py --online
git diff --check
```

Corrected failures during development included a polymorphic immutable-row trigger,
nullable query parameter typing, an owner-seed workspace filter, a browser navigation
race, load-session setup, and isolation of the lease-renewal test from older ready
jobs. Their original assertions were preserved. Two dependency deprecation warnings
remain from Starlette/httpx/anyio; no test suppressions were added.

## Security

Actual company_api and company_worker roles test populated rows in every tenant
runtime table, not only empty-table policies. A cannot see or update B rows; missing
context cannot see either; global caps cannot be read by runtime roles. Cross-tenant
references and invalid context fail. Roles remain non-owner, NOSUPERUSER and
NOBYPASSRLS. Service workspace discovery returns only principal/workspace/epoch;
business payload queries require scoped transactions. No service-role key, client
database access or arbitrary URL/SQL/provider input exists. Secret/dependency/import/
migration scans are retained. Secrets stay in ignored local config, outside the ZIP.

## Phase Boundary

No real provider, AI, outbound/send path, CRM, campaign runtime, full approval engine,
n8n Cloud, production provisioning/deployment or Phase 5 implementation. Fake
authentication is not a claim about any vendor's contract. System administration
does not grant business approval authority. No commit/push/PR/merge was performed.

## Known Limitations and Risks

- **Blocking:** final full suite/build/browser verification and the Python dependency
  audit are incomplete for the delivered source. Independent review must not infer PASS.
- Performance measurements are local synthetic samples, not production capacity:
  10 concurrent API samples and 40 executions from a 10,000/day-equivalent arrival
  fixture. Safety is measured alongside four shared-boundary execution threads;
  this does not substitute for sustained saturation of the deployed process pools.
  Five-workspace data/API tests do not prove five-workspace worker fairness under
  continuous load. Scheduler throughput is bounded by implementation, not separately
  benchmarked. Round-robin selection is simple and needs sustained-load review.
- Fake pagination/empty pages/expired cursor/rate limit/Retry-After are adapter
  contract fixtures, not a durable paginated provider-sync implementation. There is
  no real provider synchronization, drift repair or external monitoring/alert route.
- All current handlers are bounded local operations. The timeout field is represented;
  arbitrary long/blocking handler termination is not implemented. New long handlers
  must not be admitted without enforcing that timeout and validating cancellation.
- Seeded company caps and quota windows do not automatically roll forward. Missing
  or expired configuration blocks paid fake work. Frozen/budget-held jobs do not
  automatically resume on cap changes. This is a bounded demo, not funded operations.
- Raw callback expiry metadata exists; a retention deletion executor and key rotation
  are not implemented. The development encryption key derives from the fake HMAC
  secret; production credential custody is not represented.
- Technical retry records a user assertion and reason hash; it is not an independently
  verified change-management approval. Permanent/uncertain work remains ineligible.
  The console exposes bounded recent lists (200 rows), not complete historical paging.
- Global budget reservation serialization is intentionally conservative and may
  become a contention point. Migration/RLS/locking and effect-state races warrant
  code-level review even when a focused test passes. Company cap configuration is
  owner-seeded, not a general budget governance interface.
- Recovery fixtures exit child processes at six controlled boundaries and advance
  expired lease timestamps in the disposable DB. They are not OS power-loss/storage
  durability certification. Delayed receipt tests adjust only the disposable fake
  ledger's visibility timestamp under the test owner, never production data.

## Rollback

Rollback is documented, not executed on the interactive demo database. Preserve any
wanted synthetic DB state and the uncommitted source/archive first. Stop all services.
With this Phase 4 checkout, downgrade to the accepted Phase 3 schema:

```powershell
npm.cmd run stop
npm.cmd run db:start
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv(); from alembic.config import Config; from alembic import command; command.downgrade(Config('alembic.ini'), '0005_phase3_review_fixes')"
```

This removes Phase 4 tables, functions, grants and added audit foreign-key columns,
and deletes Phase 4 runtime history. Existing Phase 3 business tables are retained.
The seed's foundation membership/capability additions are separate from migrations.
For exact synthetic fixture recovery, remove only those Phase 4 additions with the
owner connection after the downgrade (never use a runtime role for this operation):

```powershell
@'
from dotenv import load_dotenv
load_dotenv('.env')
import os
from sqlalchemy import create_engine, text
from database.seeds.synthetic import key
with create_engine(os.environ['MIGRATION_DATABASE_URL'], hide_parameters=True).begin() as c:
    for letter in ('a','b'):
        c.execute(text('DELETE FROM app.memberships WHERE id=:id AND principal_id=:p AND workspace_id=:w'), {'id':key('runtime-member-'+letter),'p':key('worker'),'w':key('workspace-'+letter)})
    c.execute(text("UPDATE app.service_identities SET capability_profile='heartbeat-only',record_version=record_version+1 WHERE name='foundation-worker' AND capability_profile='phase-4-fake-runtime'"))
'@ | .\.venv\Scripts\python.exe -
```

Restore code from a separate clean checkout of baseline
`e8c896a8fd7669472d9488b83840526ce847ce20`, preserving this uncommitted tree. Do not
run Phase 4 code against the Phase 3 database; readiness rejects a revision mismatch.
Do not delete historical audit metadata to simulate a never-upgraded database.
To reapply this source: `npm.cmd run migrate`, then `npm.cmd run seed`. A full base
rollback is only for the disposable test database. No rollback commit is created.

## Review Archive

`company-os-phase-4-review-final.zip` contains complete repository source plus
`REPOSITORY_TREE.txt`, this handoff and the manifest. It excludes Git metadata,
environment secrets, dependencies, build/cache/test media, local PostgreSQL and
all previous ZIPs. The manifest omits its own hash; the delivered ZIP SHA-256 covers
it. The ZIP hash is reported separately to avoid a self-referential artifact.

## Phase 5 Readiness

**NOT READY.** Phase 4 has not passed its final gate or independent review. Phase 5
requires explicit separate authorization. Stop here.

## Exact Changed Paths

<!-- GENERATED_PATHS -->

- `.env.example`
- `AGENTS.md`
- `README.md`
- `apps/api/main.py`
- `apps/api/runtime.py`
- `apps/console/app/system/command/route.ts`
- `apps/console/app/system/events/page.tsx`
- `apps/console/app/system/incidents/page.tsx`
- `apps/console/app/system/jobs/[identifier]/page.tsx`
- `apps/console/app/system/jobs/page.tsx`
- `apps/console/app/system/page.tsx`
- `apps/console/components/runtime.tsx`
- `apps/console/components/shell.tsx`
- `apps/worker/main.py`
- `database/migrations/manifest.json`
- `database/migrations/versions/0006_durable_runtime.py`
- `database/migrations/versions/0007_runtime_integrity.py`
- `database/migrations/versions/0008_runtime_actor_guard.py`
- `database/migrations/versions/0009_runtime_callbacks.py`
- `database/migrations/versions/0010_runtime_budget_caps.py`
- `database/migrations/versions/0011_runtime_event_payloads.py`
- `database/seeds/runtime.py`
- `database/seeds/synthetic.py`
- `docs/adr/021-fake-runtime-boundaries.md`
- `docs/phases/phase-4-brief.md`
- `docs/phases/phase-4-handoff.md`
- `docs/phases/phase-4-manifest.json`
- `packages/company_os/adapters/fake_effects.py`
- `packages/company_os/application/runtime.py`
- `packages/company_os/application/scheduler.py`
- `packages/company_os/application/webhooks.py`
- `packages/company_os/config.py`
- `packages/company_os/persistence/database.py`
- `packages/company_os/persistence/runtime.py`
- `packages/company_os/reporting/runtime.py`
- `packages/company_os/runtime_contracts.py`
- `packages/company_os/workflow/README.md`
- `packages/company_os/workflow/__init__.py`
- `packages/company_os/workflow/runtime.py`
- `packages/contracts/api.d.ts`
- `packages/contracts/openapi.json`
- `scripts/boundaries.py`
- `scripts/ci-services.mjs`
- `scripts/local.mjs`
- `scripts/phase4-demo.mjs`
- `tests/conftest.py`
- `tests/contract/test_contracts.py`
- `tests/e2e/runtime.spec.ts`
- `tests/integration/test_runtime.py`
- `tests/integration/test_tenancy.py`
- `tests/phase4_scope.py`
- `tests/unit/test_core_boundaries.py`
- `tests/unit/test_runtime_contracts.py`
