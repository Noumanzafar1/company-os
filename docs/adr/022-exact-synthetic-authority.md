# ADR-022 — Exact synthetic authority over the Phase 4 runtime

Status: Phase 5 architecture accepted in principle (PASS WITH FIXES); bounded
independent-review corrections await acceptance. No provider, dependency,
production or Phase 6 authorization.

Preserve the shared application boundary and the canonical effect owner. DATA-046
is physically separated into immutable scope fields on a versioned request,
immutable target joins, immutable human decisions, and immutable manifests.
DATA-047 has append-only use reservations and separate one-time outcome records.
Uncertain effects keep their reservations; only confirmed/rejected/cancelled
effect state can prove consumption/non-use. Historical uses are never rewritten.

The closed action registry contains deterministic calculation, internal action,
single synthetic material action, batch synthetic material action and a human-only
L4 rejection demonstration, plus the canonical L3 `policy.activate` action.
Exact previously granted execution is L2; granting
new material scope is L3. L4 has no runtime route. No future provider actions are
registered. A typed policy can narrow limits; it cannot remove MFA or safety rules.

Synthetic targets are explicitly labelled fixture objects, not Accounts or
Contacts. They expose version, rights and protective suppression conditions for
authority tests. Real contact eligibility, controller-wide suppression and
provider enforcement remain later-phase contracts. Existing Phase 3 deny-only
scaffolding is retained. No fake flag can enable a real provider.

The old Phase 4 runtime fixture endpoint remains an offline technical diagnostic:
it accepts only a scenario and an ASCII logical key, and cannot carry business
payloads, recipients, destinations or provider configuration. Governed synthetic
requests carry exact target and payload snapshots through `authority_bindings`.
The binding joins immutable runtime input to manifest; uses join the sole canonical
job/effect. Followers cannot acquire independent dispatch or reservation authority.
The nullable future provider authority columns in the accepted Phase 4 effect row
remain unused; the new composite-FK binding is the durable authority reference.

DATA-045 specifies policy activation invalidating prior outstanding approvals.
Validation therefore requires the current active version, its effective window,
and current requester/approver membership. `policies/propose` first freezes a
typed candidate and evaluates the current `policy.activate` policy. The existing
request, human decision, manifest and use tables carry its authority: the snapshot
binds policy ID, record version, old active pointer, candidate ID/version/hash,
exact rules, effective/expiry bounds, workspace, approver, approval expiry and
one use. A fresh verified founder MFA decision grants that exact candidate.
`policies/activate` requires its manifest, decision and candidate, consumes one
use, updates the pointer and records the event/audit in one transaction. Same-key
HTTP retries return the original receipt; a new command cannot reuse the grant.
MFA alone and service or administrative status confer no activation authority.
The existing protective null-pointer contraction cannot authorize a replacement.
An append-only workspace/action freeze blocks new governed
commitments. There is deliberately no implicit expiry or automatic unfreeze;
recovery/reconciliation continues. A reviewed unfreeze command is future work.

Use limits, simulated spend and aggregate target volume serialize under a scoped
PostgreSQL advisory gate, alongside the existing Phase 4 budget reservation
transaction. Freeze and activation use the same gate. Target row locks close
version/safety races. Budget capacity never creates authority. A narrow fixed-path
function owned by existing NOLOGIN `company_auth` takes validation locks under
explicit context-bound RLS. Workers receive no UPDATE on approval requests and
cannot grant, change policy, add targets or create bindings. No new privileged
runtime role is introduced.

Correction migration 0018 preserves the prior validator behind a non-public
wrapper and performs a final `clock_timestamp()` check after target validation.
It rechecks manifest bounds, policy bounds/current pointer and request state.
The fake acceptance application boundary repeats only this lightweight temporal
check after full validation and budget checks. Final SQL guards also check time
after use accounting and at dispatch/receipt insertion. The shared authority
gate and acquired locks remain held. Target-lock and accounting-barrier tests
prove expiry denial while blocked; no reliance on a slow cohort or timing luck.

Approval list/detail admits the founder or the exact server-derived requester;
other same-workspace humans receive non-disclosing 404s for detail. Service and
system-only roles cannot enter human review. Worker RLS validation access remains
separate. Pure evaluation receives the complete frozen set of current roles and
uses intersection with permitted roles; role array ordering is immaterial.

Canonical hashes use sorted UTF-8 JSON with no insignificant whitespace over
closed value types. SQL independently verifies cohort, payload and manifest
hashes and matches binding scenario/namespace. The manifest contains material
bounds and exact references; its generated creation time is outside the scope hash
per SEC-006. It is immutable nonetheless. JSON number inputs are bounded integers;
money is a decimal string, avoiding binary floating-point authority comparisons.
New manifest expiry strings normalize to UTC before hashing; the immutable stored
scope is returned without changing its timestamp representation.

Approval events enter the existing events/outbox/receipt path. Their typed guard
checks the exact request state/version/payload. Existing runtime validators remain
unchanged for all prior aggregates. An event or decision result never grants
execution by itself. The API and worker recheck immediately before commitment.

The offline MFA browser demonstration signs a short-lived asymmetric fixture and
uses the existing verified identity/session boundary. Its storage state is ignored
local test material. Ordinary synthetic sign-in remains aal1. Production auth and
account MFA preflight are unchanged and no production login bypass is added.

Retention uses existing operational R3 metadata conventions; no erasure worker or
new retention policy is introduced. Performance is bounded local synthetic evidence,
not a production-capacity or remote-provider guarantee. Long-handler timeout debt
in ADR-021 remains a HARD prerequisite before Phase 6 real model/network workloads.
The original approximately 1.66-second 200-target validation measurement remains
tuning debt before high-volume/network authority execution; this correction
establishes temporal correctness without a new policy engine or infrastructure.
