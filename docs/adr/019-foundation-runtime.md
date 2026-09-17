# ADR-019: Phase 2 local runtime and foundation refinements

Status: implemented within the authorized Phase 2 scope; founder handoff review pending.

The modular monolith, Python/FastAPI/SQLAlchemy/Alembic, Next.js and PostgreSQL
choices in ADR-001–004 and the boundaries in ADR-009/016/017 remain unchanged.

Use Python 3.12 and Node 24, a hashed Python dependency lock and npm lockfile.
Local PostgreSQL 18.4 is delivered by the pinned development-only
`embedded-postgres` wrapper (MIT; binary redistribution Apache-2.0, PostgreSQL
license applies to the server). CI uses PostgreSQL 18.4. This avoids requiring
Docker Desktop on this Windows workstation. It does not provision a service,
install a machine service or replace the managed production database decision.
The wrapper's prerelease designation applies to the wrapper; the server version
is verified by integration tests. Removal trigger: a standardized Docker/local
PostgreSQL environment becomes preferable to the single maintainer.
The wrapper initializes the cluster; its publicly exported native `pg_ctl`
binary handles start/status/fast shutdown, including stops from another terminal.

Add `auth_sessions` as a strictly foundational identity table: opaque token hashes,
CSRF hashes, current principal, absolute and idle expiry, assurance and revocation.
The Next.js server is the browser's backend; only HttpOnly SameSite cookies enter
the browser, never JWTs or database credentials. API JWT verification is confined
to session bootstrap. Subsequent requests resolve the revocable server session.
Supabase asymmetric JWT verification implements the identity port; real provider
sign-in, recovery, rotating refresh and MFA enrollment remain provider preflight.
Local synthetic login is the authorized development adapter and cannot run in
staging/production. It never asserts MFA. No password or signup endpoint exists.

`company_auth` is NOLOGIN, non-owner and NOBYPASSRLS. Its fixed-search-path
security-definer functions resolve sessions and enumerate the current principal's
memberships. Explicit RLS policies and grants permit only the identity access those
functions need. Runtime roles cannot SET ROLE into it. The trusted API maps
verified identities to context; RLS protects against missing/accidental scope,
not a completely compromised API process (the Phase 1 trust model).

Workspaces omit `legal_entity_id` until its directory is authorized in a later
phase. No unbound pseudo-FK or legal-entity business table is introduced.
Audit is the Phase 2 subset of DATA-057 / OPS-018: immutable identity/action/scope,
request/correlation/command, decision/outcome and safe hash metadata. Future
approval/effect references and audit export infrastructure are deferred.
No jobs or heartbeat table is added; the worker probes its database role/schema
and emits a structured timestamp every 15 seconds. No worker-health claim is
shown by the UI because no independent worker monitor exists yet.

Phase 2 review correction: the API consumes `DATABASE_URL`; the worker directly
consumes `WORKER_DATABASE_URL` and receives neither `DATABASE_URL` nor the migration
owner credential. Launchers preserve those names without remapping. The worker
still requires `check_runtime(..., "company_worker")` before reporting healthy.
No additional credential, privilege or database role is introduced.

Authentication failures use `AuthenticationFailed` (HTTP 401). `AccessDenied` is
reserved for authenticated permission/assurance denials (HTTP 403), including the
existing permission and recent-MFA guards. Unknown/inaccessible workspaces remain
404. This clarifies foundation error semantics; it adds no policy engine,
permission, endpoint or business operation.

New read-only workspace and foundation-health routes are Phase 2 refinements of
API-001/060. The trusted BFF-only session exchange is an authentication transport
detail, not a public password endpoint. The only user state command is idempotent
logout, which revokes the session and appends scoped audit rows atomically.

Dependency evidence: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation),
[embedded PostgreSQL source](https://github.com/leinelissen/embedded-postgres),
[PostgreSQL RLS](https://www.postgresql.org/docs/18/ddl-rowsecurity.html),
[Supabase JWT verification](https://supabase.com/docs/guides/auth/jwts).
Resolved versions and security-scan results are recorded in the handoff.
