# COMPANY OS — PHASE 2 IMPLEMENTATION

## PHASE

Phase 2 — Repository & Platform Foundation

You are now authorised to IMPLEMENT Phase 2 only.

Phase 1 architecture and technical specification are attached.

Read the COMPLETE Phase 1 specification before modifying or creating anything.

The Phase 1 specification is the governing engineering contract.

Do not reinterpret the business architecture from scratch.

---

# 1. ROLE

Act as the principal implementation engineer for Company OS.

You are responsible for:

- repository bootstrap
- backend foundation
- frontend foundation
- database foundation
- authentication foundation
- workspace isolation foundation
- test infrastructure
- CI
- development environment
- documentation structure
- engineering-agent instructions

You are NOT authorised to implement later business functionality.

---

# 2. PHASE 2 OBJECTIVE

Create a locally runnable, tested Company OS skeleton with real tenant-aware authentication boundaries and NO business integrations.

At completion:

- Next.js console launches
- FastAPI API launches
- worker process launches
- PostgreSQL is available
- migrations work
- authentication works
- workspace memberships work
- tenant isolation is enforced
- initial API contracts work
- skeletal Attention / Approvals / System Health pages exist
- CI works
- tests work
- engineering instructions are stored in the repo

The system must be ready for Phase 3 without implementing Phase 3.

---

# 3. ABSOLUTE PHASE BOUNDARY

DO NOT IMPLEMENT:

- Account business model
- Person business model
- Leads
- Evidence
- Signals
- Scores
- Campaigns
- Smartlead
- Apollo
- ZeroBounce
- Pipedrive
- Google Drive integration
- Google Calendar integration
- OpenAI API
- Anthropic API
- AI workers
- AI routing
- workflow runtime
- durable business job engine
- n8n integration
- real email sending
- external provider accounts
- production deployment
- production database
- client business workflows

Do not create later-phase database tables “for convenience.”

Do not scaffold fake implementations of later business modules beyond clearly defined interfaces/placeholders allowed by Phase 1.

---

# 4. READ THESE PHASE 1 SECTIONS FIRST

Before coding, inspect and follow especially:

- Part 5 — Container and Component Architecture
- Part 6 — Repository Architecture
- Part 8 — Database Specification
- Part 20 — Authentication, Permissions and Secrets
- Part 23 — Testing Strategy
- Part 24 — Environments and Deployment
- Part 25 — Codex and Claude Code Development Rules
- Part 26 — ADR Registry
- Part 27 — Requirements Traceability
- Part 29 — Phase 2 specification
- Part 30 — Open Decision Register

The requirement identifiers in Phase 1 remain authoritative.

Do not renumber them.

---

# 5. IMPLEMENTATION TARGET

Implement the Phase 2 architecture approximately as:

company-os/
│
├── AGENTS.md
├── CLAUDE.md
│
├── apps/
│   ├── api/
│   ├── worker/
│   └── console/
│
├── packages/
│   ├── company_os/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── policy/
│   │   ├── workflow/
│   │   ├── ai/
│   │   ├── adapters/
│   │   ├── persistence/
│   │   └── reporting/
│   └── contracts/
│
├── database/
│   ├── migrations/
│   ├── policies/
│   └── seeds/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── security/
│   └── e2e/
│
├── docs/
│   ├── adr/
│   └── phases/
│
└── infra/

Refine only where implementation genuinely requires it.

Any meaningful architectural change requires an ADR.

---

# 6. TECHNOLOGY

Use the Phase 1 choices unless compatibility testing proves a problem:

Frontend:
- Next.js
- TypeScript

Backend:
- Python
- FastAPI
- Pydantic

Persistence:
- PostgreSQL
- SQLAlchemy
- Alembic

Authentication:
- Supabase Auth abstraction

Testing:
- appropriate Python test framework
- frontend test tooling
- PostgreSQL integration testing

Source control:
- Git

Do not introduce:

- Redis
- Kafka
- Celery
- Temporal
- Kubernetes
- LangChain
- agent frameworks
- extra databases
- vector databases
- additional orchestration infrastructure

in Phase 2.

---

# 7. PHASE 2 DATABASE SCOPE

Implement ONLY the foundational tables required by the approved Phase 2 specification.

At minimum:

- workspaces
- principals
- users
- service identities where required for architecture
- roles
- role permissions
- memberships
- foundational audit structure

Implement the schema conventions needed for these objects:

- UUID primary IDs
- timestamps
- schema version where required
- record version
- created_by / updated_by where appropriate
- workspace references
- migrations
- indexes
- constraints

Do not create business tables belonging to Phase 3+.

---

# 8. TENANCY AND RLS

This is one of the most important Phase 2 deliverables.

Implement the Phase 1 tenancy foundation.

Requirements include:

- tenant tables use workspace boundaries
- RLS enabled and forced where specified
- routine runtime DB roles must NOT be table owners
- runtime roles must NOT have BYPASSRLS
- no Supabase service-role credential in normal API/worker execution
- missing workspace context denies access
- workspace context comes from authenticated server-side identity
- request body cannot choose another workspace
- connection-pool reuse must not leak tenant context
- database policies and SQL grants both enforced

Implement synthetic:

Workspace A
Workspace B

Test:

User A can access A.

User A cannot access B.

User B cannot access A.

Admin/system technical access must not implicitly become business approval authority.

---

# 9. AUTHENTICATION

Implement the authentication abstraction and development flow.

Requirements:

- no public signup
- founder-oriented invite/auth model
- managed-auth compatible
- API verifies identity server-side
- frontend cannot talk directly to privileged database paths
- HTTP-only secure session architecture
- CSRF protections for state changes
- role and membership lookup
- membership revocation respected
- MFA architecture represented for later privileged actions

If local development cannot conveniently depend on live Supabase Auth, implement an explicit development/fake identity adapter behind the same interface.

Do not weaken production architecture to simplify local testing.

---

# 10. API

Implement only Phase 2 API surface.

At minimum:

GET /v1/me

POST /v1/auth/logout

GET /health/live

GET /health/ready

and the minimal authorised workspace lookup required by the console.

Use the Phase 1 response envelope and error conventions.

Do not expose generic database CRUD endpoints.

---

# 11. CONSOLE

Build only the Phase 2 UI shell.

Required:

- authentication screen/session handling
- workspace selector
- application navigation
- Attention route
- Approvals route
- System Health route

These can display empty/foundation states.

For example:

Attention:
“No decisions currently require action.”

Approvals:
“No approvals pending.”

System Health:
API
Database
Authentication

Later integrations should appear as:

Not configured

rather than falsely healthy.

Do not implement the complete dashboard from Phase 12.

---

# 12. WORKER

Create the worker application/process skeleton.

It must:

- start
- establish configured database access
- expose internal health/heartbeat behavior appropriate for the phase
- shut down cleanly
- contain no business workflow execution yet

Do NOT implement the Phase 4 durable job runtime prematurely.

---

# 13. CONTRACTS

Establish:

- Pydantic API models
- OpenAPI generation
- TypeScript client/type generation approach
- contract snapshot
- CI contract-drift detection

Frontend and backend must not maintain manually divergent request/response types.

---

# 14. MIGRATIONS

Use Alembic as the ONLY migration history.

Requirements:

- empty DB → latest schema
- downgrade/rollback where reasonably safe
- repeatable local setup
- migration ordering
- no schema auto-create at application boot
- no manual production console changes represented as architecture

Do not edit an applied migration after creation.

---

# 15. DEVELOPMENT EXPERIENCE

Target:

one documented command, or one very small sequence, to start local development.

Example desired experience:

clone repository

configure local environment

start PostgreSQL

run migrations

start API

start worker

start console

run tests

Do not optimise for exotic tooling.

Optimise for maintainability by one technical operator.

---

# 16. ENVIRONMENT

Create:

.env.example

Never:

- commit credentials
- use production credentials
- include real client/prospect data
- include live API keys
- include personal tokens

Use synthetic fixtures only.

Phase 2 has zero live sending budget.

---

# 17. AGENTS.MD

Create AGENTS.md based on Part 25 of the Phase 1 specification.

It must tell future coding agents to:

- read canonical docs first
- implement only authorised phase
- respect phase stop gate
- preserve architecture invariants
- use synthetic data
- use command boundaries
- never bypass tenant/policy/security rules
- run required tests
- report changes and risks
- never silently weaken a failing test

---

# 18. CLAUDE.MD

Create CLAUDE.md.

It should defer to AGENTS.md and the canonical docs.

Do not maintain a second contradictory architecture.

---

# 19. DOCUMENTATION

Map the approved Phase 1 specification into the proposed repository documentation structure.

At minimum ensure the repository contains canonical technical documentation for:

- product overview
- system context
- architecture
- domain model reference
- security
- testing
- deployment
- development workflow
- implementation roadmap
- ADRs
- requirements

Avoid duplicating the same rule text across many documents.

Use links/references where possible.

---

# 20. CI

Create the initial continuous integration pipeline.

At minimum verify:

- backend formatting/lint
- backend type checks where configured
- backend tests
- frontend lint/type checks
- frontend tests where applicable
- migration checks
- API contract generation/drift
- secret scanning or equivalent protection
- prohibited architecture/import checks where practical

A pull request should not be mergeable when critical foundation tests fail.

---

# 21. TESTS

Phase 2 MUST implement the relevant subset of:

TEST-001
TEST-018
TEST-019
TEST-031

from the Phase 1 specification.

Specifically prove:

### Tenant isolation
Workspace A cannot access Workspace B.

### Runtime database role
Tests execute using the real intended non-owner runtime database role.

### Missing tenant context
Access denied.

### Connection pool leakage
A transaction using Workspace A cannot leak identity to a reused connection serving Workspace B.

### Authentication
Unauthenticated/expired/revoked identity denied.

### Session/RBAC
Role/membership checks work.

### Environment containment
Staging/development architecture cannot invoke production provider effects.

### Build boundaries
CI detects:

- secret commits
- contract drift
- unversioned migrations
- prohibited dependency/import violations where implemented

Add other foundation tests as necessary.

---

# 22. SECURITY

Do not expose:

- Supabase service-role key
- unrestricted database owner key
- database credentials to frontend
- secrets in logs
- secrets in errors
- user-controlled workspace SQL context
- direct arbitrary SQL filters

Do not place credentials into:

- AGENTS.md
- CLAUDE.md
- README
- fixtures
- source code

---

# 23. LOCAL DEMO

At the end of Phase 2 I must be able to perform a reproducible demonstration.

Required demonstration:

1. Start local Company OS.
2. Sign in as Synthetic User A.
3. See Workspace A.
4. Attempt Workspace B access.
5. Receive safe denial.
6. Switch to Synthetic User B.
7. See Workspace B only.
8. View empty Attention.
9. View empty Approvals.
10. View System Health.
11. Confirm API and DB healthy.
12. Stop worker/API and restart.
13. Confirm foundation remains consistent.
14. Run automated tests successfully.

Document exact commands.

---

# 24. DO NOT PURCHASE OR PROVISION

Do not:

- purchase Supabase paid plan
- purchase Render
- purchase n8n
- purchase Apollo
- purchase Smartlead
- purchase ZeroBounce
- provision production OpenAI API
- provision production Anthropic API

without separate founder approval.

Use local/fake/dev-safe equivalents wherever possible.

---

# 25. DO NOT BEGIN PHASE 3

When Phase 2 acceptance criteria are met:

STOP.

Do not say:

“I also went ahead and implemented accounts/leads…”

Do not create Phase 3 tables.

Do not connect external providers.

Do not start AI integration.

---

# 26. REQUIRED PHASE 2 HANDOFF

At completion produce:

# PHASE 2 HANDOFF

## Gate Status
PASS / FAIL / PASS WITH OPEN ITEMS

## Objective
What was implemented.

## Repository
Tree of created/changed paths.

## Requirements Implemented
List all Phase 1 requirement IDs satisfied.

## Architecture Decisions
Any ADR added or changed.

## Database
Migration list and schema summary.

## API
Endpoints implemented.

## Frontend
Screens/routes implemented.

## Authentication
How local/dev auth works and production abstraction.

## Security
RLS and runtime-role model.

## Tests
Exact commands and exact test results.

## Demo
Exact startup and verification instructions.

## Dependencies
All packages added and justification.

## Secrets
Confirmation that none are committed.

## Known Limitations
Anything intentionally incomplete.

## Risks
Remaining Phase 2 risks.

## Phase Boundary Check
Explicit confirmation that no Phase 3+ business functionality was implemented.

## Rollback
How to return to pre-Phase-2 state.

## Phase 3 Readiness
READY / NOT READY

Do not begin Phase 3.

---

# 27. ACCEPTANCE GATE

Phase 2 passes only if:

- one reproducible local startup path exists
- console/API/worker start successfully
- database migrates from empty
- authenticated user sees only assigned synthetic workspace
- wrong-workspace access fails at database/security boundary
- missing auth context denies access
- runtime DB role does not bypass RLS
- secrets are excluded
- API contracts generate consistently
- CI passes
- required Phase 2 tests pass
- health endpoint leaks no sensitive information
- no real provider integration exists
- no live sending exists
- no Phase 3 tables/functionality were implemented

If an acceptance requirement fails:

report Phase 2 as NOT READY.

Do not weaken the requirement to obtain a PASS.

---

# FINAL INSTRUCTION

Build infrastructure, not business functionality.

The success criterion is not the number of files created.

It is:

A small, clean, secure, reproducible technical foundation that later phases can safely build upon.

Read the attached Phase 1 specification.

Implement Phase 2 only.

Run the tests.

Produce the Phase 2 handoff.

Then stop.