# Part 26 — ADR Registry

All decisions are **PROPOSED FOR PHASE 1 APPROVAL** unless otherwise labelled. Approval adopts the design, not permission to incur spend or enable live integrations.

**ADR-001 Modular monolith.** Context: one founder and one engineering codebase. Decision: shared domain/application modules, separate API/worker/console processes. Alternatives: microservices, purely visual workflows. Consequences: simpler transactions/releases, shared blast radius. Migration trigger: independent scaling/ownership requirements supported by observed bottlenecks.

**ADR-002 Python backend.** Context: typed language work, deterministic workflows and provider adapters. Decision: FastAPI/Pydantic, SQLAlchemy and Alembic. Alternatives: TypeScript-only backend. Consequences: two languages but clear server contracts. Migration trigger: sustained maintainer constraint with a costed port, not model preference.

**ADR-003 Next.js frontend.** Context: authenticated attention and approval interface. Decision: TypeScript console with generated API DTOs. Alternatives: CRM-only UI, low-code internal tool. Consequences: small custom frontend, no direct data/provider access. Migration trigger: maintenance cost exceeds value or platform limitation.

**ADR-004 Managed PostgreSQL and Auth.** Context: transactional state and RLS. Decision: Supabase initially, standard SQL schemas and app identity mapping. Alternatives: Render Postgres plus separate Auth, self-hosting. Consequences: less operations work; Auth/recovery features still provider-specific. Migration trigger: cost, required region, isolation or recovery capability.

**ADR-005 Pipedrive commercial ownership.** Context: avoid custom CRM. Decision: CRM owns stage/owner/amount/next action; database mirrors. Alternatives: local CRM, another managed CRM. Consequences: reconciliation and async commands. Migration trigger: demonstrated cost/visibility/API limitation; preserve internal UUIDs and source history.

**ADR-006 Database jobs with selective n8n.** Context: survive restarts and founder absence. Decision: leased PostgreSQL jobs/outbox; n8n for bounded connectors only. Alternatives: n8n-only state, Redis broker, Temporal immediately. Consequences: implement small queue semantics, no duplicate canonical state. Migration trigger: long-lived branching/compensation makes our runtime expensive to maintain, not job count alone.

**ADR-007 Thin AI gateway.** Context: two providers, shared policy/cost/evaluation. Decision: task-based routing and official SDK adapters. Alternatives: third-party gateway SaaS, unconstrained agent framework. Consequences: own small translation/evaluation layer. Migration trigger: evidenced operational need beyond its scope.

**ADR-008 Narrow provider ports.** Context: plausible CRM/data/sequencer changes. Decision: vendor-neutral domain commands with adapter capabilities. Alternatives: fully generic universal connector. Consequences: some provider-specific code, fewer leaky abstractions. Migration trigger: replace one provider through shadow-read and mapped cutover.

**ADR-009 Shared command/policy boundary.** Context: UI, worker and n8n could bypass each other. Decision: one in-process application authority layer exposed via API. Alternatives: direct DB/vendor actions by agents. Consequences: more explicit commands, consistent enforcement. Migration trigger: none without formal security redesign.

**ADR-010 Outbox, inbox and effect records.** Context: network delivery cannot be exactly once. Decision: at-least-once events, idempotent local consumption, uncertain external effects. Alternatives: retry every failed request; distributed transaction fiction. Consequences: founder may resolve ambiguous sends; delayed work preferred to duplicate. Migration trigger: workflow engine change preserves effect semantics.

**ADR-011 Drive document ownership.** Context: human-editable knowledge and final artifacts. Decision: Drive bytes, DB catalogue, hashed approval snapshots. Alternatives: storing files/complete knowledge in DB, duplicate note system. Consequences: ACL/version/export reconciliation. Migration trigger: contract, region or storage-control requirement.

**ADR-012 No vector database initially.** Context: small structured knowledge base. Decision: SQL/full-text; evaluate pgvector only after measured retrieval need. Alternatives: separate vector vendor at launch. Consequences: simpler deletion and access controls. Migration trigger: documented retrieval evaluation gain.

**ADR-013 Six bounded AI roles.** Context: repeatable tasks and human authority. Decision: typed task catalog with no recursive delegation. Alternatives: autonomous swarm. Consequences: fewer flexible but opaque behaviors. Migration trigger: new proven task class with contract, budget, evaluation and owner.

**ADR-014 Separate production API provisioning.** Context: founder chat subscriptions are not service credentials. Decision: provision and budget supported OpenAI/Anthropic API projects independently; verify entitlement. Alternatives: reusing personal chat sessions for unattended automation. Consequences: explicit API cost and data policy. Migration trigger: only a provider-supported commercial arrangement with equivalent controls.

**ADR-015 Remote-send safety gate.** Status: **OPEN FOR PROVIDER PREFLIGHT, REQUIREMENT RETAINED**. Context: local suppression cannot atomically control a SaaS queue. Decision: live outbound remains disabled pending EXC-001 proof or provider replacement. Alternatives: weaken promise through explicit founder exception; custom sender rejected. Consequences: research/sales prep can launch before sending. Migration trigger: sequencer fails required stop/cancellation tests.

**ADR-016 Early control UI.** Context: controls must be reviewable before automation. Decision: foundation includes auth shell; runtime includes Health; policy includes Approvals/Attention; Phase 12 expands views. Alternatives: full UI only after integrations. Consequences: earlier end-to-end review, small additional frontend work. Migration trigger: none; refine product after actual use.

**ADR-017 Workspace-local identity and restricted sharing.** Context: own acquisition, clients and partners have different data rights. Decision: independent UUIDs and explicit share/copy records. Alternatives: universal person graph. Consequences: intentional duplication and conservative aggregation. Migration trigger: approved shared-controller model with new privacy/isolation design.

**ADR-018 Versioned frozen campaign manifests.** Context: template approval alone does not approve changing facts/targets. Decision: approve rendered recipient messages and exact scope; new content requires new grant. Alternatives: unrestricted runtime personalisation. Consequences: larger manifests, deterministic auditable release. Migration trigger: evaluated dynamic-content policy with independently bounded claim generation and explicit founder acceptance.

## Migration contracts

Every migration freezes new affected effects, exports permitted source data/mappings, validates target reads, rehearses on staging, records a cutover timestamp/owner and retains rollback evidence. Never run two active sequencers for the same contact.

| Move | Preserved contract and sequence | Cutover gate |
|---|---|---|
| Supabase→standard PostgreSQL | Export SQL/data, verify extensions/RLS, move schema; separately replace Auth issuer while preserving principal UUID mappings | Tenant/restore/performance tests pass; sessions reauthenticated; no bypass keys |
| Pipedrive→other CRM | Map fields/stages/owners/custom UUIDs, shadow-read and compare; stop old commercial writes then activate new adapter | Counts, values, next actions and ID references reconcile; source authority date recorded |
| Smartlead→other sequencer | Stop new enrolments, stop/reconcile active sequences, export suppression/history; migrate only completed/stopped contacts with fresh grant | No uncertain old effect, confirmed provider stop, new safety gate passed |
| Apollo→other source | New source rights, field/evidence mapping and enrichment cost; keep historical provenance | No silent licence transfer; sample coverage/identity checks pass |
| OpenAI→other provider | Same task/context/result contracts; new approved data policy, price config and evaluation | Quality/safety holdout and cost caps pass; no unapproved context transfer |
| Anthropic→other provider | Same route-level method; avoid provider-specific fields in domain | Promotion decision and rollback route available |
| n8n→Temporal | Move one workflow type at a time; preserve command/effect keys and authority records; drain old triggers | Replay in effect-disabled mode matches; one owner of each workflow instance |
| Render→other hosting | Container/runtime config, env references, domain/webhooks and independent monitors moved; DB unchanged initially | Health, secrets, persistent worker, drain/restart and callback tests pass |

