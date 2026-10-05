# Phase 6B Gate B1 handoff

PHASE 6B GATE B1 — PASS WITH FIXES (independent review)

The two bounded corrections are recorded in `phase-6b-gate-b1-correction-handoff.md`.
The results below are the preserved original B1 baseline, not correction-run results.

## Authority and starting state

The founder accepted GB-001 through GB-007 and authorized B1 implementation and
synthetic/mock verification. B1 authorizes zero real provider requests, zero real
credential resolution and USD 0.00 live spend. The earlier USD 5.00 ceiling is
reserved for separately authorized B2 and is not active here.

Branch: `phase-6b-gate-b-live-provider-preflight`.
HEAD, protected main and origin/main: `007977c8655b2d7bfca662f77e17befed68d6f12`.
Starting migration: `0026_phase6b_review_fixes`. Before B1 implementation, tracked
source and index were clean; blocked-assessment documents and historical archives
were untracked. At the start of the exception cycle, the incomplete B1 changes
were already unstaged. All final changes remain local and unstaged.

Accepted Core remains CLOSED. Its PR #5 and protected-main workflow 35526943549
are historical acceptance evidence, not fresh B1 regression results.

## Accepted blocker resolutions

| Blocker | Implemented resolution |
| --- | --- |
| GB-001 | Distinct founder/MFA preflight command reuses ordinary task/context construction; public ordinary submission remains fake-only. |
| GB-002 | Reservation explicitly validates the current preflight report, connection and separate gate budget while preserving ordinary fake checks. |
| GB-003 | Migration 0027 permits real/testing with exact tenant/provider references, never real/enabled; immutable test bindings remain draft. |
| GB-004 | Typed SelectedCredential has a redacted representation and a closed selected-provider resolver. |
| GB-005 | Supervisor requires preflight bindings, attaches containment, then releases one selected secret through bounded secondary stdin. |
| GB-006 | Fixed child exposes preflight-only SDK dispatch and synthetic-only mock transport; no inherited provider credentials or SDK discovery. |
| GB-007 | Required capability evidence precedes reservation and secret resolution; durable aggregate reservations, one-call guards and no uncertainty replay enforce spend bounds. |

## Architecture and authority

The closed in-process commands authorize, provision and submit only for a current
workspace founder with recent verified MFA. They use scoped, fixed-search-path
security-definer functions owned by non-login company_auth. API/worker cannot
assume that role or directly write preflight configuration. Commands append audit
records. System administration does not imply founder business authority.

The path is AITask -> ContextPack -> explicit draft test route -> CapabilityReport
-> shared gate budget -> committed ModelRun/reservation -> fresh authority,
context, price, connection and report checks -> one selected credential -> contained
child -> SDK translation -> validation -> AIResult. Ordinary AI remains fake-only.
No generic connection editor, production activation API or model tool was added.

CapabilityReport binds provider, exact model, test environment, account/project,
credential reference, SDK version, limits, verification flags and validity window.
Unknown account, billing, retention, region, rate, model or schema support fails
closed. Price configuration is immutable, hashed and rechecked for currency. B1
reports, model IDs and prices are synthetic; no real account/model/price selection
has been verified. Historical adapter model candidates are offline fixtures only.

## Migration exception: six conditions checked before editing

1. Protected main was freshly fetched and lacks 0027; its SHA is unchanged.
2. 0027 was untracked with zero local commits. GitHub histories for all six remote
   branches contained no commit for its path; it had not been pushed.
3. Protected-main history contained no 0027, so no merged PR had introduced it.
4. Available execution history showed only loopback local development/test
   applications. The file had never been published; no production, staging,
   shared, client or non-disposable database was accessed.
5. A new database, `company_os_b1_disposable_d07eebb2ab`, was created on local
   loopback PostgreSQL for this cycle. All 98 application tables were empty.
   It was rolled back from the initial draft 0027 to 0026 before editing.
6. Every 0001-0026 migration file matched the exact HEAD bytes, not merely
   newline-normalized hashes. Their raw SHA-256 ledger is in the B1 manifest.

These observations and the successful pre-edit rollback were recorded in ignored
local evidence before edits; the sanitized ledger is included in the manifest.
The founder exception was then used only for unpublished 0027 on disposable
no-history databases. No 0028 was created. The migration hash was refreshed.
This exception does not change general policy; reviewed/published 0027 is immutable.

The pre-existing development database was not rolled back or changed by this
exception cycle. It still contains an obsolete initial unreviewed draft of 0027.
Future B2 must use a database freshly migrated from the reviewed source. Do not
assume that the old development database matches this archive.

## Database and rollback

0027 adds `ai_preflight_gates` and `ai_preflight_routes`, both append-only with
FORCE RLS and same-workspace foreign keys. Existing provider connections gain
versioning and exact testing/reference constraints. Real enabled connections and
active preflight routes are forbidden. Existing fake connections remain unchanged.

Task and ModelRun guards enforce a synthetic preflight task, exactly one call,
current founder session, matching gate/provider/route/price/report, valid worker
fence and correct gate reservation. Live budgets cannot be spent by fake tasks.
The budget ceiling/category/period are immutable; deferred exposure checks bind
reserved/spent counters to actual reservations and ModelRuns. Scoped helper grants
support row locking and verification without adding API/worker configuration writes.

Disposable empty-schema -> head, 0026 -> 0027, no-history 0027 -> 0026 -> 0027,
repeated head upgrade and older round trips are covered by the database fixtures.
A populated preflight authorization/history database refuses downgrade and retains
0027 and its data. Rollback is permitted only before preflight history exists;
otherwise preserve history and use a reviewed forward correction after publication.

## Secret boundary and contained mock evidence

References are exactly `preflight:<workspace UUID>:openai` or
`preflight:<workspace UUID>:anthropic`. The closed parent resolver selects only
OPENAI_API_KEY or ANTHROPIC_API_KEY respectively; it does not search files,
profiles, arbitrary variables or accounts. B1 tests supply synthetic values only.

The typed secret is absent from the serializable call envelope, database, argv,
child environment, result and captured logs. Existing OS environment allowlisting
remains. After containment attaches and invalidation is checked, the supervisor
writes the envelope and a separate bounded one-use stdin message (maximum 8192
bytes) containing only the selected secret and required preflight metadata.
The child validates the binding again. Revocation/timeout rejects late output.

Both provider canary tests execute the contained mock path. They populate unrelated
provider/profile/environment canaries and verify selected-secret isolation and
no result/log/envelope leakage. Mock mode requires a synthetic credential; live
mode rejects synthetic credentials before launch and again in the child.
Python tests deny non-loopback socket and DNS access, positively tested for both
provider hostnames and an arbitrary non-loopback address. Child mock mode uses
MockTransport, not a live network transport. No real credential was resolved.

## Retry and spend safety

Each gate permits at most one task/call for each provider binding (two providers
maximum). SDK retries, automatic model retry, repair and fallback are all zero
for this path. A generic job retry cannot create another ModelRun or replay an
uncertain provider request. Durable uniqueness and call guards enforce this.

Both providers draw from one gate budget. Existing reservation/settlement locking
serializes concurrent spending. Pessimistic cost uses the most expensive allowed
input class plus bounded output. Known usage settles once; unknown usage, timeout,
process loss and uncertain dispatch retain exposure. A concurrent test with a
USD 0.020 synthetic cap permits only one USD 0.017024 reservation. Ordinary fake
technical budgets remain separate. B1's actual authorized and observed spend is $0.

## Verification

- Canonical `npm.cmd run check`: PASS, including generated contracts, Ruff lint,
  Ruff format (205 files), mypy (69 source files), boundaries, migration hashes,
  secret scanner, ESLint, TypeScript and console tests (2 passed, 0 skipped).
- Full Python: **478 passed, 0 skipped**, 815.05 seconds; one existing
  Starlette/AnyIO deprecation warning.
- Focused B1 unit/integration: **54 passed, 0 skipped**, 127.25 seconds;
  same existing warning. This comprises 29 unit and 25 integration cases.
- Actual company_api/company_worker role, populated A/B RLS, cross-reference,
  concurrent shared cap, immutable counter, no-retry and failure matrix: PASS.
- `npm.cmd run db:start` and `npm.cmd run migrate`: PASS on dedicated local B1 DB.
- Migration empty -> head, 0026 -> 0027, no-history 0027 -> 0026 -> 0027,
  repeated head, historical round trips and populated downgrade refusal: PASS.
- Production `npm.cmd run build`: PASS, 21 generated pages.
- Chrome Playwright: **8 passed, 0 skipped**, 50.8 seconds, against running
  local API/worker/console. Services shut down cleanly afterward.
- `npm.cmd audit --audit-level=moderate`: **0 vulnerabilities**.
- Python online OSV/PyPI audit: **57 packages, 0 findings**, checked
  2026-09-26T13:45:51.124466+00:00. `pip check`: no broken requirements.
- Pinned installed SDKs unchanged: openai 3.16.2, anthropic 1.7.0, httpx2 2.13.0.
- Network-ban positive denials and contained mock canary checks: PASS.
- `git diff --check`, raw historical migration byte comparisons, unchanged
  lock/CI/Core evidence and historical archive comparisons: PASS.
- Final remote main read: still `007977c8655b2d7bfca662f77e17befed68d6f12`.

No new failure remains. These are fresh local B1 results; no protected CI run was
triggered and no independent review acceptance is implied.

The initial full pass found 477 passing tests and one failure in the old tenancy
table inventory, which omitted the two new B1 tables. The inventory was extended;
the assertion that all tables have FORCE RLS was retained. No safety test was
skipped or weakened. The final run below supersedes that failed attempt.

Requirement mapping: SYS-002/012/014/019/022; AI-001-005; DATA-048/053/054;
SEC-003/009/010; TEST-001/009/010/011/012/017/018/019/022/031. ADR-025 documents
the reviewed provider/authority boundary extension to ADR-024.

## Changed paths

- `database/migrations/manifest.json`
- `database/migrations/versions/0027_phase6b_live_preflight.py`
- `docs/adr/025-live-provider-preflight.md`
- `docs/phases/phase-6b-gate-b-brief.md`
- `docs/phases/phase-6b-gate-b-handoff.md`
- `docs/phases/phase-6b-gate-b-manifest.json`
- `packages/company_os/ai/contracts.py`
- `packages/company_os/ai/credentials.py`
- `packages/company_os/ai/offline_probe.py`
- `packages/company_os/ai/preflight.py`
- `packages/company_os/ai/sdk_providers.py`
- `packages/company_os/application/ai_gateway.py`
- `packages/company_os/application/ai_preflight.py`
- `packages/company_os/persistence/ai.py`
- `packages/company_os/persistence/database.py`
- `packages/company_os/workflow/ai_runtime.py`
- `packages/company_os/workflow/isolation.py`
- `packages/company_os/workflow/provider_child.py`
- `packages/contracts/api.d.ts`
- `packages/contracts/openapi.json`
- `tests/conftest.py`
- `tests/contract/test_contracts.py`
- `tests/integration/test_ai_preflight.py`
- `tests/integration/test_ai_review.py`
- `tests/integration/test_tenancy.py`
- `tests/unit/test_ai_preflight_contracts.py`

No historical migration, dependency lock, CI workflow or accepted Core handoff
changed. Protected main and the index are unchanged. No commit, push, PR or merge
was performed. Build-generated next-env content is restored to its HEAD bytes.

## Review archive

The full-source `company-os-phase-6b-gate-b1-review.zip` includes source, tests,
docs, a content-hash manifest, REPOSITORY_TREE.txt and GATE_B1_CHANGED_FILES.txt.
The detached `.zip.sha256` records the archive digest to avoid recursive hashing.
Previous ZIPs, .git, .local, real .env, secrets, dependency trees, build/cache output,
local databases, browser profiles and private account metadata are excluded.
The tracked .env.example remains documentation. The obsolete root Phase 4
CORRECTION_FILE_LIST.txt is excluded in favor of the exact B1 inventory.

The earlier incomplete B1 ZIP is preserved as
`company-os-phase-6b-gate-b1-incomplete-review.zip`, SHA-256
`6bfa52fc0d72666ce6f9ca4e985576ab91f6f6c037368680e28488015356d312`.
The original blocked Gate B ZIP remains byte-for-byte unchanged, SHA-256
`29bd4e6ff1e704cbde5e534437a7fd77072a74b5ff435e70e59bbc5b638ae84c`.
All earlier historical archives remain untouched.

Archive CRC, source-byte equality, manifest hashes, exclusion rules and credential
pattern scans are verified. Intentional synthetic canary literals in test source
are fixture definitions, not leaked runtime credentials. A static pattern scan
alone cannot establish secret isolation; the contained runtime tests provide the
behavioral evidence. No real credential was used in either form of verification.

## Live status and future B2

OpenAI live calls: 0
Anthropic live calls: 0
Authenticated provider administrative requests: 0
Authorized B1 live spend: $0
Observed B1 live spend: $0
Production AI routes: 0

Architecture is submitted for independent review; B2 is not authorized by this
handoff. After acceptance and separate execution authorization, B2 must reverify
current account/model entitlement, pricing, SDK behavior, retention and region,
provision exact test-only references securely, and establish a founder-approved
aggregate cap. B2 MUST run against a database freshly created/migrated from the
finally reviewed 0027 source, or one whose schema equivalence to that source has
been independently proven. Do not reuse the obsolete local draft database as
evidence or for B2. Do not supply keys now.
B1 mock results do not prove real account access, retention, billing or live success.
Fresh verification in this cycle ran on Windows with Chrome; it is not a new
protected Ubuntu CI run. No production system or production inventory was queried.

## Phase boundary

Phase 7 has NOT begun. Apollo, ZeroBounce, Smartlead and Pipedrive have NOT been
integrated. Google production integration has NOT begun. No real business data
was used and no external business outbound occurred. Read-only GitHub/registry
security checks are not provider preflight requests. No deployment or Gate B2
execution occurred. Stop for independent review.
