# Company OS engineering instructions

Read `docs/02-architecture.md`, `docs/14-security.md`, `docs/16-testing.md`,
`docs/requirements.md`, accepted ADRs, and the explicitly authorized phase brief.
The canonical specification preserves its Phase 1 design status; the current
implementation authority is `docs/phases/phase-6b-brief.md` and the user's instructions.

Implement only Phase 6B Gate A. Accepted Phase 6A protected main is
`41e27ff8cb211b1d3a80d702995cad2a9f28567e`, containing reviewed feature
`fc6921d148ea4d7d163119e5da3560caf653011c`. Stop at independent review.
Real OpenAI/Anthropic adapter code is permitted; real provider calls require
separate founder chat authorization naming providers and a total dollar cap.
No Phase 7, autonomous or recursive agents, production route activation,
live business data, sends, production provisioning or deployment. Fake technical
routes and synthetic engineering evaluations confer no business authority.
Do not commit, push, open a PR or merge until the founder explicitly authorizes it.
The repository owner and acceptance reviewer is Nouman; technical review evidence
belongs in the phase handoff. Do not infer approval from silence.

Use synthetic data. API and worker share application command boundaries. Never
bypass workspace, role, version, policy, authority, budget or effect controls.
Runtime roles must be non-owner, NOSUPERUSER and NOBYPASSRLS. No service-role key.
Keep tenant context transaction-local and server-derived. No client database access.
System administration never implies business approval authority.

Use one Alembic history. Never edit an applied migration; add a new revision.
No schema auto-create at application startup. Changes to architecture, ownership,
dependencies, policy boundaries, retention or provider contracts need an ADR or
an explicitly reviewed specification change. Keep future modules as documentation
boundaries until their phase is authorized.

Keep secrets out of tracked files, logs, fixtures and prompts. No production data.
Run `npm run check`, `npm run build` and Phase 2/3 browser tests against running
services. Do not skip or weaken a failing security test to obtain a pass. Report
exact results, limitations, changed paths, requirement IDs, migrations, rollback,
and risks in `docs/phases/phase-6b-handoff.md`. Stop; do not begin Phase 7.
