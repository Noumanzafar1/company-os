# Local startup, demonstration and verification

Requirements: Node 24, npm 11+, Python 3.12; Windows x64, Linux x64 or supported
embedded-postgres platform. Use a normal non-root OS account. PostgreSQL 18.4 is
downloaded with npm dependencies and runs only on `127.0.0.1:55432`. No installed
service or container daemon is needed. Ports 3000 and 8000 must also be free.

## First setup

Run from the repository root:

```sh
npm ci
npm run setup
npm run dev
```

`setup` creates an isolated `.venv`, installs the hash-locked Python dependencies
and editable package, and creates random development secrets in `.env` if absent.
It never replaces an existing `.env`. `dev` initializes/starts local PostgreSQL,
creates dedicated non-owner API/worker login roles and a NOLOGIN identity helper
role, runs Alembic as a separate maintenance step, seeds synthetic fixtures
idempotently, then starts API, worker and console. Application boot never migrates.
API/worker check the exact schema head and reject unsafe database roles at startup.

If `python` is not on PATH, PowerShell can select a Python 3.12 executable:

```powershell
$env:COMPANY_PYTHON = 'C:\path\to\python.exe'
npm run setup
```

On this workstation the interpreter used for initial setup was the Codex bundled
Python 3.12.14. Normal later commands use `.venv/Scripts/python.exe`. Linux uses
`.venv/bin/python`. The repository does not depend on a Codex installation.
Package download and child-process execution require normal local permissions;
an agent sandbox may require explicit tool approval. Do not run production secrets
through these scripts. Local setup rejects a non-loopback bootstrap database.

## Reproducible founder demonstration

1. Run `npm run dev` and open [http://localhost:3000](http://localhost:3000).
2. Choose **Sign in as Synthetic User A**. Workspace selector lists **Workspace A** only.
3. Append `?workspace=<Workspace-B-UUID>` using the actual
   Workspace B UUID printed by the fixture command below. A mismatched workspace must show **Workspace unavailable**, never
   reveal its name or content. The automated browser test obtains both IDs from
   their authorized users and performs this exact A/B exchange.
4. Sign out, choose **Synthetic User B**, and verify **Workspace B** is its only option.
   Use A's UUID in B's URL and receive the same safe denial.
5. Open Attention: **No decisions currently require action.** The explanatory text
   states business workflows are not enabled.
6. Open Approvals: **No approvals pending.** No grant/approval controls exist.
7. Open System Health: API, Database and Authentication are **Healthy** for the
   successful scoped request; seven future integrations are **Not configured**.
   Worker health is not claimed by this screen; observe its timestamped heartbeat
   in the terminal.
8. In a second terminal run `npm run stop`. Observe the worker's `stopped` record
   and API's completed shutdown. Run `npm run dev` again. The same identities,
   memberships and unexpired server sessions persist. Stopped services must not
   present fabricated health.
9. Run the acceptance commands below.

Synthetic workspace IDs can be printed without accessing any secrets:

```sh
# Windows; on Linux replace the executable with .venv/bin/python
.venv/Scripts/python.exe -c "from database.seeds.synthetic import key; print('A:', key('workspace-a')); print('B:', key('workspace-b'))"
```

The `workspace` query selects an authorized workspace; it never supplies SQL
identity. The backend independently maps the session, checks current membership,
then opens a transaction-local RLS context. Unknown and inaccessible IDs both
return 404. Missing API authentication returns 401.

## Tests and build

With local services running:

```sh
npm run check
npm run build
npx playwright install chromium
npm run test:e2e
```

`check` verifies OpenAPI and generated TypeScript without rewriting snapshots,
Ruff lint/format, mypy, secret/dependency/migration/import boundaries, PostgreSQL
integration/security/contract/unit tests, frontend ESLint/TypeScript and Vitest.
No PostgreSQL test silently skips when its dependency is missing. Each suite run
creates `company_os_test_<random>`, migrates empty→head→base→head, seeds fixtures,
uses the actual non-owner runtime roles, and removes only that test database.
Process tests start a separate API on port 18001, prove session persistence over
restart and clean API/worker shutdown. They never run business jobs.

Browser tests save screenshots and structured results in ignored `test-results/`.
If Chrome is already installed on Windows, use `$env:PLAYWRIGHT_CHANNEL='chrome'`
before `npm run test:e2e` to use it instead of downloading Chromium. The final
local handoff records which browser was actually tested; CI uses pinned Chromium.
The CI workflow uses the same checks with a PostgreSQL 18.4 service, and tests the
production console build. The GitHub job is named `foundation-required`. Once the
founder authorizes the first push, require this check in branch protection before
merging PRs. This local implementation does not change GitHub repository settings.

For intentional API changes, update Pydantic models and run `npm run contracts`,
reviewing both OpenAPI and TS snapshots. Never edit generated DTOs independently.
For dependency updates, document the ADR rationale, regenerate the appropriate
lock and scan before reviewing. Python lock generation uses Python 3.12:

```sh
python -m piptools compile pyproject.toml --extra dev --all-build-deps --allow-unsafe --generate-hashes --output-file requirements.lock
```

Run that command from the activated repository virtual environment. A lock's
generation comment may reflect the runner's pip environment; installs always
verify the pinned hashes. Runtime and development package purposes are in
[dependencies.md](dependencies.md).

## Auth and operational limits

Synthetic identity buttons exist only in local/test mode with a loopback origin.
The BFF signs a 15-minute development assertion and exchanges it through the API's
verified identity port. Only preseeded app subjects can establish sessions.
Server sessions expire after 12 hours absolute or 30 minutes idle, and principal
status/membership is rechecked on requests. Session tokens and CSRF values are in
HttpOnly, SameSite=Strict cookies; tokens are hashed in PostgreSQL. Cookies require
Secure in staging/production; plain HTTP is an explicit loopback-only dev exception.
State changes require exact Origin and matching CSRF. API sessions cannot be set
by a client-chosen workspace or user UUID.

Managed mode verifies Supabase issuer, audience, asymmetric signature and expiry.
It has no auto-signup or automatic principal creation. Actual invite/PKCE/refresh,
MFA enrollment and provider account revocation behavior need the later managed
Auth preflight. Until configured, managed sign-in fails closed in the console.
No MFA grant endpoint or business approval operation exists; a deterministic
recent-MFA guard and assurance metadata are tested for later authorized work.

## Migration rollback

Stop services first. For an explicitly chosen disposable local database, set
`MIGRATION_DATABASE_URL` from your local configuration in the operator environment
and run `.venv/Scripts/python.exe -m alembic downgrade base` (Linux `.venv/bin/python`).
This removes the Phase 2 `app` schema and its synthetic data. It does not drop the
database or cluster roles; passwords/data files remain only in ignored local
configuration. Do not downgrade a database with data you wish to preserve.
`npm run migrate` and `npm run seed` restore the foundation while the DB is running.
The first migration is immutable; revision 0002 corrects a trigger defect found
by the tests. Returning only to 0001 is not a supported runnable application.

No commits exist at the initial handoff. Returning the codebase to its original
empty state means archiving/removing precisely the paths in the handoff manifest
after stopping processes; preserve `.git` and any wanted local data. No automatic
destructive reset or cleanup is performed.
