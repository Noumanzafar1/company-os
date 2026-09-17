# Company OS Phase 1 Technical PRD and Implementation Specification

Prepared for Nouman • 16 September 2026 • Specification version 1.0

**Decision:** The design is ready for review and a separately authorised Phase 2 foundation build. Live outbound is blocked until the sequencer's suppression, cancellation and reconciliation guarantees are demonstrated. No application, migrations, deployment or provider accounts have been created in this phase.

This specification translates the complete supplied **Company Operating Architecture** into engineering contracts. The supplied **Pasted markdown** is the governing Phase 1 brief. References to the source report use its Part numbers and subsection names. Where this specification differs, the consistency register records the change. Legal formation, banking, taxation and registrations are parked. Software retains legal-entity and contract references without choosing a jurisdiction or entity form.

Normative language: **MUST** is an acceptance condition; **SHOULD** permits a documented engineering exception; **MAY** is optional. All operating thresholds and cost ceilings below are proposed internal policies, not measured performance, vendor prices or legal conclusions. Provider documentation was checked during this phase; no authenticated account capability tests were performed. **IMPLEMENTATION PREFLIGHT REQUIRED** means documentation does not establish the actual account entitlement or operational guarantee.

The 30 Parts follow the requested sequence. Schema, API and diagram examples are design contracts, not production implementation. IDs are stable within version 1.x; never renumber an existing requirement to accommodate a new one.

# Part 1 — Executive Technical Summary

Company OS is a private web console backed by an always-on application, durable PostgreSQL records and bounded workers. It researches authorised accounts, prepares outreach, monitors provider activity, prepares sales and client work, and presents decisions to the founder. It continues permitted work when the laptop is closed. Work requiring a new approval waits durably.

Use Next.js and TypeScript for the console, Python/FastAPI/Pydantic for the API and worker, Supabase PostgreSQL and Auth, Pipedrive for commercial state, Google Drive for documents, Apollo for authorised research, ZeroBounce for verification and Smartlead for sequencer execution if its live-sending gate passes. Use n8n Cloud selectively for integration triggers and notification delivery. PostgreSQL owns schedules and workflow progress. n8n is not on the critical suppression path.

The implementation is a **modular monolith**, deployed as a console service, API service and worker service from one repository. These are process roles with shared contracts, not independently owned microservices. The worker invokes the same application command handlers as the API; it cannot bypass policy because it is an internal process.

Six AI worker roles produce typed proposals. They do not own company state, release campaigns, sign contracts, move money, change permissions or execute arbitrary code. Model/provider selection is a versioned configuration backed by evaluation. OpenAI and Anthropic adapters remain distinct; their request formats are not assumed interchangeable.

Five architectural decisions govern the rest of this document:

1. **One owner per field.** PostgreSQL owns operational identities and controls; Pipedrive owns accepted commercial fields; Drive owns document bytes. Local projections are labelled and timestamped.
2. **Every consequential action has an authority record.** Bind approvals to frozen recipients, exact content, versions, sender, schedule, limits, policy and expiry. Revalidate before dispatch.
3. **Durability is explicit.** Transactional outbox, webhook inbox, consumer receipts, leased jobs and external-effect records handle retries and restarts. Delivery is at least once; external exactly-once execution is not promised.
4. **Client boundaries exist everywhere.** Scope database rows, provider accounts, document folders, caches, context packs and reporting. A shared CRM pipeline or an email address does not create a tenant boundary.
5. **Uncertainty changes behavior.** Ambiguous sends do not retry blindly; stale approvals cannot execute; absent data is unknown; unsupported claims remain drafts; provider outage can cause protective suspension.

A useful first vertical slice is: authorised account → sourced facts → reproducible fit score → founder inspection. It requires no live email sending and does not require a completed CRM integration. Build the small Attention, Approvals and System Health interfaces early, then expand them as workflows become usable.

**Authority hierarchy:** this specification defines the application design; approved workspace policies configure business behavior; a narrowly scoped approval authorises an instance. A policy or approval cannot waive a hard architectural control. Founder decisions can approve an architecture exception through a revised specification, never a hidden runtime flag.

# Part 2 — Architecture Consistency Review

| ID | Issue | Source architecture | Why it matters | Resolution | Blocks implementation |
|---|---|---|---|---|---|
| ARC-001 | Source roadmap Phase 1 means legal setup; present brief Phase 1 means technical design | XVII roadmap | Coding tools could build the wrong phase | This document's Phase 2–14 numbering governs engineering only; source business roadmap remains separate | Resolved |
| ARC-002 | Source recommends validation before custom build; current instruction requests machine design first | I, VII, XVII | Design can become an implied spending or launch approval | Produce full design now; retain separate funding, data-rights and live-execution gates | No foundation block |
| ARC-003 | Identity can originate in CRM but becomes database-owned | VIII ownership and migration | Two writers can oscillate fields | Start new build with PostgreSQL identity ownership; import existing CRM identities through one reviewed bootstrap; CRM edits become correction proposals | Resolved |
| ARC-004 | CRM lead and operational lead are similarly named | VIII, XIII CRM specification | Stage transitions can become dual-master | Operational Lead tracks research/qualification; CRM Lead/Deal projections track commercial acceptance; no automatic equality | Resolved |
| ARC-005 | Campaign definition and execution ownership overlap | VIII ownership | Provider edits could silently alter approved copy | Immutable local campaign versions own intended configuration; provider owns observed execution. Drift pauses affected work | Resolved |
| ARC-006 | Immediate opt-out conflicts with remote scheduled sends | VI outbound, X recovery, XII monitoring | A database lock cannot cancel remote mail already being dispatched | EXC-001 below; provider execution contract and adversarial tests required | Live outbound blocked |
| ARC-007 | “Service identity” plus RLS may imply a bypassing Supabase service key | VII, XII | Server-side key placement alone does not ensure tenant isolation | Custom runtime DB roles without BYPASSRLS; no service-role key in routine API/worker | Resolved; verify Phase 2 |
| ARC-008 | Shared person/domain deduplication could cross clients | II populations, VIII identities | Data rights and relationships leak | Duplicate real-world entities may have separate workspace UUIDs; no tenant-wide person master | Resolved |
| ARC-009 | Domain uniqueness conflicts with subsidiaries/shared domains | VIII identity rules | Incorrect merges and misdirected campaigns | Nonunique domain search index; explicit domain-claim identity key with discriminator and reviewed merges | Resolved |
| ARC-010 | Missing effect and budget-reservation objects | VIII entities, X retries | Job dedupe alone cannot prevent uncertain resend or overspend | Add external_effects, approval_uses, budget_reservations, usage_entries and quota buckets | Resolved |
| ARC-011 | Approval hash does not specify personalised content or audience changes | XI approvals | Generic template approval could allow new claims or recipients | Freeze cohort and per-recipient rendered messages or a closed approved content manifest; V1 uses frozen rendered messages | Resolved |
| ARC-012 | Source model names and prices are configuration suggestions | IX, XIV | Display names may not be callable API IDs; prices can change | Resolve model IDs, support and prices during preflight; pin evaluated configuration; no provider billing assumption | Preflight Phase 6 |
| ARC-013 | Ordinary n8n workflows can bypass policy with vendor credentials | VII, X | A second send path defeats the control plane | n8n submits commands, has no sequencer-send credentials and cannot approve work | Resolved |
| ARC-014 | Finance numbers are expected before a ledger integration exists | XI daily brief | Pipeline value can masquerade as cash | Nullable finance projection with explicit unavailable/stale states; no invented cash or revenue | Resolved |
| ARC-015 | Four-hour operational RPO conflicts with daily-only backup | XII recovery | Data loss can repeat external effects | Paid recovery option or independently tested ≤4-hour capture before live release; reconcile providers before replay | Preflight Phase 14 |
| ARC-016 | Client approval is described but only founder user exists | II offer, XI | Founder approval might be mistaken for client authority | Client authority evidence references exact scope/version; founder records it; no client portal required | Resolved |
| ARC-017 | Local tenant checks do not isolate shared SaaS access | XII, XIII | Client users could see other clients in CRM/Drive | Separate provider account or demonstrated native isolation; no client access to founder CRM | Preflight per client |
| ARC-018 | Commercially won does not mean paid or accepted delivery | V, XIII | Automation could start unfunded obligations | Separate Opportunity, Contract, PaymentGate, Engagement and Deliverable acceptance | Resolved |
| ARC-019 | Webhook age alone is a poor health measure | XI, XII | Quiet campaigns appear broken; missing events appear healthy | Use poll/synthetic heartbeat, reconciliation watermark and divergence, not last event time alone | Resolved |
| ARC-020 | Global suppression could disclose another client's contacts | VI, VIII | Safety check becomes an identity lookup oracle | Restricted HMAC match service returns blocked/clear/unknown only for owned contacts; no provenance exposure | Resolved |
| ARC-021 | A 100-case AI evaluation is too small to infer safety | IX evaluation | Perfect small-sample scores overstate reliability | Keep seed dataset, add dedicated adversarial slices; hard deterministic stops; report sample size and uncertainty | Resolved |

**EXC-001 Remote send boundary.** Current rule: a prospect opting out one second before a scheduled follow-up must block that send. Technical problem: Smartlead owns its queue; Company OS cannot transact atomically with that queue or observe an email reply before the provider delivers it. Alternatives: (a) require documented and tested native stop guarantees at the execution boundary; (b) choose a provider with a pre-dispatch authorisation/cancellation contract; (c) loosen the guarantee through explicit founder-approved exception. Recommendation: retain the requirement, keep outbound disabled until (a) or (b) is satisfied, and do not implement (c) silently. A manual send is not a solution to this distributed race. A send already irreversibly handed to a mail transport cannot be recalled by this design. Tests distinguish opt-out receipt, persistence, provider confirmation and irreversible dispatch times. No universal end-to-end one-second guarantee is claimed from the documentation reviewed.

**EXC-002 Early control screens.** The source places the full console late. Approval and failure handling must be reviewable before outbound. Build minimal control screens in Phases 2, 4 and 5; Phase 12 adds broader operating views. This changes delivery order, not the chosen frontend or authority model.

# Part 3 — Scope of Company OS V1

V1 supports the company's acquisition workspace, isolated client campaign workspaces and a separate partner workspace. Initially only the founder signs in. Roles and workspace membership are foundational so later employees can take over existing tasks.

| Capability | V1 completion boundary | Explicit exclusion |
|---|---|---|
| Intelligence | Accounts, people, employment, source rights, evidence, signals, ICP and reproducible scores | Broad web crawler, inferred private data, LinkedIn automation |
| Prospect operations | Licensed discovery, verification, permission assessment, suppression and reviewed identity corrections | Email guessing as verified identity, data resale |
| Campaigns | Versioned offer/ICP, frozen cohorts, drafts, QA, exact approvals, controlled provider enrolment | Generic visual sequence builder, live AI-written follow-ups |
| Replies and sales | Immediate stop, classification proposals, tasks, CRM projection, calendar sync, meeting packs, proposal preparation | Custom inbox, autonomous negotiation or contract signature |
| Client operations | Onboarding gates, milestones, risks, accepted evidence, status drafts, closure checklist | Full project management suite or client portal |
| Platform | Jobs, events, policy, budgets, AI evaluations, audits, recovery and health | Microservices, Kafka, Kubernetes, autonomous agent swarm |
| Founder experience | Attention, Approvals, Health first; linked Pipeline, Leads, Campaigns, Clients, Knowledge and AI views later | CRM replacement, accounting editor, mobile app |
| Finance | Cost attribution and optional reviewed financial snapshots with authoritative references | Ledger, payroll, banking, money movement, tax calculation |
| Partner work | Capability record and disclosed referral linkage | Prime-contract delivery automation without separate commercial readiness |

All integration code initially uses fake adapters and synthetic data. A finished integration remains disabled until account preflight and its release gate pass. Signing up for a vendor, spending money, sending messages, scheduling real meetings and granting external access are not authorised by this specification alone.

**NFR registry — measured at initial test load of 5 workspaces, 50,000 accounts total, 100,000 people total, 10 concurrent users and 10,000 ordinary jobs/day.** This is a capacity test envelope, not a demand forecast.

| ID | Requirement and measurement |
|---|---|
| OPS-001 | No accepted job, approval or committed event lost on one API/worker restart. Prove through crash tests, not uptime claims. |
| OPS-002 | Internal read API p95 <750 ms and command acknowledgement p95 <1 s under test load, excluding vendor/AI execution; Attention usable within 2.5 s on a simulated ordinary broadband connection. |
| OPS-003 | Safety jobs begin within 5 s p95 while DB is healthy; normal ready jobs within 60 s p95. Alert if safety queue oldest age >10 s or ordinary queue >5 min. |
| OPS-004 | Critical webhook persisted within 1 s p95. Reply/suppression divergence >2 min is amber; >5 min or any confirmed violation is red. Target provider confirmation <60 s, without claiming a provider guarantee. |
| OPS-005 | CRM and Calendar reconcile every 5 min; active sequencer safety reconciliation every 60 s if account quota permits. Otherwise reduce active load or block launch, not secretly weaken the threshold. |
| OPS-006 | Every external effect and privileged command has actor, scope, authority, version, effect key and outcome records; audit completeness is 100% in acceptance fixtures. |
| OPS-007 | Internal research RPO ≤24 h; live operational RPO ≤4 h; restore within one business day in a timed drill. Reconciliation and safety checks are required before sending resumes. |
| OPS-008 | Reserve maximum billable cost before dispatch. Unknown billed outcomes keep reservations. 80% budget warning; 100% stops new discretionary consumption. |
| OPS-009 | Provider failure preserves state and surfaces age/reason. A deterministic 08:00 Asia/Karachi brief remains available without AI. |
| OPS-010 | All critical control tests pass; no skipped isolation, authority, suppression or duplicate-effect tests. Coverage target ≥85% branches for policy/state/budget code, with targeted failure tests more important than aggregate coverage. |
| OPS-011 | Working target 99.5% monthly console/API availability after launch, no contractual SLA. Report planned maintenance and dependency outages separately; observed availability starts only after monitoring exists. |
| OPS-012 | One engineer can trace an effect from command to provider receipt in <10 min using saved IDs; a new operator can resume an open task from its record and linked SOP. |

