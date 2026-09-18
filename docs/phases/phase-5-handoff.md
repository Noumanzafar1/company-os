# PHASE 5 CORRECTION HANDOFF

## Phase 5 Correction Gate

Independent review of the original Phase 5 submission: **PASS WITH FIXES**.
The architecture was accepted in principle. This handoff covers only the five
authorized corrections. Final gate results are recorded below; Nouman remains
the repository owner and acceptance reviewer. Stop at independent review.

## Fix 1 — Exact Policy Activation Authority

API-064, SEC-006/007 and DATA-045/046/047: `POST /policies/propose` freezes an
immutable candidate before approval, evaluates the active typed `policy.activate`
policy and records the existing approval request. The founder reviews the exact
candidate through the existing decision command with fresh verified MFA.

The immutable manifest binds policy ID, current record version, old active
pointer (including disabled/null), candidate ID and version number, content hash,
exact typed rules, action, effective/expiry windows, workspace, approver, approval
expiry and one activation use. Candidate rules and hashes cannot be updated.
Policy pointer/version drift, expiry or revocation blocks activation.

`POST /policies/activate` accepts only exact candidate, decision and manifest IDs
with If-Match. It reserves one shared authority use, updates the policy pointer,
records its consumed outcome and emits `policy.activated` with linked audit in
the same transaction. The proposal's correlation/hash joins its policy evaluation;
request → human decision → manifest → use → pointer/result → event/audit completes
the chain. Same idempotency key returns the original receipt without another use.
An altered candidate/decision or new replay cannot consume that grant again.

Fresh MFA alone cannot update the pointer. Service identities and system-only
administrators cannot activate. The protective disable path never grants a
replacement policy. Successful activation still invalidates prior execution
grants; the existing regression assertion remains intact. The console shows the
exact candidate and provides the distinct approved activation command.

## Fix 2 — Final Temporal Authority Check

Migration 0018 wraps the unchanged prior full validator. It retains all checks
and locks, then reads `clock_timestamp()` again after target/version/rights work.
The final check covers manifest starts/expiry, governing policy effective/expiry,
current active pointer and request state. Policy activation additionally checks
the candidate's material validity bounds.

The worker calls the lightweight temporal check after full validation, budget
validation and other dispatch checks immediately before fake acceptance. It does
not rescan the target cohort merely to check time. SQL final triggers independently
guard use reservation after accounting, dispatch transition and fake receipt
insertion. Existing gate and row locks remain held.

Deterministic PostgreSQL tests observe a validator actually blocked by a target
row lock before expiry, hold that lock until the database clock reaches manifest
or policy expiry, and require EXPIRED/POLICY_CHANGED after release. A test-only
advisory barrier after bounded-use accounting proves that the final use trigger
rejects an expired reservation. No use/effect survives the failed reservation.
Direct fake acceptance after expiry cannot create a receipt. Existing exact
expiry/no-grace and valid execution tests remain.

## Fix 3 — Approval Read Authorization

API-048/049: founder can read workspace approvals; every other human business
user is filtered by `created_by = authenticated principal`. Detail checks this
before reading manifest/history/uses and returns the existing safe 404. Principal
and roles are server-derived. Same-workspace invited human fixtures prove own
read, non-enumeration and another requester's denial. Cross-workspace, service
identity and system administrator denials remain. Worker validation RLS is intact.

## Fix 4 — Multi-Role Evaluation

Evaluation uses `frozenset[str]` containing every authenticated current role.
Intersection with permitted roles determines authorization. Tests cover both
role orders, permitted researcher among multiple roles, no permitted intersection,
single-role behavior and the API passing the complete server-derived set.

## Fix 5 — Review Artifact Hygiene

The untracked root REPOSITORY_TREE.txt was moved to ignored `.local/review-staging`.
It is absent from implementation changed paths/source hashes and from the
correction delta. The original full review ZIP retains its useful tree and remains
byte-identical. No new full review ZIP was generated.

The historical root CORRECTION_FILE_LIST.txt already exists on protected main
(blob `a988091d0f6b5529d821aa337651ac3a9852b919`); it remains unchanged and is not
part of this implementation change. The new correction list is generated only
as an archive member, with the correction-specific paths and SHA-256 values.

## Migration

Single linear Alembic history; corrected head: `0018_phase5_review_fixes`.
Migrations 0001–0017 are byte-identical to the correction baseline and their
normalized hashes remain unchanged. 0018 adds typed policy-candidate references
to requests and a constrained policy-activation variant to the existing use row.
There is no second approval subsystem and no new runtime role or dependency.

The existing NOLOGIN `company_auth` receives only scoped policy-lock and canonical
hash permissions needed by fixed-path validators; FORCE RLS remains enabled.
API and worker remain non-owner, NOSUPERUSER and NOBYPASSRLS. Workers receive no
policy/grant mutation capability. Startup performs no schema creation.

The persistent local synthetic database was upgraded to 0018. The initial
`policy.activate` governance fixtures were seeded through the existing offline
setup boundary. Before/after assertions verified every existing policy pointer
and record version, all workspace budgets and company caps remained unchanged.
The exhausted demo budgets and existing authority history were preserved.

The suite upgrades accepted Phase 4 head → corrected head, downgrades to Phase 4,
re-upgrades, and repeats the existing Phase 3, Phase 2 and base round trips plus
repeat head upgrade. Empty/pre-activation downgrade restores the frozen prior
function definitions. If policy activation history exists, 0018 downgrade fails
closed: preserve its audit/history and restore a matching backup with the matching
prior application/schema after stopping/draining work. Do not discard activation
evidence to force a rollback. Original Phase 5 preexisting runtime history has the
same original matched-backup/drained-outbox rollback constraints.

## Changed Files

`phase-5-manifest.json` contains the full future Phase 5 implementation change
set plus the smaller correction-cycle set and exact source hashes. The correction
ZIP contains only files changed since the preserved original review baseline.

<!-- CORRECTION_PATHS_START -->

- `apps/api/authority.py`
- `apps/console/app/approvals/command/route.ts`
- `apps/console/components/approvals.tsx`
- `database/migrations/manifest.json`
- `database/migrations/versions/0018_phase5_review_fixes.py`
- `docs/adr/022-exact-synthetic-authority.md`
- `docs/phases/phase-5-handoff.md`
- `docs/phases/phase-5-manifest.json`
- `packages/company_os/application/authority.py`
- `packages/company_os/application/policy_activation.py`
- `packages/company_os/application/runtime.py`
- `packages/company_os/persistence/database.py`
- `packages/company_os/policy/engine.py`
- `packages/company_os/policy_contracts.py`
- `packages/company_os/workflow/runtime.py`
- `packages/contracts/api.d.ts`
- `packages/contracts/openapi.json`
- `tests/contract/test_contracts.py`
- `tests/integration/test_authority_controls.py`
- `tests/integration/test_phase5_review.py`
- `tests/phase5_scope.py`
- `tests/unit/test_policy_engine.py`

<!-- CORRECTION_PATHS_END -->

Requirements: API-048/049/064; SEC-001/003/004/006/007/008;
DATA-045/046/047/052/053/057; SYS-002/006/014/019/025;
TEST-001/002/005/006/007/009/018/028/030. These are bounded synthetic Phase 5
slices; no future provider, commercial, campaign or production requirement is
claimed complete. Prior Phase 2–4 assertions remain.

## Full Regression Results

| Gate | Final-source result |
|---|---|
| `npm.cmd run db:start` | PASS; local PostgreSQL and restricted runtime roles ready |
| `npm.cmd run check` | PASS; 267 Python tests, 2 upstream deprecation warnings, 265.91s; 2 frontend tests; zero skips |
| Included check stages | OpenAPI/TypeScript snapshot, Ruff lint/format, mypy (46 sources), phase/dependency/secret/migration checks, all integration/security tests and migration round trips, ESLint, TypeScript, Vitest |
| Focused authority/adversarial/concurrency rerun | PASS; 48 tests, 2 upstream warnings, 197.66s; zero skips |
| Final fixture/isolation confirmation | PASS; 4 tests, 2 upstream warnings, 46.35s; zero skips |
| `npm.cmd run build` | PASS; Next.js 16.3.5; 19 generated pages |
| Chrome canonical browser gate | PASS; 6 tests; zero failures, skips or flaky tests; 40.268s |
| `npm.cmd audit --audit-level=moderate` | PASS; 0 vulnerabilities |
| `python scripts/audit_python.py --online` | PASS; 49 packages; OSV/PyPI findings empty; 2026-09-18T09:59:24.979028+00:00 |
| `git diff --check` | PASS |

Browser command: `$env:PLAYWRIGHT_CHANNEL='chrome'; node .local/e2e-run.mjs`.
That local wrapper invokes `node scripts/ci-services.mjs e2e` after provisioning
a new synthetic database at corrected head, then drops only that database.

No safety assertion was skipped, weakened or deleted. The existing policy
invalidation test now obtains a real exact grant and keeps its POLICY_CHANGED
assertion. The two upstream test-client deprecation warnings are reported,
not suppressed. Focused development initially exposed an additional-human
fixture sign-in restriction; it was corrected using the existing offline signed
identity pattern without extending the runtime development allowlist.
The new disabled-policy test exposed an omitted disabled row in policy readback;
the read now includes it with typed nullable active-version fields. The final
acceptance fixture now pauses specifically after dispatch, and added human
memberships clean up after the test. Original isolation assertions remain intact.

Browser tests use the canonical `scripts/ci-services.mjs e2e` runner against
running API, worker and built console in Chrome. The ignored local wrapper
provisions and removes a disposable synthetic database: the persistent demo DB
has exhausted budgets from previous exercises. Its budget caps/history are not
reset or bypassed to obtain a pass.

## Performance

The preserved original measurement is approximately **1.66 seconds per 200-target
validation** (100 warm calls, 1,659.417 ms mean). This remains tuning debt before
high-volume/network authority execution. The correction adds a bounded final
temporal read; it does not add a second 200-target scan for that read. The existing
50-contender/10-use and 200-target regressions are retained. Final focused rerun
measured 853.235 ms mean over 100 warm 200-target validations. Concurrent local gates can affect this measurement. Final focused rerun measured 853.235 ms mean over 100 warm 200-target
validations. Concurrent local gates can affect this measurement. Local synthetic
measurements are not a production throughput or remote-provider guarantee.

## Security

Synthetic data and offline fake adapters only. Exact hash/reference binding,
workspace gates, current role/assurance checks, tenant-local context, FORCE RLS,
optimistic versions, idempotency, separate budget/use controls, sole effect owner,
unknown-outcome accounting and reconciliation remain. A service session cannot
enter human review. No new service-role key, secret, provider dependency or client
database access was introduced. Original immutable migrations remain frozen.

## Git

Branch remains `phase-5-policy-approvals-founder-control`.
HEAD, main and origin/main remain `bf12861bc9b711a3669ba62c2ab56596035b5d0e`.
Main unchanged. No commit. No push. No PR. No merge. Index unchanged and no
implementation changes staged. Earlier review archives remain preserved.

## Phase Boundary

No OpenAI, Anthropic, model gateway, AI worker, Apollo, Smartlead, ZeroBounce,
Pipedrive, Google integration, n8n Cloud, real outbound, campaign execution,
payments, contracts or production deployment. **Phase 6 has NOT begun.**
Only the five authorized independent-review corrections were implemented.

## Known Remaining Debt

- Tune 200-target validation before high-volume/network authority execution.
- ADR-021 long-handler timeout debt remains a **HARD prerequisite** before any
  Phase 6 real model/network workload; it was not expanded or solved here.
- Fake synthetic evidence does not establish real-provider idempotency, remote
  timeout, delivery, rights, suppression or production capacity guarantees.
- Existing upstream test-client deprecations remain non-blocking technical debt.

## Phase 6 Readiness

Not authorized and not started. This correction ends at Nouman's independent
review gate. Acceptance does not authorize commit, push, PR, merge or Phase 6.
