# PHASE 2 HANDOFF

Completed: 17 September 2026; bounded architectural-review corrections verified
17 September 2026 (initial verification ran 16–17 September).
Repository: `Noumanzafar1/company-os`.
Local checkout: `D:\SCIPIOFORM\companyOS`. Reviewer: Nouman.

## Gate Status

**PASS WITH OPEN ITEMS.** The local Phase 2 acceptance suite passes. No failing or
skipped foundation control test remains. The GitHub-hosted workflow has not run
because the founder explicitly prohibited the first push. Requiring the
`foundation-required` check in branch protection also remains a repository-owner
step after push authorization. Neither item is represented as already completed.

Managed Supabase account preflight and production deployment are not Phase 2
release claims; the specification explicitly permits the tested synthetic adapter.
Founder review of this handoff is the phase stop gate.

Independent architectural review returned **PASS WITH FIXES**. Both authorized
corrections below are now implemented and locally verified; reviewer acceptance
of the corrected handoff remains pending. No commit, push or Phase 3 work is authorized.

## Architectural Review Correction Cycle

The worker directly reads `WORKER_DATABASE_URL`, never aliases it to `DATABASE_URL`,
and the launcher excludes API, migration-owner and auth secrets from its environment.
Integration/process tests use that actual launcher environment and prove successful
startup as `company_worker` without `DATABASE_URL`, SQL privilege denials, repeat
clean shutdown, rejection of API/owner credentials by unchanged `check_runtime`,
and fail-closed behavior for a legacy caller supplying only `DATABASE_URL`.

Authentication failures now raise `AuthenticationFailed` and map to 401.
`AccessDenied` denotes authenticated permission/assurance denial and maps to 403.
The existing health route uses `require_permission`; existing recent-MFA guards
also receive the correct 403 mapping. Real session-based regression tests cover
both, missing/invalid authentication remains 401, and hidden workspaces remain 404.
No permission, endpoint, dependency, migration or business capability was added.

Exactly **14 repository files have net changes** from the frozen 119-file inventory:

| Changed file | Correction |
|---|---|
| `apps/worker/main.py` | Read `WORKER_DATABASE_URL` directly; retain runtime-role/schema check |
| `scripts/local.mjs` | Preserve worker credential name; remove `DATABASE_URL` from worker environment |
| `packages/company_os/domain/identity.py` | Distinct authentication-failure and authorization-denial exception types |
| `packages/company_os/adapters/auth.py` | JWT/identity verification failures use `AuthenticationFailed` |
| `packages/company_os/application/identity.py` | Invalid/unavailable identity/session failures use `AuthenticationFailed` |
| `apps/api/main.py` | Separate safe 401/403 handlers; permission helper on health; narrow logout catch |
| `tests/conftest.py` | Worker fixture invokes actual launcher sanitizer and checks credential isolation |
| `tests/integration/test_restart.py` | Repeated worker processes use sanitized, documented credential contract |
| `tests/integration/test_tenancy.py` | Assert actual worker role; API/owner rejection and missing-worker-variable regressions |
| `tests/security/test_auth.py` | Authenticated permission/MFA denial regression coverage; preserve 401/404 behavior |
| `tests/unit/test_security_policy.py` | Require authentication-specific exception for invalid managed JWT signature |
| `docs/adr/019-foundation-runtime.md` | Explicit credential ownership and authentication/authorization semantics |
| `docs/phases/phase-2-handoff.md` | Corrected handoff, changed-file inventory and exact verification evidence |
| `docs/phases/phase-2-manifest.json` | Updated result evidence, correction metadata and source hashes |

Build tooling regenerated `apps/console/next-env.d.ts`; its pre-cycle content was
restored and TypeScript rechecked, so it has **no net change**. `.env.example`
already defines the correct two runtime credentials and remains unchanged. The
policy helper, `check_runtime`, all migration/RLS files, dependencies/locks,
generated API contracts, CI configuration and engineering instructions are unchanged.
No test assertion was weakened. The existing review ZIP is unchanged; no new ZIP
was created. That archive is a historical **pre-correction** snapshot, not this handoff.

## Objective

Implemented a runnable modular-monolith foundation: Next.js/TypeScript console,
FastAPI/Pydantic API, PostgreSQL/SQLAlchemy/Alembic persistence, a connectivity-only
worker, invite-mapped identity abstraction, revocable server sessions, workspace
membership/RBAC, forced RLS, synthetic A/B fixtures, generated contracts,
verification tooling, CI definition and canonical engineering documentation.

## Repository

All files are new because the cloned repository had no commits or files.
The complete path/hash inventory is [phase-2-manifest.json](phase-2-manifest.json).

```text
companyOS/
  AGENTS.md, CLAUDE.md, README.md, .env.example, .gitignore
  .node-version, .python-version, package.json, package-lock.json
  pyproject.toml, requirements.lock, alembic.ini, playwright.config.ts
  .github/workflows/ci.yml
  apps/
    api/                 FastAPI routes and cooperative process launcher
    worker/              Connectivity/role/schema check and heartbeat only
    console/
      app/               Login, auth transport, Attention, Approvals, System
      components/        Scoped console shell
      lib/               Generated-contract client and CSRF/environment checks
  packages/
    company_os/
      domain/            Identity value types
      application/       Identity use cases and authentication port
      policy/            Permission and recent-MFA guards
      adapters/          Development/Supabase JWT verification
      persistence/       Runtime-role checks and transaction-local context
      reporting/         Reserved module boundary
      workflow/, ai/     Documentation-only deferred boundaries
      config.py, contracts.py
    contracts/           OpenAPI snapshot and generated TypeScript types
  database/
    migrations/          Alembic revisions and immutable hash manifest
    policies/            Reference to migration-owned policies
    seeds/               Idempotent, synthetic-only fixture loader
  tests/
    unit/, integration/, security/, contract/, e2e/
  docs/
    00–20 numbered docs  Complete mapped Phase 1 source
    adr/                Original registry plus ADR-019
    phases/             Phase 2 brief, handoff and result manifest
    requirements.md, local-development.md, dependencies.md
  infra/README.md        Local/CI boundaries; no production deployment
  scripts/              Setup, start/stop, CI, contracts and build guards
```

## Requirements Implemented

IDs are unchanged from Phase 1. “Foundation subset” does **not** claim later-phase
provider, business policy, audit-export or full-dashboard requirements are complete.

| Requirement IDs | Phase 2 evidence/scope |
|---|---|
| DATA-001 | UUIDs, clocks, schema/record versions, immutable tenant/identity fields, FK/unique/check constraints and expected-version update trigger |
| DATA-003 | Workspaces, purpose/status/timezone, authorization epoch and synthetic policy values; legal-entity directory deferred per ADR-019 |
| DATA-004 | Global principals, users and service identities with deferred exact-subtype constraint; no stored passwords/raw tokens |
| DATA-005 | Roles, closed permission registry, expiring/revocable memberships and server-side permission lookup |
| DATA-057 / OPS-018 | **Audit skeleton only**; append-only runtime grants and atomic logout/revocation audit |
| SEC-001 | Private schema, ENABLE/FORCE RLS, non-owner/NOBYPASSRLS runtime roles, SQL grants, scoped helper functions and transaction-local context |
| SEC-003 | **Foundation subset:** enumerate only the authenticated principal's authorized workspaces; no unscoped reporting |
| SEC-004 | **Foundation subset:** server-derived actor/scope and application command boundary; no later policy/approval engine |
| SEC-008 | Local invite-mapped auth, independently verified JWT bootstrap, HttpOnly sessions, CSRF/Origin, revocation, membership/RBAC and recent-MFA guard; managed account preflight deferred |
| SEC-009 | Generated local secrets excluded from Git; runtime credentials separated from migration owner and console; safe API errors |
| API-001 / API-002 / API-003 / API-061 | Closed schemas, response/error envelope, `/v1/me`, idempotent logout and minimal liveness/readiness |
| API-060 | **Foundation subset:** scoped platform status, explicit unconfigured integrations |
| UI-001 / UI-002 / UI-003 / UI-011 / UI-015 | **Shell subset:** private navigation, workspace selector, honest empty/failure states and scoped foundation health |
| TEST-001 | Real PostgreSQL A/B reads/writes/joins, missing/stale scope, non-owner role, FORCE RLS owner test, pool reuse after success/error/cancel |
| TEST-018 | Identity signature/issuer/audience/expiry, disabled users, revoked/expired/idle sessions, revoked memberships, CSRF, role limits, MFA and redirect controls |
| TEST-019 | Development adapter rejected in staging/production, nonzero sending/budget flags rejected, no effect endpoints/providers |
| TEST-031 | Secret/current-history scanning, dependency/import guard, contract drift, migration hash/history guard, phase-only tables/routes, locks and CI definition |
| SYS-002 / SYS-022 | **Foundation subset** of isolation and safe phased engineering; Parts 5/6/20/23–29 implemented within the Phase 2 boundary |

## Architecture Decisions

[ADR-019](../adr/019-foundation-runtime.md) records the concrete local PostgreSQL
runtime, Python/Node versions, server sessions, NOLOGIN identity helper role,
managed-auth preflight boundary, audit subset, omitted future legal-entity FK and
heartbeat-only worker. The original ADR-001–018 registry is preserved as supplied;
EXC-001 / ADR-015 / DEC-001 remain live-outbound blockers. No business architecture
or data-ownership model was replaced.

## Database

Migration head: **`0002_identity_guards`**.

1. `0001_foundation`: private `app` schema, nine foundation tables, functions,
   forced RLS, grants, indexes, constraints and version/subtype triggers.
2. `0002_identity_guards`: fixes shared-trigger field resolution found by the
   disabled-user test, with nested table-specific checks. The first applied
   migration was not edited. Downgrade restores the preceding function definition;
   full base rollback removes the synthetic foundation schema.

Tables: `workspaces`, `principals`, `users`, `service_identities`, `roles`,
`role_permissions`, `memberships`, `auth_sessions`, `audit_entries`.
No Phase 3 business tables exist. Sessions are foundational infrastructure added
by ADR-019. Alembic is the sole schema history. Role/bootstrap tooling handles
cluster credentials; application startup never creates or migrates tables.

Every backend test run proves empty→head→base→head and repeat upgrade, then uses
the seeded disposable database. PostgreSQL 18 is asserted in the integration suite;
the pinned local server and CI service are 18.4.

## API

| Method | Path | Behavior |
|---|---|---|
| GET | `/health/live` | Minimal process status |
| GET | `/health/ready` | Runtime role, DB connectivity and exact migration-head check; status only |
| POST | `/v1/auth/session` | Trusted BFF-only identity exchange; verified JWT, closed CSRF body, invited subject mapping |
| GET | `/v1/me` | Current principal, assurance and active authorized memberships/permissions |
| POST | `/v1/auth/logout` | Origin/CSRF protected, session-local idempotent revocation and audit; 204 |
| GET | `/v1/workspaces/{workspace_id}` | Independently authorized workspace lookup with RLS; inaccessible/unknown both 404 |
| GET | `/v1/workspaces/{workspace_id}/health` | Permission-scoped foundation status and explicit unconfigured integrations |

Pydantic generates the deterministic OpenAPI snapshot. `openapi-typescript`
generates console request/response types; CI/check compares both snapshots.
There is no generic database CRUD, signup, provider-effect or approval-grant route.

## Frontend

Routes: `/` redirects to `/attention`; `/login`, `/attention`, `/approvals`,
`/system`; server-only auth transport at `/auth/prepare`, `/auth/login`,
`/auth/logout`. Workspace selector lists only the user's memberships. API failure
is a visible unavailable state, not an empty successful dashboard. Business UI
is intentionally absent. Browser screenshots were captured and visually inspected
at `test-results/attention.png` and `test-results/system.png` (ignored artifacts).

## Authentication

Synthetic User A maps only to Workspace A (founder fixture). Synthetic User B maps
only to Workspace B (system-administrator fixture, no approval permission).
The BFF signs a short development assertion, the API verifies it, and a random
opaque server session is created. Only hashes persist in PostgreSQL. Browser
cookies are HttpOnly/SameSite=Strict, Secure outside the explicit loopback dev
exception. Idle expiry is 30 minutes; absolute expiry is 12 hours. API requests
recheck principal status and current membership; logout revokes immediately.

The Supabase-compatible port verifies asymmetric signatures, issuer, audience,
expiry and signed MFA claims. It was tested offline with generated asymmetric
keys, not a live Supabase account. Unknown subjects never auto-provision. Synthetic
auth cannot assert MFA or run in staging/production. Real invite/PKCE/refresh/MFA
enrollment is a managed-provider preflight, not an implemented production flow.

## Security

All nine foundation tables have ENABLE and FORCE RLS. API/worker roles are
NOSUPERUSER, NOBYPASSRLS, non-owner and cannot become `company_auth`. API accesses
only scoped workspace/membership/audit data and narrowly granted identity/session
functions. Worker has no business-table privileges or identity-directory lookup.
The NOLOGIN function role uses fixed search paths and explicit identity grants.
PUBLIC has no application-schema/function access.

Principal/workspace/epoch context is transaction-local and derived only after
server authentication and membership lookup. Tests inspect the reused physical
connection directly after commit/error/cancellation to prove context was cleared.
Missing context denies tenant reads/writes. RLS is not claimed to defeat a fully
compromised trusted API process; this is the explicit Phase 1 trust model.

The console has no DB environment credentials. No Supabase service-role key,
provider credential or production credential is used. API validation errors omit
submitted values; health exposes no configuration. Logout requires Origin and CSRF.

## Tests

Correction-cycle commands below executed locally on Windows x64, Python
**3.12.14**, Node **24.16.0**, npm **11.13.0**, PostgreSQL **18.4**, synthetic
fixtures only. No required test is skipped. PowerShell uses `npm.cmd` explicitly.
The complete existing Python unit/integration/security/contract/process suite and
frontend unit suite run through `npm.cmd run check`; five new cases raise the
backend count from 40 to 45. Setup/dependency installation was not repeated.

| Exact command | Final observed result |
|---|---|
| `.\.venv\Scripts\python.exe -m ruff check .` | PASS; all lint checks |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | PASS; 77 files already formatted |
| `npm.cmd run dev` | PASS outside sandbox; database, API, console and corrected heartbeat worker started |
| `npm.cmd run check` | PASS; **45 Python tests in 15.45 s**, 0 failed/skipped, 2 warnings; **2 Vitest tests**, 1 file (306 ms); Ruff lint/format (77 files), mypy (20 source files), ESLint, TypeScript, OpenAPI/TS drift, secret/dependency/import/migration/phase guards |
| `npm.cmd run build` | PASS; optimized production Next.js build, all nine listed routes compiled |
| `$env:PLAYWRIGHT_CHANNEL='chrome'; npm.cmd run test:e2e` | PASS; **2 browser tests in 10.4 s**, 0 failed/skipped; A/B isolation, shell, cookies/logout, CSRF/redirect controls |
| `$env:PLAYWRIGHT_CHANNEL='chrome'; node scripts/ci-services.mjs e2e` | PASS; **2 browser tests in 6.8 s**, 0 failed/skipped, against production console; API shutdown complete |
| `npm.cmd audit --audit-level=moderate` | PASS; **0 vulnerabilities** |
| `node node_modules/typescript/bin/tsc --noEmit --project apps/console/tsconfig.json` | PASS, exit 0 after restoring generated pre-cycle Next type-reference file |
| `.\.venv\Scripts\python.exe scripts/boundaries.py` | PASS; current/history secret, dependency/import, immutable migration and phase guards; 120 candidates including unchanged historical ZIP (119 source/doc files) |
| `git check-ignore .env .local .venv node_modules apps/console/.next test-results` | PASS; all six local/generated paths ignored |
| `git diff --check` | PASS, exit 0; no tracked changes (checkout is still unborn/untracked) |
| `npm.cmd run stop` | PASS; API shutdown complete, worker emitted `stopped`, PostgreSQL stopped cleanly; supervisor exit 0 |
| `npm.cmd run db:start` | PASS; PostgreSQL restarted for production-mode browser verification |
| `npm.cmd run db:stop` | PASS; final clean PostgreSQL shutdown |

Initial sandboxed `npm.cmd run dev` could not start PostgreSQL (`pg_ctl` restricted
token error 87 / start error 3). The same command succeeded with approved execution
outside the sandbox. This was an execution-environment failure, not bypassed test
coverage; every required test/check subsequently passed. Browser runs emitted the
non-failing `NO_COLOR`/`FORCE_COLOR` environment warning.

Final Python result: **45 passed, 0 failed, 0 skipped**, with two upstream
deprecation warnings (Starlette HTTPX adapter and AnyIO BlockingPortal alias).
Final frontend unit result: **2 passed**. Browser result: **2 passed**.
The process test additionally starts/stops the API and worker twice and proves
the same unexpired session and membership survive API process replacement.

Earlier verification findings remain documented: revision 0002 fixes the trigger defect;
the browser test exposed that `Referrer-Policy: no-referrer` suppressed Origin for
form navigation, corrected to `strict-origin-when-cross-origin` while preserving
strict Origin/CSRF rejection. The vulnerable initial Vitest pin was upgraded to
4.1.11 before final verification. No assertion was weakened to obtain a pass.
The local CI harness also verified its non-cookie-jar readiness probe handles the
expected login redirect. PostgreSQL lifecycle uses the packaged `pg_ctl` command
so an independent `db:stop` can perform a clean checkpointed shutdown.

The pinned Chromium download stalled locally and was stopped; tests used installed
Chrome through Playwright instead. No pinned-Chromium or Linux-hosted result is
claimed. CI is configured to install Chromium and upload test results when pushed.

## Demo

Full exact sequence: [local-development.md](../local-development.md).

```sh
npm ci
npm run setup
npm run dev
```

Open `http://localhost:3000`. A/B IDs for the unauthorized-URL demonstration:

- A: `a5dfc0dc-4d36-5087-b3fd-bc596ab872a2`
- B: `f31c9c83-9935-52c9-ae74-f3e79bb6d1dd`

As User A, visit `/attention?workspace=f31c9c83-9935-52c9-ae74-f3e79bb6d1dd`:
expect **Workspace unavailable**. Switch to User B and test A's UUID. View all
three shell pages, stop/restart with `npm run stop` / `npm run dev`, then run the
acceptance commands above. No password or real user account is needed.

## Dependencies

Complete direct-package/version/rationale table: [dependencies.md](../dependencies.md).
All transitive dependencies are recorded in the Python and npm lockfiles.
No paid service or business-provider SDK was added. ADR-019 documents the local
binary wrapper choice; all application traffic remains local in this demo.

## Secrets

**No credentials are committed; no commit exists yet.** The commit candidate was
scanned for credential patterns, prohibited environment files and historical
secrets. Random development-only values are in ignored `.env`; data/cache/test
artifacts are ignored. `.env.example` contains placeholders only. No production
data, API keys, personal tokens or live sending credentials were used.

## Known Limitations and Risks

1. GitHub-hosted CI and branch protection are pending the authorized first push
   and repository-owner review. Local checks are evidence, not a fabricated remote run.
2. Real managed Auth account configuration, MFA enrollment, refresh rotation and
   provider revocation preflight remain untested; managed sign-in fails closed until
   configured. Local synthetic auth is explicitly unsuitable for public deployment.
3. Worker monitoring is a local structured heartbeat only. No jobs runtime,
   independent uptime service, production monitoring, backups/PITR or restore SLA
   is claimed. Process restart tests do not claim full Phase 14 disaster recovery.
4. The two test-library deprecations need attention at a future dependency update.
   The local PostgreSQL wrapper carries a prerelease version label and is a dev-only
   convenience; application persistence is standard PostgreSQL.
5. Identity policy tables are not exposed as arbitrary CRUD. Founder invite/role
   administration beyond synthetic setup needs its own reviewed command/UI increment.
6. EXC-001 / DEC-001 and all paid-provider/account/business-authority gates remain
   open. Phase 2 provides no evidence that a remote sequencer can satisfy them.

## Phase Boundary Check

**No Phase 3+ business functionality was implemented.** No Accounts, People,
Leads, Evidence, Signals, Scores, Campaigns, approvals engine, durable jobs, AI,
provider integrations, external messages, client workflows, paid provisioning or
production deployment. Deferred module directories contain only boundary notes.
Reference documentation for later phases is preserved but not implemented.

## Git Status and Commit Readiness

Branch: `main`, unborn. Status reports **No commits yet on main...origin/main [gone]**
because the remote repository is still empty. Origin remains
`https://github.com/Noumanzafar1/company-os.git`. All Phase 2 source/docs/config
files are untracked and unstaged. No commit, branch publication or push occurred.
There are **119 source/documentation/configuration files plus one previously created
untracked ZIP** (120 untracked files total, zero staged/tracked files). The manifest
covers the 119 source files, not the historical archive. The existing
`company-os-phase-2-review.zip` is unchanged, SHA-256
`b6dd957ffe530541cdd9056cb570b502d32630e597ece4bca66fca98d37a785e`.
Do not treat that pre-correction snapshot as corrected source or include it in a
future commit. No replacement archive was requested or produced in this cycle.
At handoff the API, console, worker and local PostgreSQL are stopped cleanly.
The synthetic database files and ignored local configuration are preserved.

**Commit readiness: READY FOR REVIEW**, with the open external items above. Review
the manifest and handoff, then explicitly authorize the desired first commit/push.
No first push is inferred from completion of this implementation.

## Rollback

Stop local processes. For disposable synthetic data, an explicit operator
`alembic downgrade base` removes the application schema; the automated test suite
already exercised that rollback and upgrade. Keep wanted data/configuration first.
The exact commands and warnings are in the runbook. There is no prior Git commit
to reset to; archive/remove only the new manifest paths to recover the original
empty checkout, preserving `.git` and any wanted local state. No destructive
rollback was performed on the demo database or repository.

## Phase 3 Readiness

**READY for founder review of the technical foundation.** Overall Phase 2 remains
PASS WITH OPEN ITEMS until the external CI/review items are closed. This readiness
statement does not authorize Phase 3. **STOP: Phase 3 has not begun.**
