# Part 25 — Codex and Claude Code Development Rules

The following are proposed file contents for Phase 2, not files installed in this phase.

**AGENTS.md contract**

```markdown
# Company OS engineering instructions
Read docs/02-architecture.md, docs/14-security.md, docs/16-testing.md,
docs/requirements.md and the explicitly authorised docs/phases/phase-N.md.
The numbered specification and accepted ADRs are the shared authority.
Implement only the named phase and its listed modules. Stop at its gate.
Do not initiate the next phase, buy services, deploy production, send external
messages, grant access or run production migrations without applicable authority.
Use synthetic fixtures and fake providers until the relevant preflight passes.
All writes use application commands. Enforce workspace, role, version, policy,
approval, budget and effect idempotency. Do not expose privileged DB keys.
No AI output may grant authority or become an unsupported outward factual claim.
Preserve CRM, document and operational ownership. Do not invent provider guarantees.
Use one Alembic migration history; do not edit applied migrations or auto-create tables.
Changes to data ownership, policy boundaries, retention, dependencies or provider
contracts require an ADR or an explicitly reviewed specification change.
Run the phase's required tests plus directly affected regressions. Report exact
results and limitations; never mark an unrun account test passed.
Keep secrets out of code, logs, fixtures and prompts. No production-data downloads.
Provide changed paths, requirement IDs, test evidence, migration impact, rollback
and open risks in the handoff. Stop after the reviewable phase result.
```

**CLAUDE.md contract**

```markdown
# Company OS context
Follow AGENTS.md and the canonical numbered documents in docs/.
This file adds no alternative architectural or permission rules.
Read the currently authorised phase brief before modifying the repository.
Use the same command contracts, migration history, fake adapters and acceptance
tests as Codex. Preserve phase stop gates and document any provider uncertainty.
```

The phase brief names allowed directories, requirements, acceptance tests, exclusions and reviewer. Coding tools may refactor within that scope, fix tests, create branches and local fixtures, and propose documentation corrections. They may not waive failing controls by editing requirements or tests to match faulty behavior. Human review is required for production releases, new spend, destructive migrations, role/secret access, authority changes, external communications and changed client obligations.

Dependencies require a concrete need, maintained primary source, pinned version, licence compatibility and review of transitive/security impact. Prefer official provider SDKs plus standard FastAPI/Pydantic/SQLAlchemy/Alembic tooling. Do not introduce an agent framework, message broker or second ORM because scaffolding suggests it. Version runtime and package locks in Phase 2 after compatibility checks; this document does not invent current package versions.

Technical debt policy: acceptable V1 shortcuts include modest UI styling, manual vendor onboarding, simple SQL metrics, one region, explicit admin runbooks and fixture adapters for later phases. Never acceptable: tenant mixing, credentials in prompts, uncontrolled retries, approval bypass, missing opt-out handling, hidden stale data, silent fabricated claims, unaudited privileged changes, unversioned migrations or production changes without relevant tests. Record accepted debt with owner, consequence and removal trigger.

