# PHASE 6B CORRECTION HANDOFF

## Correction Gate

BOUNDED CORE CORRECTIONS COMPLETE — independent-review handoff. Architecture was
accepted in principle with fixes. All four requested corrections are implemented;
no live-provider or publication authority is inferred. Canonical Phase 1 design
status and the accepted Phase 4/5/6A runtime, authority and containment remain.

## Fix 1 — Evaluation Freshness Through Promotion

Finalization revalidates every immutable batch run against its ContextPack and
current dependencies. A stale sample retains its denominator and class count,
contributes no valid accepted output, and records STALE_EVALUATION_CONTEXT.
Staleness in either candidate or current cohort forces technical_fail. Prior
results/evaluations are never rewritten or deleted.

The durable manifest is the existing immutable evaluation.batch_id → batch ordered
run IDs → immutable run context_id/task identity → immutable ContextPack, which
contains source/evidence version, content hash and document permission epoch.
The database verifies both cohorts against the frozen dataset cases and route IDs.
No extra table or full-context copy was introduced.

Proposal and final promotion call the scoped freshness helper and return typed
EVALUATION_STALE on stale dependencies. It checks workspace/authz epoch, requester
and service membership/expiry, source approval/rights/expiry/observed time, evidence
version/identity, document permission epoch, ContextPack expiry/hash, current policy,
route state/hash, prompt/schema/price hashes, price expiry and enabled fake provider.
Completed evaluations use ContextPack expiry; execution deadlines remain enforced
for inference and do not independently expire already completed samples.

Additive migration 0026 extends the exact Phase 5 approval-use and route-activation
guards and adds a deferred activation freshness check. Shared dependency locks
remain held through commit. The existing workspace authority lock is acquired
first; row locks follow workspace, sorted principals, memberships, service
identities, policies, route states, sources and provider connections. Only the
existing NOLOGIN company_auth helper owner receives lock-related UPDATE privileges;
API/worker grants are unchanged. Fixed search_path, caller membership and scoped
RLS remain enforced. The helper performs no updates and returns only IDs/Booleans.

Deterministic tests observe actual PostgreSQL lock waits: committed revocation
first rejects promotion without consuming a use or changing the pointer; promotion
holding freshness locks first commits, then revocation succeeds without rewriting
activation history. Both candidate/current pre-finalization revocation, pre-proposal
revocation, post-approval application/direct-database rejection, fresh promotion,
and age/current-route/route-hash/dataset-hash guards pass. Providers are fake only.

## Fix 2 — Complete AI RLS Evidence

Both tenants are populated using explicit synthetic configuration provisioning and
actual API/worker commands for runtime records. A seed defect was corrected: the
migration owner's registry-existence query now filters the selected workspace,
so Workspace A no longer suppresses Workspace B provisioning. No RLS policy was
loosened and no runtime table privilege was expanded.

All entries below passed under actual company_api and company_worker roles
(NOSUPERUSER, NOBYPASSRLS, non-owner). Both directions return only the selected
tenant's populated rows; missing context returns zero rows; DELETE and tenant
identity mutation are denied for every table.

| Table | Populated A/B and missing-context reads | Write/reference evidence |
| --- | --- | --- |
| ai_evaluation_batches | PASS, API + worker | API create only; immutable; cross-tenant run/config input set fails closed |
| ai_registry | PASS, API + worker | API/worker insert/update/delete denied |
| ai_provider_connections | PASS, API + worker | API/worker insert/update/delete denied |
| ai_fixture_sources | PASS, API + worker | API provisioning/protective revocation; worker writes denied |
| ai_routes | PASS, API + worker | API/worker insert/update/delete denied; configuration references cannot be written |
| ai_route_states | PASS, API + worker | API exact human transition only; worker writes denied |
| context_packs | PASS, API + worker | API insert; immutable; cross-tenant source FK denied |
| agent_runs | PASS, API + worker | API insert/worker state progression; immutable identity; cross-tenant references denied |
| model_runs | PASS, API + worker | Worker bounded call/settlement only; cross-tenant run rejected by binding guard |
| ai_results | PASS, API + worker | Worker append only; cross-tenant run FK denied |
| ai_evaluations | PASS, API + worker | Worker append only; cross-tenant references denied; no update/delete |

Configuration rows and sources have no further writable runtime cross-tenant
references to exercise. Successful contained execution, settlement, evaluation and
human activation prove retained narrow write capabilities, not merely denial tests.

## Fix 3 — Anthropic Credential Isolation

Pinned anthropic 1.7.0 explicitly tests exact class identity in _is_base_client.
The explicit-only client now has a closed constructor (key, timeout, HTTP client)
and excludes profile/config/token-provider arguments. A unit regression intercepts
both default_credentials and _warn_env_shadow and proves neither is called for
this client. A positive control proves the base Anthropic client enters the warning
profile probe even with an explicit key. This is a version-specific SDK behavior,
not an unsupported general claim about empty subclasses.

Contained canary tests plant ANTHROPIC_API_KEY/AUTH_TOKEN/PROFILE, arbitrary config
and profile variables, custom headers, temporary profile/credential files and
HOME/USERPROFILE/APPDATA/XDG/ANTHROPIC_CONFIG_DIR paths. The actual child probe checks
its minimal environment (Windows SystemRoot/WINDIR; POSIX may add Python's LC_CTYPE).
Selected synthetic auth is verified at the mock HTTP header; it cannot be replaced
by parent/profile auth. No credential value appears in request body, returned result
or captured logs. The child has neither a database credential nor an audit writer.
Parent environment stripping, post-containment secret delivery and trust_env=False
remain required boundaries. No network request or real credential was used.
ADR 024 and the provider preflight now state these exact limits; SDK upgrades and
live-provider/account behavior require separate verification.

## Fix 4 — Publishing / Handoff Hygiene

REPOSITORY_TREE.txt and scripts/phase6b_review.py were moved to ignored .local review
tooling. Neither is in the future commit inventory, source hashes or correction ZIP.
The original full review archive is preserved unchanged. The stale test placeholder
in the original handoff was replaced with its recorded baseline results: 407 Python,
0 skipped, 78 focused AI, 8 Chrome, build/audits/migration passes. The final correction
results below supersede those counts. No new full-repository ZIP was generated.
The corrected manifest lists actual future Git changes; the delta contains only
this correction cycle's changed files plus archive-only CORRECTION_FILE_LIST.txt.

## Migration

Head: 0026_phase6b_review_fixes. Revisions 0001–0025 are byte-for-byte unchanged.
The existing normalized-LF migration hash manifest includes 0026. No tables or
alternate migration history were added; application startup still checks the head.
The test fixture passed empty-schema 0025 → head → 0025 → head and 0020 → head
round trips, existing earlier canonical 0018/0012/0011/0005/0002/base round trips,
and repeat head upgrades. A populated-history downgrade regression proves 0026
refuses rollback and preserves evaluation records/head. Operational rollback with
history requires a matched baseline backup; never delete history to downgrade.

## Tests

Final stable runtime/schema/test source, Windows:

- npm.cmd run db:start: PASS.
- npm.cmd run migrate: PASS, corrected head 0026.
- npm.cmd run check: PASS; 423 Python tests, zero skipped, one existing
  Starlette/AnyIO deprecation warning, 910.81 seconds; Ruff, formatting,
  mypy, contracts, boundaries, console lint/type checks and 2 Vitest tests passed.
- Focused contract/AI integration/provider/review tests: 91 passed,
  zero skipped, one same warning, 218.58 seconds. Includes revocation,
  RLS, exact route authority, injection/evidence/cost/fallback and credential canaries.
- npm.cmd run build: PASS, production Next build. Generated next-env.d.ts restored
  to intended baseline bytes afterward.
- PLAYWRIGHT_CHANNEL=chrome node scripts/ci-services.mjs e2e: PASS against a fresh
  synthetic database and running API/worker/production console; 8 passed, zero skips,
  failures, flaky tests or retries, 66.62 seconds. Existing isolated
  scripts/phase6a-e2e.mjs provisions the disposable database and invokes this command.
- npm.cmd audit --audit-level=moderate: PASS, zero vulnerabilities.
- .venv/Scripts/python.exe scripts/audit_python.py --online: PASS, 51
  PyPI packages checked via OSV, zero findings at 2026-09-19T15:09:21.346493+00:00.
- git diff --check: PASS. Applied migration integrity and correction archive checks: PASS.
- Ubuntu CI: NOT RUN; publication is not authorized. No Linux evidence is claimed.

Exact local logs are ignored under .local/phase6b-correction-*.log; the manifest
records final outcomes, immutable migration hashes and implementation source hashes.
No safety assertion was skipped, removed or weakened.

## Security

Existing Phase 4 durable commands/accounting, Phase 5 exact human authority and
Phase 6A contained process supervision remain. AITask/AIResult/ContextPack, immutable
route/prompt/schema/price config, budgets, ModelRun accounting and fake-only routing
are preserved. No model tool can reach SQL, browser, shell, computer or arbitrary URL.
Stale context cannot release an AI route; no source/evaluation history is rewritten.
The non-login helper-owner row-lock grants are documented in ADR 024; API/worker
cannot assume that role. New source and archive contents pass the existing secret
scanner. No credential, .env, dependency tree, local database, build or cache is packaged.

## Performance

Freshness adds bounded database reads/hash checks and shared dependency locks for
both frozen cohorts (seed 4, development/holdout 6, adversarial 16 runs per batch).
It adds no inference or provider calls. Row locks are transaction-local and released
at commit. Race regressions confirm contention serializes without violating history.
This cycle makes no new production throughput or live-provider latency claim.

## Changed Files

See correction_changed_paths in phase-6b-manifest.json and the archive-only
CORRECTION_FILE_LIST.txt for exact delta paths. changed_paths in the
manifest describes the full future Phase 6B implementation commit; review-only
files and previous ZIPs are excluded. The delta adds migration 0026, correction
regressions/handoff and modifies evaluation lifecycle/metrics, the head assertion,
fixture provisioning, explicit SDK client/probe/canary tests and related ADR/docs.
No dependency/model ID changes were made.

## Git

Branch remains phase-6b-ai-gateway-evaluation. Protected main and HEAD remain
41e27ff8cb211b1d3a80d702995cad2a9f28567e. No commit, push, PR, merge or deployment was performed.

## Live Provider Authorization

- authorized = false
- live spend cap = $0
- OpenAI calls = 0; Anthropic calls = 0
- real providers remain disabled/unconfigured; production routes = 0

## Phase Boundary

Phase 7 has NOT begun. No Apollo, Smartlead, ZeroBounce, Pipedrive or Google live
integration, outbound, autonomous agent loop, recursive delegation, model browser/
shell/computer tool or real business data was added. Synthetic technical evaluations
do not establish business model quality. FOUNDER_LABELLED_DATASET_REQUIRED remains.

## Remaining Gate

Stop at correction review. Live-provider preflight remains separately founder-authorized
and is NOT part of this correction. Account-specific model availability, billing,
retention, region and actual structured output must be reverified only under that
authorization. No newer model or live route was substituted.

Archive: company-os-phase-6b-correction-delta.zip. Its SHA-256 is in the detached
.zip.sha256 sidecar and final delivery, avoiding recursive archive/self hashing.
