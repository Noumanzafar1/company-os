# Phase 6B Gate B1 correction handoff

PHASE 6B GATE B1 CORRECTIONS NOT READY

The two requested implementation corrections are complete and focused tests pass.
The required npm audit fails with five high and one critical finding in unchanged
dependencies. All other required regression checks passed, as recorded below.
This is not an all-green acceptance or authorization to execute Gate B2.

## Authority and baseline

Independent review accepted the B1 architecture in principle (PASS WITH FIXES),
authorizing only privilege preservation and credential/capability binding. The
founder expressly retained the unpublished-0027 migration exception. No redesign,
real provider request, real credential resolution, commit, push, PR or B2 is allowed.

Branch: `phase-6b-gate-b-live-provider-preflight`.
HEAD/main/origin main: `007977c8655b2d7bfca662f77e17befed68d6f12`.
Starting source matched all 287 source entries of the previous full B1 review ZIP.
That archive remains unchanged with SHA-256
`6ffd877c5c015f1f9be7836c77f588d80c62b121a568e14866119898cdfa4d29`.
The correction delta is calculated against that source snapshot, not against HEAD,
which intentionally does not yet contain the accepted-in-principle B1 work.

Before editing 0027, verified: unchanged remote branches (including main), untracked
uncommitted 0027 matching the unpublished prior ZIP, no published/merged history,
only local development applications, newly created no-history loopback database,
and exact byte equality of 0001-0026 against HEAD. The old draft development
database was not used or modified. The original downgrade defect was reproduced
and recorded in a fresh empty database before editing; a second fresh database was
created for corrected browser fixtures. Integration fixtures create and destroy
their own isolated databases. The general migration immutability rule is unchanged.

## Fix 1 - Migration privilege preservation

Measured actual information_schema grants at accepted 0026, including grant options:

| Existing table | company_auth privileges at 0026 | Additions in 0027 |
| --- | --- | --- |
| authority_test_targets | SELECT, UPDATE | INSERT |
| budgets | none | SELECT, INSERT, UPDATE |
| ai_registry | SELECT | INSERT |
| ai_routes | SELECT | INSERT |
| ai_route_states | SELECT, UPDATE | INSERT |
| model_runs | none | SELECT |

All listed grants have no grant option. The two new preflight tables receive
SELECT/INSERT and disappear on a permitted empty-history downgrade. The original
0027 downgrade demonstrably lost authority_test_targets SELECT. The correction
now grants/revokes only INSERT on that table, preserving historical SELECT/UPDATE.
Other privileges are revoked only where they were introduced by 0027.

The new regression creates a disposable database, upgrades to 0026, records ALL
company_auth app-table privilege/grant-option tuples, upgrades to 0027 and checks
the exact additions, downgrades to 0026 and compares exact set equality, then
re-upgrades and verifies the same 0027 set. Repeated head is also checked. Existing
empty-schema, no-history round-trip and populated downgrade refusal remain covered.
Migration 0027's hash is updated. 0001-0026 remain byte-for-byte unchanged; no 0028.
The measured original grant ledger is included in the correction manifest.

## Fix 2 - Credential/capability binding

CapabilityReport carries a bounded non-secret `credential_binding`:
`sha256-v1:` plus 64 lowercase hex digits. SHA-256 hashes a fixed domain/version,
the exact workspace/provider credential reference and selected key bytes with NUL
separators. The closed environment mapping is unchanged. Future authorized account
verification must compute this binding from the same selected key used to verify
the reported account; B1 uses only synthetic canaries.

The trusted parent commits reservation/ModelRun, rechecks current context/report,
resolves one selected credential and constant-time compares the recomputed binding
before calling the supervisor. The supervisor checks before child creation; the
fixed child checks again before SDK translation. The immutable selected value is
used thereafter, so changing the environment cannot substitute a later value.
Mismatch gives a generic denial, retains the conservative reservation and cannot
replay. Existing post-containment secondary stdin, minimal child environment,
fixed HTTPS endpoints, trust_env=False, retry-zero and one-call controls remain.

Only the digest is stored in the scoped immutable report/configuration; the raw key
never enters SQL, business rows, task/context/envelope, logs, API/UI or results.
The health API removes credential_binding from report projection. SHA-256 is
appropriate for high-entropy API credentials; it is not password hashing, encryption,
account verification or attestation. Low-entropy values can be guessed offline,
and report metadata can correlate a key within its scoped reference. Existing RLS
still protects reports. A compromised trusted parent/verifier is outside this check.
Rotation requires new account verification and a new report; old unbound reports fail
closed. No real account, pricing, billing, region or retention assertion was made.

Synthetic evidence:

- A-bound reports with A resolved complete the contained mock path for both providers.
- Substitution of environment slot B causes denial before supervisor/child dispatch;
  a spy would fail the test if execution were reached. No second ModelRun is allowed.
- Cross-provider binding, wrong workspace reference and missing binding deny before
  child launch. The digest itself is workspace/provider scoped.
- Runtime-generated canaries are absent from all application table rows, task/context,
  ProviderCall, results, captured logs and health API output. Binding metadata is
  absent from ordinary API output and ProviderCall. Artifact scans reject runtime
  canary patterns; synthetic source fixture expressions contain no runtime values.

## Regression

| Check | Final result |
| --- | --- |
| Canonical npm.cmd run check | PASS |
| Full Python suite | 494 passed, 0 skipped, 1 existing warning; 610.65 seconds |
| Focused B1 corrections | 70 passed, 0 skipped, 1 existing warning |
| Console tests | 2 passed, 0 skipped |
| Chrome Playwright | 8 passed, 0 skipped; 1.1 minutes reported |
| Production build | PASS, 21 generated pages |
| Contracts / lint / format / types / boundaries | PASS; Ruff 206 files, mypy 69 source files |
| API/worker RLS / cross-tenant / shared cap | PASS |
| Migration privilege equivalence / re-upgrade | PASS; exact all-table privilege and grant-option equality |
| Empty -> head / 0026 -> 0027 / round trip / repeated head | PASS |
| Populated downgrade refusal | PASS |
| Credential A acceptance / slot B substitution denial | PASS for both providers |
| Cross-provider / workspace / missing-binding denial | PASS before child creation |
| Database / envelope / API / log / result canary checks | PASS |
| Network-ban positive checks | PASS |
| npm audit --audit-level=moderate | FAIL: 5 high, 1 critical dependency finding |
| Python OSV/PyPI audit | 57 packages, 0 findings, 2026-10-05T04:41:26.214715+00:00 |
| pip check | PASS: no broken requirements |
| git diff --check / historical migration bytes / prior archives | PASS |

The full canonical check excludes the separate npm audit command; its PASS does
not override the audit failure. No new protected CI run was triggered. Fresh browser
services used the corrected disposable database and shut down cleanly afterward.

One existing Starlette/AnyIO deprecation warning remains. No safety tests are skipped
or weakened. Focused-suite elapsed time was reported as 49,625.46 seconds across
this long-running session; its result is 70 passed, zero skipped. This is elapsed
wall time and is not a performance benchmark.

The npm audit failure is preserved: six affected dependency entries, comprising
five high and one critical. It reports braces/micromatch/fast-glob and the Next ESLint
chain, plus Next 16.3.5. Advisories:

- https://github.com/advisories/GHSA-vfj7-8cjw-p6xm
- https://github.com/advisories/GHSA-vcvr-r3jv-pc5j

No exploitability claim for this application is inferred from package audit alone.
No dependency, lockfile, CI threshold or audit rule was modified. npm suggested
forced changes including a breaking ESLint-config downgrade; no such command was
run. A separately reviewed dependency correction is required before an all-green
acceptance can be claimed. The two requested code corrections do not resolve these
newly reported dependency findings.

Requirements: SEC-009/010; TEST-001/009/010/011/012/017/018/019/022/031;
SYS-002/012/014/019/022. ADR-025 documents the bounded binding extension.

## Exact correction files and artifact

- `apps/api/ai.py`
- `database/migrations/manifest.json`
- `database/migrations/versions/0027_phase6b_live_preflight.py`
- `docs/adr/025-live-provider-preflight.md`
- `docs/phases/phase-6b-gate-b-handoff.md`
- `docs/phases/phase-6b-gate-b1-correction-handoff.md`
- `docs/phases/phase-6b-gate-b1-correction-manifest.json`
- `packages/company_os/ai/credentials.py`
- `packages/company_os/ai/preflight.py`
- `packages/company_os/workflow/ai_runtime.py`
- `packages/company_os/workflow/isolation.py`
- `packages/company_os/workflow/provider_child.py`
- `tests/integration/test_ai_preflight.py`
- `tests/integration/test_ai_preflight_migrations.py`
- `tests/unit/test_ai_preflight_contracts.py`

`company-os-phase-6b-gate-b1-correction-delta.zip` contains only changed repository
files from this correction plus `CORRECTION_FILE_LIST.txt`. Its detached SHA-256
avoids recursive hashing. The correction manifest hashes changed files except itself.
CRC, file-list equality, source-byte equality, credential-pattern and generated-canary
scans are performed. .git, real .env, dependencies, build/cache output, local DBs,
.local, browser profiles and prior archives are excluded. The accepted full B1 ZIP,
its sidecar and every historical archive remain unchanged.

## Live provider status

OpenAI live calls: 0
Anthropic live calls: 0
Authenticated provider administrative requests: 0
Authorized B1 live spend: $0
Observed B1 live spend: $0
Production AI routes: 0

## Gate B2 and phase boundary

B2 NOT AUTHORIZED. B2 MUST run against a database freshly created/migrated from the
finally reviewed 0027 source, or against a database whose schema equivalence to that
source has been independently proven. The obsolete local draft-0027 database is
not evidence and must not be silently reused.

Phase 7 has NOT begun. No real business data or external business outbound occurred.
Dependency/advisory lookups were read-only and are not provider preflight requests.
No commit, push, PR, merge, deployment or B2 execution occurred. Stop for independent
review with the npm audit blocker visible.
