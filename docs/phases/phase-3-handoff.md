# PHASE 3 HANDOFF

## Phase 3 Correction Gate

**PASS — all five bounded review fixes implemented and full local regression gates passed.**
Independent correction acceptance remains with Nouman. The prior independent review was
PASS WITH FIXES; this evidence does not imply acceptance or authority to commit/push.

### Changed Files — correction cycle only

Exact changes against the original Phase 3 review source, not against the Git baseline:

- `database/migrations/manifest.json`
- `database/migrations/versions/0005_phase3_review_fixes.py`
- `docs/adr/020-core-state-refinements.md`
- `docs/phases/phase-3-handoff.md`
- `docs/phases/phase-3-manifest.json`
- `packages/company_os/application/business.py`
- `packages/company_os/application/scoring.py`
- `packages/company_os/business_contracts.py`
- `packages/company_os/persistence/business.py`
- `packages/company_os/persistence/database.py`
- `packages/company_os/reporting/business.py`
- `packages/contracts/api.d.ts`
- `packages/contracts/openapi.json`
- `tests/contract/test_contracts.py`
- `tests/integration/test_identity_review.py`
- `tests/integration/test_phase3_review_fixes.py`
- `tests/phase3_scope.py`

### Fix 1 — Score Dependency Tracking

New `score_input_evidence` rows retain every submitted evidence UUID, including facts used
only by hard exclusions, contradictory facts and currently invalid inputs. New `score_signals`
rows retain exact trigger Signal UUIDs, versions, accepted status, expiry and supporting
Evidence UUIDs. Both are immutable, FORCE-RLS tenant tables with composite foreign keys,
actor/subject guards and indexes; Signal snapshots must match the referenced Signal at insertion.
No worker grants were added.

`application/scoring.py` now owns the shared read-only evaluator. Creation and current-score
validation use it, so validation recomputes the versioned input hash from the persisted
input evidence set. Hash inputs include accepted Signal dependencies, account identity/version,
immutable ICP/rubric, evidence content/current validity and source versions. Account and ICP
exclusions remain deterministic and explainable through those inputs. Evidence-derived
exclusions are covered even when they supplied no positive component points. Lead
disqualification also rejects a score whose complete input hash is no longer current.

A Signal that expires, is rejected, changes version or loses evidence support makes its
historical score non-current. Recalculation appends/reuses a different immutable result;
expired/rejected/unsupported trigger support earns no points. No event or scheduled
invalidation exists. Legacy scores have dependency_version=0 and fail closed as non-current:
their original full evidence input set cannot safely be reconstructed. They remain readable;
explicit rescoring creates version-one history without rewriting them. Existing local demo
scores therefore may initially show non-current; use the rescore action described below.

Tests in `test_phase3_review_fixes.py` verify accepted-trigger points, expiry with Evidence
still valid, rejection, retraction, changed Signal version, recalculation/reuse, preserved
historical rows/dependency snapshots, exclusion-only evidence retraction, legacy fail-closed
behavior, composite-scope rejection and immutable dependency rows. Existing score tests
remain unchanged. New tables also run through the complete actual-runtime-role RLS matrix.

### Fix 2 — Typed Contradictions

Canonical comparison includes FactValue's declared type, value and unit. Expected types
are enforced for industry/country strings, employee integers, boolean economics/trigger
facts and required problem facts. Mixed types and conflicting values become unknown; no
row-order choice can award points. Current-score evaluation uses the same logic.

Parameterized runtime regressions cover integer 1 versus string "1", boolean true versus
string "True", equivalent integer/integer and boolean/boolean observations, contradictory
integer and boolean values, and a lone invalidly typed employee count. Same-type equivalent
observations retain their points. The existing deterministic scoring assertions were preserved.

### Fix 3 — Reversal Evidence

Before a reversal decision is written, every supplied Evidence UUID is loaded under the
current tenant, must concern the survivor or retired identity, and must pass the same
current-evidence predicate used by merge. The existing identity locks, versions, snapshot,
permission and recent-MFA controls remain. Invalid requests create no reversal decision.

The existing signed offline-MFA merge/reversal test now rejects unrelated same-workspace,
expired, retracted, uncertain entity-match, rights-revoked, superseded, cross-workspace and
missing Evidence. It verifies unchanged merge history and decision counts after rejection,
then proves valid reviewed-identity evidence succeeds and contact holds/history remain.
The user-approved offline fixture remains test-only; normal synthetic login still lacks MFA.

### Fix 4 — Contact Permission Semantics

Only an email ContactPoint creates the Phase 3 email/outreach permission assessment, with
result unknown. Phone and URL identities create no email assessment. Parameterized tests
cover all three kinds, their independent identity status and the absence of fabricated
suppression records. No phone, SMS, voice, LinkedIn or other channel permission system exists.

### Fix 5 — Signal Temporal Integrity

Application validation rejects future observed_at values and observations before supporting
Evidence.observed_at. The input model checks expires_at >= observed_at; existing SQL expiry
constraints remain. A new database trigger checks observation chronology on insert/update.
The existing observed/current/matched-evidence validation remains. Future event_at is allowed.

Focused application and actual-runtime SQL regressions cover future observation, observation
before evidence and expiry before observation. A valid advance announcement succeeds and
can be accepted. Its acceptance reason is checked after a fresh database read.

### Review-only Cleanup

Removed dead `DocumentInput.purpose` from the closed contract: registration never applied
purpose-specific behavior. Its presence is now rejected (tested); source-purpose controls
are unchanged. Generated OpenAPI/TypeScript reflect this bounded correction. Clients must
omit purpose when registering a document. Signal acceptance now persists acceptance_reason
and exposes it in SignalView; legacy values remain null rather than inventing past reasoning.
Neither change creates a policy, provider or approval workflow.

### Migration

New revision: **0005_phase3_review_fixes**, parent **0004_core_integrity**. Adds two tables,
scores.dependency_version, signals.acceptance_reason and the dependency/chronology guards.
The migration manifest records its immutable SHA-256. Applied revisions 0003 and 0004,
all Phase 2 revisions, and the original Phase 3 review ZIP are byte-for-byte unchanged.

The complete suite exercised populated Phase 2 head → new Phase 3 head → downgrade to
Phase 2 (nine foundation tables and two memberships preserved) → re-upgrade → base rollback
→ re-upgrade → repeated upgrade. Local migration also upgraded the existing populated
Phase 3 demo successfully; repeat `npm.cmd run migrate` passed. Downgrading only 0005 to
0004 removes its two tables/columns/triggers, preserving score history but discarding new
support links/reasons; use the matching pre-correction code. Full Phase 3 rollback remains
documented below. No applied migration was edited.

### Full Test Results

| Exact command | Correction-cycle result |
|---|---|
| `npm.cmd run db:start` | PASS: local synthetic PostgreSQL 18.4 |
| `npm.cmd run migrate` | PASS: 0004 → 0005 on existing demo; repeated upgrade also PASS |
| `npm.cmd run contracts` | PASS: regenerated OpenAPI/TypeScript and subsequent drift check |
| `npm.cmd run check` | PASS: 159 Python tests, 0 failed, 0 skipped, 2 upstream warnings, 71.50s; 102 formatted Python files; mypy 30 source files; complete integration/security/RLS/migration/scoring/identity/contract tests; boundary/secret/dependency checks; frontend lint/types and 2 Vitest tests (465ms) |
| `npm.cmd run build` | PASS: Next.js 16.3.5 production build; 16 routes including not-found |
| `$env:PLAYWRIGHT_CHANNEL='chrome'; node scripts/ci-services.mjs e2e` | PASS: all 4 tests (2 Phase 2, 2 Phase 3), 21.4s, against running API and production console |
| `node node_modules/typescript/bin/tsc --noEmit --project apps/console/tsconfig.json` | PASS after restoring build-generated next-env.d.ts to baseline |
| `npm.cmd audit --audit-level=moderate` | PASS: 0 vulnerabilities |
| `.\.venv\Scripts\python.exe scripts/audit_python.py --online` | PASS: 49 pinned public PyPI packages, no OSV findings; 2026-09-17T14:10:40.186073+00:00 |
| `git diff --check` | PASS; only normal Git line-ending notices |

The initial correction run had 157 passes and one new fixture failure: copied evidence
reused a unique content hash. The fixture now has distinct provenance and a recomputed hash;
the uniqueness constraint and all existing assertions remain. An additional Signal-version/
legacy regression brings the final count to 159. Upstream Starlette httpx/AnyIO warnings
remain; no tests were skipped or weakened. Hosted CI was not run because no push is authorized.

### Phase Boundary

Still no Apollo, ZeroBounce, Smartlead, Pipedrive, Google provider integration, OpenAI,
Anthropic, n8n, outbound, CRM, AI, durable job runtime, event/outbox runtime, campaign system,
general approval engine or Phase 4 implementation. Only fake local business adapters remain.
Foundation authentication is unchanged. Dependency allowlists and lockfiles are unchanged.

### Git

Branch remains `phase-3-core-business-state`. HEAD, main and origin/main remain
`8e8de67447d6283bd51c412487af90ddf5eb7cf3`. Main unchanged; no staged changes, commit,
push, PR or merge. Phase 4 has not begun. All implementation remains local for review.

### Correction Archive and Remaining Limits

Only `company-os-phase-3-correction-delta.zip` is produced for this cycle. It contains
exactly the correction paths above plus `CORRECTION_FILE_LIST.txt`, with repository-relative
paths. Apply these replacements/additions over the original Phase 3 review source. No new
full-repository ZIP is produced. SHA-256 is reported at delivery to avoid a self-reference.
Ignored state, secrets, prior ZIPs, dependencies, caches and build/test artifacts are excluded.

Read-time re-evaluation adds database queries; no load-capacity claim is made. Old scores
lack reconstructable full inputs and intentionally require explicit rescoring. Independent
acceptance is outstanding. The existing Phase 3 limitations and stop gate remain in force.

---

## Gate Status

**PASS — implementation gates passed locally; awaiting independent review by Nouman.**
This is implementation evidence, not founder acceptance, hosted CI evidence, permission
to commit/push, or authorization for another phase. Date: 17 September 2026.

## Git

- Branch: `phase-3-core-business-state`, created from fetched `origin/main`.
- Phase 2 baseline, current HEAD, local main and origin/main: `8e8de67447d6283bd51c412487af90ddf5eb7cf3`.
- Working tree: modified/new Phase 3 paths below; no staged changes, no new commit.
- Main was not modified. No push, PR, merge, production provisioning or deployment.
- Pre-existing untracked `company-os-phase-2-review.zip` and `company-os-phase-2-correction-delta.zip` were preserved and excluded from this phase's manifest/archive.

## Objective

Implemented workspace-isolated core business state: sourced account/person identities,
employment/contact history, evidence/retractions, observed signals, draft strategy
versions, leads, deterministic explanatory scores, reviewed identity merge/reversal,
and local document/knowledge metadata. The console exposes evidence, missingness,
source rights and historical versus current support. All fixtures are synthetic.

## Changed Files

All modified/new Phase 3 paths relative to the accepted Phase 2 baseline:

- `AGENTS.md`
- `README.md`
- `apps/api/business.py`
- `apps/api/main.py`
- `apps/console/app/accounts/[identifier]/page.tsx`
- `apps/console/app/accounts/page.tsx`
- `apps/console/app/business/rescore/route.ts`
- `apps/console/app/evidence/[identifier]/page.tsx`
- `apps/console/app/globals.css`
- `apps/console/app/knowledge/page.tsx`
- `apps/console/app/leads/page.tsx`
- `apps/console/app/sources/[identifier]/page.tsx`
- `apps/console/components/business.tsx`
- `apps/console/components/shell.tsx`
- `database/migrations/manifest.json`
- `database/migrations/versions/0003_core_business_state.py`
- `database/migrations/versions/0004_core_integrity.py`
- `database/migrations/versions/0005_phase3_review_fixes.py`
- `database/seeds/core_business.py`
- `database/seeds/synthetic.py`
- `docs/adr/020-core-state-refinements.md`
- `docs/phases/phase-3-brief.md`
- `docs/phases/phase-3-handoff.md`
- `docs/phases/phase-3-manifest.json`
- `packages/company_os/adapters/local_documents.py`
- `packages/company_os/adapters/local_source.py`
- `packages/company_os/application/business.py`
- `packages/company_os/application/business_ports.py`
- `packages/company_os/application/scoring.py`
- `packages/company_os/business_contracts.py`
- `packages/company_os/domain/scoring.py`
- `packages/company_os/persistence/business.py`
- `packages/company_os/persistence/database.py`
- `packages/company_os/policy/access.py`
- `packages/company_os/reporting/business.py`
- `packages/contracts/api.d.ts`
- `packages/contracts/openapi.json`
- `scripts/audit_python.py`
- `scripts/boundaries.py`
- `tests/conftest.py`
- `tests/contract/test_contracts.py`
- `tests/e2e/core-business.spec.ts`
- `tests/integration/test_core_commands.py`
- `tests/integration/test_core_state.py`
- `tests/integration/test_identity_review.py`
- `tests/integration/test_phase3_review_fixes.py`
- `tests/integration/test_tenancy.py`
- `tests/phase3_scope.py`
- `tests/unit/test_core_boundaries.py`
- `tests/unit/test_scoring.py`

## Requirements Implemented

These are Phase 3 subsets, not claims that future workflows in each canonical requirement
are complete. Existing requirement IDs and Phase 1 design status remain unchanged.

| Requirement IDs | Implemented scope / remaining boundary |
|---|---|
| SYS-002; SEC-001/003; DATA-001/007 | Server-derived tenant context, typed resource registry, composite tenant references, FORCE RLS, runtime-role tests |
| SYS-003; DATA-014–020/026; API-017–020 | Evidence-backed observed signals and reproducible component scores with explicit unknowns and exclusions; no AI or activation |
| SYS-004; DATA-009–012 | Distinct identities, employment and contact state; no provider verification or outreach eligibility |
| SYS-023; DATA-013; SEC-004 | Source provenance, allowed purpose/fields, rights/retention checked synchronously on use; no external export/deletion workflow |
| DATA-022/023 | Workspace-local deny/unknown permission and suppression support only; no grants or release |
| DATA-025/058; DATA-044 subset | Reviewed merge/reversal, immutable snapshot/decisions and preserved attribution; no generalized privacy or approval engine |
| SYS-015; DATA-055/056 | Immutable local document versions, ACL-aware metadata and PostgreSQL full-text knowledge retrieval; no Drive or AI context |
| DATA-057 subset; API-001 | Atomic audit and scoped synchronous command receipts; no events/outbox runtime |
| API-004–006/008–010/012/013/016/054/056 subsets | Explicit typed read/command routes below; correction records are identity conflicts, not the future Task workflow |
| SEC-008/009; TEST-018 | Existing session/RBAC/CSRF/MFA boundaries retained; system admin gains no business authority |
| TEST-001/008/016/017/028/031 | Real-role tenant/FK tests, supporting evidence, merge/reversal, immediate revocation/retention checks and build boundaries; provider/AI portions remain deferred |

## Architecture Decisions

[ADR-020](../adr/020-core-state-refinements.md) records the bounded implementation
refinements for independent review. It adds no external dependency or provider:
four typed resource kinds; synchronous receipts; narrow identity/knowledge decisions;
identity conflict records instead of general Tasks; preserved historical child attribution
with retired-ID redirects; fake-local document ownership; deny-only permission structures;
and draft-only ICP/Offer versions. ADR-001–019 and canonical numbered specs are unchanged.
`AGENTS.md` now reflects the user's explicit Phase 3 authority and next stop gate.

## Database

One Alembic history adds `0003_core_business_state`, `0004_core_integrity` and
review correction `0005_phase3_review_fixes`. Current head: **`0005_phase3_review_fixes`**. Applied migration hashes are frozen in
`database/migrations/manifest.json`; Phase 2 migrations remain unchanged.

35 new tenant tables (44 including the nine Phase 2 foundation tables):

`accounts`, `command_receipts`, `contact_points`, `data_sources`, `decision_evidence`, `decisions`, `document_grants`, `document_versions`, `documents`, `employments`, `evidence`, `evidence_retractions`, `icp_excluded_accounts`, `icp_versions`, `icps`, `identity_conflict_evidence`, `identity_conflicts`, `identity_merge_reversals`, `identity_merges`, `knowledge_chunks`, `knowledge_items`, `leads`, `offer_proofs`, `offer_versions`, `offers`, `people`, `permission_assessments`, `resources`, `score_components`, `score_evidence`, `score_input_evidence`, `score_signals`, `scores`, `signals`, `suppressions`.

Every new tenant table uses FORCE RLS, composite workspace references and runtime-role
coverage. UUIDs, UTC timestamps, schema versions and expected record versions follow
foundation conventions. SQL enforces immutable history, matching resource children,
non-cyclic parents, valid scoped principals, matching evidence subjects and lead scores,
unique domain/discriminator pairs, next record versions, score bounds and permanently
null active strategy pointers. Actor checks use a narrowly scoped boolean membership
helper owned by existing NOLOGIN `company_auth`, with fixed search_path; it grants no
business authority. API roles cannot edit the resource registry; workers get no business
table grants. Runtime roles are non-owner, NOSUPERUSER and NOBYPASSRLS.

Indexes cover workspace chronology, foreign references, domain, status, lowercase names,
source/evidence/signal expiry, lead state and GIN full-text search. Lists are cursor-bounded
(default 50, maximum 200); cursors are signed and bound to principal/workspace/table.
No load-envelope claim or caching service is introduced.

Every final Python suite exercised: populate Phase 2 head → upgrade all Phase 3 revisions →
downgrade to `0002_identity_guards` (assert nine tables and two memberships retained) →
upgrade head → downgrade base → upgrade head → repeat upgrade. Tests use an isolated
random test database. The local synthetic demo was also explicitly reseeded via a guarded
Phase 3 downgrade/re-upgrade during development, retaining its Phase 2 identities; startup
does not create schema. Final `npm.cmd run migrate` succeeded as a no-op at head.

## Domain Model

- **Account:** legal/display identity, domain plus discriminator, parent and sourced attributes; shared domains and similar names stay distinct.
- **Person / Employment / ContactPoint:** separate people, evidenced current/former/uncertain employment, normalized immutable contact values. Email normalization does not remove dots or plus tags. Verification is unknown; permission and suppression are separate.
- **DataSource / Evidence / Retraction:** source rights document, allowed purposes/fields, expiry and retention; typed append-only facts distinguish observed/reported/inferred, confidence, entity match and explicit unknowns. Retractions/supersessions preserve original rows and immediately remove current support.
- **Signal:** candidate/accepted observation tied to matching current event evidence; unrelated facts cannot be promoted into an observed trigger. It is not a statement of buying intent.
- **ICP / Offer:** immutable numbered draft versions with closed criteria, exclusions, fixed-weight score policy and immutable proof joins. Leads pin exact versions. No activation command or active version exists.
- **Lead:** account/person/contact relationship, scoped owner and pinned strategy versions. Manual discovered → researching → researched, hard-exclusion disqualification and archive commands enforce versions and evidence/unknown completion. No generic state setter or eligibility transition.
- **Score:** immutable typed components and supporting evidence joins, priority, missingness and reproducible input hash. New inputs/version/retraction create history rather than rewriting a result.
- **Resource:** registry for account/person/lead/document with exact-child validation and workspace FKs.
- **Identity history:** immutable conflict, decision, merge and compensating reversal records; details below.
- **Documents / Knowledge:** local adapter-owned immutable bytes, PostgreSQL metadata, document grants, derived chunks and revocation-aware search.

## API

Exact added method/path pairs, compared with the baseline OpenAPI snapshot:

| Method | Path |
|---|---|
| GET | `/v1/workspaces/{workspace_id}/accounts` |
| POST | `/v1/workspaces/{workspace_id}/accounts` |
| GET | `/v1/workspaces/{workspace_id}/accounts/{identifier}` |
| POST | `/v1/workspaces/{workspace_id}/accounts/{identifier}/propose-correction` |
| POST | `/v1/workspaces/{workspace_id}/contact-points` |
| GET | `/v1/workspaces/{workspace_id}/documents` |
| POST | `/v1/workspaces/{workspace_id}/documents/register` |
| GET | `/v1/workspaces/{workspace_id}/documents/{identifier}` |
| POST | `/v1/workspaces/{workspace_id}/employments` |
| GET | `/v1/workspaces/{workspace_id}/evidence` |
| POST | `/v1/workspaces/{workspace_id}/evidence` |
| GET | `/v1/workspaces/{workspace_id}/evidence/{identifier}` |
| POST | `/v1/workspaces/{workspace_id}/evidence/{identifier}/retract` |
| GET | `/v1/workspaces/{workspace_id}/icp-versions/{identifier}` |
| POST | `/v1/workspaces/{workspace_id}/icps` |
| POST | `/v1/workspaces/{workspace_id}/icps/{identifier}/versions` |
| POST | `/v1/workspaces/{workspace_id}/identities/merge` |
| POST | `/v1/workspaces/{workspace_id}/identities/merges/{identifier}/reverse` |
| GET | `/v1/workspaces/{workspace_id}/knowledge/search` |
| GET | `/v1/workspaces/{workspace_id}/leads` |
| POST | `/v1/workspaces/{workspace_id}/leads` |
| GET | `/v1/workspaces/{workspace_id}/leads/{identifier}` |
| POST | `/v1/workspaces/{workspace_id}/leads/{identifier}/archive` |
| POST | `/v1/workspaces/{workspace_id}/leads/{identifier}/begin-research` |
| POST | `/v1/workspaces/{workspace_id}/leads/{identifier}/complete-research` |
| POST | `/v1/workspaces/{workspace_id}/leads/{identifier}/disqualify` |
| GET | `/v1/workspaces/{workspace_id}/offer-versions/{identifier}` |
| POST | `/v1/workspaces/{workspace_id}/offers` |
| POST | `/v1/workspaces/{workspace_id}/offers/{identifier}/versions` |
| GET | `/v1/workspaces/{workspace_id}/people` |
| POST | `/v1/workspaces/{workspace_id}/people` |
| GET | `/v1/workspaces/{workspace_id}/people/{identifier}` |
| POST | `/v1/workspaces/{workspace_id}/scores/calculate` |
| GET | `/v1/workspaces/{workspace_id}/scores/{identifier}` |
| GET | `/v1/workspaces/{workspace_id}/signals` |
| POST | `/v1/workspaces/{workspace_id}/signals` |
| GET | `/v1/workspaces/{workspace_id}/signals/{identifier}` |
| POST | `/v1/workspaces/{workspace_id}/signals/{identifier}/accept` |
| GET | `/v1/workspaces/{workspace_id}/sources` |
| GET | `/v1/workspaces/{workspace_id}/sources/{identifier}` |

Pydantic closed contracts generate OpenAPI and console TypeScript. Mutation requests use
server-derived context, permission/MFA as applicable, Origin/CSRF, Idempotency-Key and
If-Match for existing targets. Idempotency scope includes actor, workspace and command;
changed payloads conflict and replays recheck authority. Mutation, audit and receipt commit
atomically. Inaccessible/unknown IDs give safe errors. Restricted read metadata is audited.
List envelopes include metadata and signed cursors. Business timestamps normalize to UTC.

## Frontend

Added `/accounts`, `/accounts/[identifier]`, `/leads`, `/knowledge`,
`/sources/[identifier]`, `/evidence/[identifier]` and the server-only POST handler
`/business/rescore`. `components/business.tsx` renders typed server-side projections;
`components/shell.tsx` adds business navigation while retaining Phase 2 screens.

Accounts show provenance/current support, missing fields, observations, relationships,
score components, exclusions and input hashes. Leads show readable account/person names
and the exact ICP/Offer definitions and versions. Sources show rights/purpose/expiry;
knowledge displays stale items explicitly and hides revoked/ungranted content. The
rescore form re-authorizes through the API. No browser database access exists.

## Synthetic Data

Workspace A has 12 accounts and B has 10. Each also has six people/employments/contacts,
leads, draft definitions, source-rights documents, evidence, scores and knowledge fixtures.
Cases include a shared-domain parent/subsidiary; same names/domains across workspaces;
duplicate-looking people; current/former/uncertain employment; strong fit; missing trigger;
unknown size; excluded high raw points; expired/retracted facts; revoked/expired sources;
two distinct merge candidates; and approved/stale/revoked knowledge. Derived knowledge
chunks match their own immutable source document bytes and hashes.

User A is founder. User B remains the Phase 2 system administrator: it can access its
foundation workspace but has no business.read permission. No business authority was added
merely to demonstrate B. Direct runtime-role tests independently exercise B's business rows.
Seed is explicit, idempotent and preserves existing demo history; it is never startup DDL.

## Scoring

The versioned synthetic binary rubric uses Decimal arithmetic: fit 30, economics 20,
trigger 20, role 15, freshness 15. Criteria and rubric versions are persisted and closed.
Missing required support is null, never positive points or renormalized weight. Verified
role support is deferred, so seeded role points remain unknown and the strongest current
fixture reaches 85. A known mismatch is distinct from an unknown. Hard exclusions dominate
raw points and prevent high-priority qualification.

Canonical sorted JSON plus SHA-256 includes the evaluated inputs, source/evidence validity,
account identity/version, evidence hashes and immutable ICP/policy versions. Identical inputs
reuse the immutable result. Every non-null component has supporting evidence; unrelated,
expired, retracted or rights-invalid evidence cannot supply points. Historical rows remain
readable with current-validity context. This fixture tests explainability/arithmetic, not
predictive sales performance.

## Identity

No name/domain similarity auto-merges. Exact domain/discriminator collisions fail; shared
domains with different discriminators coexist. Correction proposals append evidence-linked
conflicts and put the account on hold. Reviewed same-workspace merges require current
versions, current evidence, founder identity-review permission and recent verified MFA.
UUID-ordered locks and a workspace command lock protect the mutation. The before-state
snapshot is immutable and hash-verified through the fake document store.

The retired identity redirects to the survivor while historical evidence/employment/contact
references retain their original attribution. Affected contacts are conflicted/held and get
review-required suppressions. Reversal is a new compensating record tied to the prior merge,
checks versions and snapshot integrity, restores identity availability under hold and retains
both the original merge and contact holds. No command silently restores outreach eligibility.

Nouman explicitly authorized the offline MFA fixture. Tests locally sign ES256 claims,
verify them through the existing identity verifier with offline JWKS, reject a wrong signature,
and create a real session before calling merge/reversal APIs. Normal synthetic sign-in stays
at aal1 and is denied these commands. No live provider authentication is claimed.

## Knowledge

FakeDocumentStore accepts only registered fixture identifiers or content hashes, rejects
arbitrary paths/URLs and verifies snapshot bytes. Document/version metadata includes hash,
classification and grants. PostgreSQL FTS applies tenant scope and document authorization
before returning derived text. Revocation is immediate at query time; stale results are
explicitly stale. No Drive API, OAuth, vector database, embedding or AI context pack exists.

## Security

The suite covers every new table using actual restricted runtime roles, absent/wrong tenant
context, composite-FK attacks, resource spoofing, invalid owners/grantees, cross-workspace
parents/employment/leads/documents/evidence/contact joins, signed cursor tampering, source
and document revocation, append-only history and score bounds. Foundation auth/session,
role, CSRF, logout, pool reset and process-restart persistence regressions remain passing.
Workers have no business grants. Synthetic login cannot merge; admin cannot read/approve
business state. Secrets/current-history and dependency/migration boundaries pass. No service
role key, production data or secrets are included in the source bundle.

## Initial Implementation Tests (historical)

Pre-review results; the correction gate above supersedes these counts. Results on Windows x64, Node 24.16.0, PostgreSQL 18.4, Python 3.12.14:

| Exact command | Final result |
|---|---|
| `npm.cmd run db:start` | PASS: local PostgreSQL available |
| `npm.cmd run migrate` / `npm.cmd run seed` | PASS; repeat migration at head also PASS |
| `npm.cmd run contracts` | PASS: generated snapshots match final contracts |
| `npm.cmd run check` | PASS: 132 Python tests, 0 failed, 0 skipped, 2 upstream warnings, 33.41s; Ruff lint/format (98 files), mypy (29 source files), OpenAPI/TypeScript drift, boundaries/secrets/migrations, ESLint/TypeScript and 2 Vitest tests (234ms) |
| `npm.cmd run build` | PASS: Next.js 16.3.5 production build; 16 routes including framework not-found |
| `$env:PLAYWRIGHT_CHANNEL='chrome'; node scripts/ci-services.mjs e2e` | PASS: 4/4 tests in 13.3s against running API and production console; includes both unchanged Phase 2 browser tests |
| `node node_modules/typescript/bin/tsc --noEmit --project apps/console/tsconfig.json` | PASS after restoring build-generated next-env.d.ts to the baseline |
| `npm.cmd audit --audit-level=moderate` | PASS: 0 vulnerabilities |
| `.\.venv\Scripts\python.exe scripts/audit_python.py --online` | PASS: OSV checked 49 pinned public PyPI packages, no findings; 2026-09-17T13:16:51.681910+00:00 |
| `git diff --check` | PASS (only normal Git line-ending notices) |
| Exact offline merge/reversal demo command in Local Demo below | PASS: 2 tests, 2 upstream warnings, 12.60s |
| `.\.venv\Scripts\python.exe scripts/boundaries.py` after handoff/manifest | PASS: final source, migration, dependency and secret checks (153 enumerated files) |

The advisory script is an explicit development-only online lookup of public package names/
versions; application, fixtures and test suite do not call it. No dependencies were added.
Scans are point-in-time results, not future vulnerability guarantees. The two Python warnings
come from upstream Starlette httpx/AnyIO deprecations; no tests were skipped or weakened.

Development failures were corrected: shared evidence-list mutation initially reduced the
strong-fit score to 70 instead of 85; the fixed assertion remains. Browser accessible-name
spacing and duplicate alert locators were corrected without changing production controls.
The new UTC regression initially omitted required record metadata, then hit formatting; the
complete test now passes and rejects naive timestamps. Windows sandbox process/temp/spawn
restrictions required approved executions outside the sandbox for build/integration/browser
checks and advisory networking. No security test failure was waived. Hosted CI was not run
because no push is authorized; the canonical CI-equivalent checks ran locally.

## Local Demo

In PowerShell, from the repository (first run only: `npm.cmd ci`, `npm.cmd run setup`):

```powershell
npm.cmd run dev
```

Open `http://localhost:3000`; sign in as Synthetic User A and select Accounts. The two
`shared.synthetic.example` rows remain distinct. Open **Synthetic A Missing Trigger**:
inspect unknown trigger/role, evidence links, current support and components. Click
**Recalculate deterministic score** twice; the unchanged inputs reuse the score/hash.
Open the approved source link to inspect rights/purposes. Open **Synthetic A Retracted Fact**,
**Expired Fact**, **Revoked Source** and **Expired Source** to inspect invalid support and
preserved history. **Excluded High Score** shows exclusion overriding raw points.

Open Leads to inspect pinned ICP/Offer versions and expanded definitions. Search `knowledge`
in Knowledge: A's approved/stale entries appear, stale is labeled, revoked and B entries do
not appear. Sign out, sign in as B and revisit an A detail URL: it is unavailable. B's Accounts
page denies business access because system administration is not business authority.

For the approved offline reviewed merge/reversal demonstration, leave PostgreSQL running
and use a second terminal. This uses a separate disposable test database and preserves the
interactive demo's candidates; its assertions verify decisions, snapshot, retired redirect,
original attribution, reversal and contact holds:

```powershell
node --input-type=module -e "import {loadEnv,python,run} from './scripts/local.mjs'; loadEnv(); run(python,['-m','pytest','-q','tests/integration/test_identity_review.py']);"
npm.cmd run check
npm.cmd run build
$env:PLAYWRIGHT_CHANNEL='chrome'
npm.cmd run test:e2e
```

Use installed Chrome as tested, or `npx.cmd playwright install chromium` and omit the channel
override. `npm.cmd run test:e2e` expects running services. For the exact production-server
browser gate above, stop the dev services with `npm.cmd run stop`, start only PostgreSQL
with `npm.cmd run db:start`, then run `node scripts/ci-services.mjs e2e`; that launcher stops
its API/console after the tests. Finish with `npm.cmd run db:stop` when appropriate.

## Phase Boundary

Exact table/route allowlists, import/dependency scans and runtime worker-grant tests enforce
this phase. There are no real source/verification/outbound/CRM integrations, AI clients,
sending paths, durable jobs, event/outbox runtime, leases/fences/effect dispatch, Redis,
Celery, Temporal, general approval engine, campaign runtime or Phase 4+ implementation.
Foundation authentication remains unchanged; Phase 3 integrations are fake and local.
Receipts are synchronous idempotency records, decisions are narrowly scoped history, and
permission/suppression rows are deny-only structural support. No future stub runtime was added.

## Known Limitations

No unresolved critical local Phase 3 acceptance failures. ADR-020 and this implementation
still require independent review. The synthetic console cannot itself perform privileged
merge/reversal; the explicitly approved offline fixture is the reproducible demo. Source
approval/knowledge review are seed inputs; no generalized promotion workflow exists.
The binary scoring fixture and unknown role component are explicit bounds, not evidence
of verified contacts. Detail views bound history to the latest 200 evidence/signals/employment
rows and 20 scores; collection APIs provide cursor pagination. Hosted CI and live identity
provider preflight are not claimed.

## Risks

Complex SQL invariants and broad new tenant schema merit independent review despite the
passing runtime tests. Rights and expiry are checked synchronously; no scheduled invalidation
or retention executor exists. Fake document bytes are outside the database transaction, so
a rolled-back registration can leave an unused local blob; no external effect occurs and
hash-addressed reads still verify content. Local documents are not a production storage or
backup solution. No concurrency/load capacity or production readiness claim is made.

## Rollback

Stop API/console/worker processes and preserve any wanted synthetic database/documents first.
With this Phase 3 checkout and local `.env`, explicitly load the existing development
environment and downgrade only Phase 3 (this deletes Phase 3 business data):

```powershell
npm.cmd run stop
npm.cmd run db:start
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv(); from alembic.config import Config; from alembic import command; command.downgrade(Config('alembic.ini'), '0002_identity_guards')"
```

This tested downgrade retains Phase 2 foundation rows, removes Phase 3 tables/functions and
new role permissions. Archive the uncommitted working tree before restoring code; obtain a
clean checkout of baseline `8e8de67447d6283bd51c412487af90ddf5eb7cf3` without overwriting other
work. Do not run current Phase 3 API code against the Phase 2 head: readiness intentionally
rejects the mismatch. To reapply using this checkout: `npm.cmd run migrate`, then
`npm.cmd run seed` (new synthetic business history). Fake local blob cleanup is separate and
was not automatically performed. A full `downgrade base` is only for a disposable database.

## Phase 4 Readiness

**NOT READY for commencement: independent Phase 3 review and explicit next-phase authorization
are required.** Technical implementation gates pass; no acceptance or permission is inferred.
No Phase 4 work has begun. No commit, push, PR or merge is authorized by this completion.

**PHASE 3 IMPLEMENTATION COMPLETE — AWAITING INDEPENDENT REVIEW**
