# Phase 6B — AI Gateway, Model Routing and Evaluation Harness

Authority: founder implementation request supplied 19 September 2026. It closes
Phase 6A and explicitly authorizes Gate A, superseding the historical 6A-only
instructions. Canonical numbered specifications retain their Phase 1 design status.

Fresh origin fetch verified main = origin/main =
`41e27ff8cb211b1d3a80d702995cad2a9f28567e`, containing reviewed feature
`fc6921d148ea4d7d163119e5da3560caf653011c`. Work branch:
`phase-6b-ai-gateway-evaluation`. Existing review archives are preserved.

Implement AI-001–005, AI-024 technical harness; DATA-048 AI connection metadata,
DATA-053 cost, DATA-054, API-057, SYS-012/013/014, SEC-003/004/006/007/009/010
and TEST-008/010/011/017/022/027/031. All model results remain proposals.

Gate A includes deterministic scoped context, immutable prompt/schema/price/route
versions, independently validated typed output, fake OpenAI/Anthropic providers,
disabled official SDK adapters, bounded repair/fallback, pessimistic reservations,
one durable ModelRun per request, Phase 6A process containment, frozen evaluation
datasets/comparisons, human route promotion and an AI Runs inspector.

Gate B is NOT authorized. Live preflight requires explicit founder chat consent
identifying OpenAI, Anthropic or both and a maximum combined live-test spend.
No credentials in chat. Documentation evidence never establishes account access.
Business route quality requires founder-labelled datasets; synthetic labels do not.

No research_account, later business task handlers, live connectors, arbitrary
tools/network destinations, autonomous/recursive agents, model-created effects,
production route activation or real business data. Phase 7 has NOT begun.

Preserve migrations 0001–0020; add ordered migrations, test downgrade to 0020 and
re-upgrade plus prior round trips. Run db:start, migrate, check, build, Chrome
ci-services e2e, npm audit, online Python audit, dedicated gateway/security/fault
tests and diff --check. Record exact results, limitations and rollback in handoff.
Produce manifest and sanitized source review ZIP with tree and SHA-256.
Stop for independent review without commit, push, PR, merge or deployment.

## Independent-review correction authority

The founder's Phase 6B Core independent-review correction request supersedes the
full-archive instruction above for this cycle. Scope is evaluation freshness through
promotion, populated RLS evidence for all eleven AI tables, precise pinned Anthropic
credential isolation and review artifact hygiene. Applied revisions 0001–0025 are
frozen; changes use additive 0026. Produce only a correction delta archive and stop.
No live call, spend, provider enablement, publication or Phase 7 is authorized.
