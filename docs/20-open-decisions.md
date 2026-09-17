# Part 30 — Open Decision Register

No ordinary choice of framework, queue, ORM or frontend is left for the founder. The unresolved matters below involve actual account capabilities, business authority or release risk.

| ID / class | Question and why it matters | Owner and deadline | Temporary assumption and safe fallback |
|---|---|---|---|
| DEC-001 BLOCKER for live outbound | Can selected sequencer satisfy EXC-001 stop/race, expiry and queue guarantees? | Technical owner + provider; P10/P14 | All send flags false. Build fakes/research/CRM; replace provider or seek explicit architecture exception if impossible |
| DEC-002 PREFLIGHT | Do chosen Apollo accounts permit these endpoints and own/client use, retention/export? | Founder for rights, technical owner for endpoints; P7/P8 | No client sharing assumed; fixtures/permitted public research |
| DEC-003 PREFLIGHT | Which Smartlead plan/account exposes stop/history/authenticated callbacks/client isolation/caps? | Technical owner/provider; P10 | No live adapter enabled; exact capability report required |
| DEC-004 PREFLIGHT | Pipedrive auth, scopes, fields, webhooks, testing and conflict controls supported on account? | Technical owner; P11 | Fake CRM; native reviewed CRM use without claiming automatic control |
| DEC-005 PREFLIGHT | ZeroBounce credentials, credits, statuses, limits and data policy verified? | Technical owner; P8 | Sandbox addresses/fake verification, real contacts ineligible |
| DEC-006 PREFLIGHT | Which API model IDs, structured outputs, prices, region and retention policy are available? | Technical owner with founder data-policy approval; P6 | No real client context; fake routes/evaluation fixtures |
| DEC-007 PREFLIGHT | Google OAuth scopes and Drive/Calendar permission/version/export behavior on selected accounts? | Technical owner; P7/P11 | Synthetic documents/calendar, no public shares or broad OAuth scope |
| DEC-008 PREFLIGHT | Paid hosting, DB recovery, Auth MFA and connection capacity at acceptable cost? | Technical owner supplies quote; founder approves envelope; before paid staging/P14 | Local build, no operational SLA or live release |
| DEC-009 BLOCKER for production operation | Who owns alerts, release/recovery and emergency access when founder is unavailable? | Founder; P14 | Protective stops and queued approvals, no implied delegate or autonomous commitments |
| DEC-010 BLOCKER for real campaigns | What actual offer/ICP, sender identity, authorised region policy, recipient basis, proof and client authority are approved? | Founder with appropriate adviser/client; P9/P14 | Synthetic policy fixtures only; no inference of legal permission from this blueprint |
| DEC-011 BLOCKER for paid dispatch | What daily/monthly company and workspace spend caps are funded? | Founder; before first paid integration use | Zero live budgets; suggested per-task caps do not authorise charges |
| DEC-012 PREFLIGHT | Is n8n materially useful and what account limits/auth/retention apply? | Technical owner; when first connector workflow is justified | Keep correctness in direct worker; defer subscription |
| DEC-013 PREFLIGHT | Can provider-native access isolate future client users and employee roles? | Technical owner/client admin; before each client onboarding | Founder-only native access; separate provider account if needed |
| DEC-014 DEFERRED | Which accounting source and invoice/payment projection will be integrated? | Founder/accountant; future finance increment | Finance unavailable or reviewed source snapshot; no accounting writes |
| DEC-015 DEFERRED | When should pgvector, Temporal or dedicated tenant DBs be added? | Technical owner; measured trigger in ADRs | SQL/full-text, bounded DB jobs, RLS with explicit isolation tests |
| DEC-016 DEFERRED | Which future legal entity owns a given contract/invoice? | Founder/professionals; before actual contracts | Unconfigured LegalEntity reference; no chosen formation route in software |
| DEC-017 BLOCKER for retention activation on real data | Are source/client retention, legal holds and global suppression scopes authorised? | Founder/data owner; before real imports | Conservative workspace-local processing; proposed defaults only, no blanket controller-wide sharing |

These are not a list of questions the founder must answer now. Phase 2 has no unresolved technical selection blocker. Later integrations may be implemented against closed ports and fake adapters while their capability tests are prepared. A preflight becomes a blocking gate before the affected capability handles real data or effects.

## Answers to the ten design tests

| Design question | Answer and limit |
|---|---|
| Laptop closed? | Hosted API/worker/database continue within current authority. Human approvals wait; production never depends on a local chat session. |
| GPT unavailable? | All business state survives. Deterministic processing and brief continue; approved fallback or human work handles language tasks. |
| Claude returns a bad result? | Result is a scoped proposal; hard validators and authority boundary prevent privileged mutation. Semantic errors remain possible and are evaluated/reviewed. |
| n8n restarts? | Jobs, schedules, waits and approvals remain in PostgreSQL; idempotent callbacks prevent duplicate commits. |
| Duplicate Smartlead webhook? | Inbox and consumer dedupe prevent duplicate local effects. Provider-internal duplicates require provider safety tests and incident response. |
| Opt-out one second before follow-up? | Local release is blocked once suppression is known. Universal remote blocking is not proven; EXC-001 explicitly blocks live outbound until resolved. |
| Malicious Client A website requests Client B? | Scoped context/tool API/RLS/egress checks deny access; untrusted content cannot change workspace or permissions. |
| Approve version 3, then edit version 4? | Version/hash mismatch invalidates grant; no version 4 dispatch under version 3 approval. Active native work must also stop/reconcile. |
| Why was an external message sent? | Trace command, frozen manifest, policy, grant/use, eligibility, effect and provider receipt; missing receipt remains uncertainty, not invented success. |
| Can a person take over? | Role-owned task includes SOP, input versions, evidence, attempts, output and pending decision. No months of chat reading required. |

## PHASE 1 TECHNICAL DESIGN STATUS

“PASS” below means the specification defines the contract and acceptance method; it does not mean an implementation has passed tests. “READY” means ready to begin the narrowly bounded foundation phase after founder approval, not ready for production.

| Area | Status | Basis |
|---|---|---|
| Architecture consistency | **OPEN** | EXC-001 depends on provider execution guarantees; all other listed ambiguities resolved in the design |
| Domain model | **PASS** | Explicit identities, ownership, relationships, authority and operational resources |
| Data ownership | **PASS** | Per-field owners and reconciliation; no undocumented dual-master |
| Tenancy model | **PASS** | Composite FKs/RLS, service scoping, provider/file/context boundaries and explicit shares |
| Event design | **PASS** | Envelope, registry, inbox/outbox, consumer dedupe and ordering rules |
| Job design | **PASS** | Leases/fences, retries/waits, scheduling, uncertainty and cost reservations |
| Policy and approval design | **PASS** | L0–L4, immutable manifests, runtime rechecks and bounded use |
| AI gateway design | **PASS** | Typed task/context/result, provider restrictions, evaluations and budgeted fallback |
| Integration contracts | **PREFLIGHT** | Ports specified; actual account capabilities and remote safety behavior not tested |
| Security model | **PASS** | Defined auth/roles/RLS/secrets/egress/audit; implementation tests still mandatory |
| Test strategy | **PASS** | Critical authority/failure tests, real provider gates and honest unresolved race test |
| Deployment design | **PASS** | Managed always-on processes, separated environments, recovery and release design; procurement preflight remains |
| Phase 2 readiness | **READY** | Foundation can be implemented with synthetic data and fake integrations; no later gate is waived |

### Phase 2 Entry Criteria

- Founder approves this Phase 1 design and the bounded Phase 2 scope.
- Assign the repository owner and technical reviewer; use the proposed shared guidance files.
- Record EXC-001/DEC-001 as an open live-outbound blocker, not a failing foundation dependency.
- Use synthetic A/B workspaces, fake provider adapters and zero live sending budgets.
- Confirm development runtime/managed Auth approach and document local startup; do not provision paid production services without the approved budget.
- Implement only Phase 2 deliverables and required tests, then stop with the reviewable handoff.

**Phase 1 ends here. Phase 2 has not begun.**
