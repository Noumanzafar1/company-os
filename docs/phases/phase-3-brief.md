# Phase 3 — Core business state

Implementation authority: Nouman's supplied Phase 3 implementation request,
17 September 2026, and the numbered specification. The request supersedes the
Phase 2-only authorization wording in AGENTS.md and the historical handoff.
The Phase 1 design status and the accepted Phase 2 evidence remain historical.

Baseline: `8e8de67447d6283bd51c412487af90ddf5eb7cf3`. A successful fetch verified
local main and origin/main at that exact commit. Implementation branch:
`phase-3-core-business-state`. No commit, push, PR, production deployment or
Phase 4 work is authorized. Reviewer and acceptance owner: Nouman.

## Schema map before migrations

This map records the intended implementation, not completed work or acceptance.

| Requirement | Implement in Phase 3 | Deliberately deferred and reason |
|---|---|---|
| DATA-007 | Closed typed resource registry, composite tenant FKs and deferred matching-child validation | Future aggregate types until their phase |
| DATA-009–012 | Account, Person, Employment, ContactPoint and explicit identity conflict records | Provider discovery, contact verification and outbound eligibility |
| DATA-013 | Synthetic source metadata, purposes, fields, rights evidence, expiry and retention constraints | Live connections and generalized source approval/policy engine |
| DATA-014–016 | Append-only Evidence/retractions; observed Signal records; current-support queries | Invalidation events, workers and scheduled expiry sweeps (Phase 4) |
| DATA-017–018 | Immutable draft ICP/Offer versions, closed criteria/rubric, proof joins | Activation/approval commands; roadmap explicitly says draft-only definitions |
| DATA-019 | Lead identity and permitted synchronous Phase 3 transitions | Research jobs, eligibility, engagement and sales qualification |
| DATA-020/026 | Immutable deterministic score history, typed components, evidence joins, reproducible hashes | Production qualification and AI inference |
| DATA-022–023 | Workspace-local deny/unknown permission and suppression structural support | Eligible permission assessment, releases, global matching and outbound enforcement (Phase 5/8) |
| DATA-025/058 | Reviewed same-workspace merge, before-state snapshot and compensating reversal | Privacy workflow execution, erasure automation and restore exports |
| DATA-055–056 | Fake document catalogue/version metadata, workspace grants, knowledge metadata and PostgreSQL full-text chunks | Drive/OAuth, cross-workspace shares, AI context packs and vector search |
| API-001 / DATA-057 | Synchronous command idempotency receipts and atomic audit using foundation boundaries | Outbox, event delivery, jobs, leases, fences and effects |

All reference arrays requiring integrity become join tables. Business facts stay
in typed tables. All new tenant tables require FORCE RLS, actual-runtime-role
tests and composite FKs. Runtime workers remain connectivity-only. Applied
Phase 2 migrations must remain byte-for-byte unchanged after newline normalization.

## Contracts and acceptance

Reconcile API-004–006,009/010,012/013,017–020,054/056. Explicit synchronous
definition creation/version commands must be documented before implementation;
they cannot activate versions. Account/lead/evidence/source review surfaces
must explain missingness, rights and historical versus current support.

DATA-026 weights remain fit 30, economics 20, trigger 20, role 15, freshness 15.
The binary synthetic rubric tests arithmetic, not predicted sales performance.
Missing required support produces null, never positive points or renormalization.
Hard exclusions override numeric priority. Source expiry, revocation, evidence
expiry and retraction are checked synchronously on use.

The synthetic A/B set must contain at least 20 business records and exercise
shared domains, parent/subsidiary relationships, uncertain employment, duplicate
names, exclusions, missingness, retractions, expired rights and stale knowledge.

Preserve all Phase 2 regression controls. Required gates include canonical lint,
format/type checks, contracts, migration integrity, PostgreSQL integration and
security tests, frontend checks/build, browser E2E and dependency/security scan.
Record exact results, limitations, paths, hashes and rollback in the Phase 3
handoff/manifest, then create the source-only review bundle. Nothing in this
brief claims those gates have run or passed.

### Narrow additional command contracts

`POST /icps`, `/icps/{id}/versions`, `/offers`, `/offers/{id}/versions`
create draft definitions only. Version commands require the parent's expected
version and leave active pointers null. `POST /employments` records evidenced
history. Read-only `GET /icp-versions/{id}` and `/offer-versions/{id}` expose
the exact immutable definitions for lead inspection. `POST /signals/{id}/accept` records review of current observed support.
`POST /leads/{id}/begin-research` and `/complete-research` use the canonical
discovered→researching→researched states synchronously for local/manual research:
there is no job claim, provider cost, or scheduler. Completion requires every
required field to have current evidence or an explicitly unknown value.
`POST /leads/{id}/disqualify` requires a current hard-exclusion score;
`/archive` records local closure. Reassessment, eligibility, engagement,
qualification and activation remain deferred. No generic state setter exists.

## Human identity review preflight

The accepted Phase 2 synthetic login deliberately cannot assert MFA. SEC-008
requires MFA for privileged human actions. The implementation must not weaken
that guard to demonstrate merges. Nouman explicitly approved an offline test-only
verified-MFA identity fixture for the merge/reversal demo in this task. Normal
synthetic login remains unable to perform those privileged commands. That
approval authorizes the test mechanism, not any production authority exception.
Do not imply that a fixture establishes real human/provider authentication.
