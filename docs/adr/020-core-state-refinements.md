# ADR-020: Bounded Phase 3 state contracts

Status: implementation proposal within authorized Phase 3; independent review pending.

Preserve ADR-001–019 and the numbered specification. Phase 3 has synchronous
local commands, atomic audit and command receipts; no event/outbox/job runtime.
Receipts implement API-001 idempotency, not effect dispatch. Existing-target
commands lock and compare versions. Receipts never bypass current authorization.

Resources register only the Phase 3 aggregate types actually referenced by
heterogeneous subjects: Account, Person, Lead and Document. All other references
use typed tenant FKs. A deferred trigger validates the exact registry/child pair.

DATA-044 is limited to immutable human decision records for identity merge,
reversal and synthetic knowledge review. There are no approval grants, manifests,
uses, budgets or policy engine. Merge/reversal requires founder permission and
the existing recent-MFA guard. The user approved offline verified-MFA fixtures
for tests; development sign-in continues to provide aal1 only.

Identity corrections are durable conflict records instead of DATA-043 Tasks:
the Phase 3 API-006 subset records the proposal and an identity hold; the shared
task workflow is deferred. Merges preserve historical child attribution and
redirect the retired identity. No external mappings or enrollment tables exist.
Reversal is a new record, preserves the merge, and places identities/contacts
on hold for rechecking. It cannot confer eligibility.

Document metadata uses a closed fake-local store identifier in place of a
provider connection FK until provider connections are authorized. Bytes remain
owned by that adapter; metadata and derived search text remain in PostgreSQL.
Source rights evidence links to immutable document versions. Source approval and
knowledge review are synthetic seed inputs; no generalized promotion API exists.
ICP and Offer versions remain drafts, with no activation endpoints.

Permission/suppression scaffolding is workspace-local and deny-only. There is no
eligible permission assertion, release, global matching or sending capability.
Contact validity, outreach permission and suppression remain separate fields/
records. No verification result is fabricated.

No dependency or production data-ownership change is proposed. All refinements
must be independently reviewed with the Phase 3 handoff before commit/push.

## Independent-review corrections (17 September 2026)

The review authorized five bounded fixes. Revision `0005_phase3_review_fixes`
adds two immutable, tenant-scoped join tables: `score_input_evidence` retains the
entire submitted evidence set, including exclusion-only or currently unusable
inputs; `score_signals` records the exact accepted Signal UUID, version, status,
expiry and evidence reference used for trigger support. Composite tenant FKs,
subject/snapshot guards, FORCE RLS, actor guards and append-only enforcement apply.
Workers receive no new grants. Migrations 0003 and 0004 remain unchanged.

A read-only evaluator is shared by score creation and current-support validation.
The versioned hash includes Signal dependencies plus the existing account,
immutable ICP/rubric, evidence validity and source versions. Retrieval recomputes
using the persisted input evidence set and compares the hash. This also detects
changed evidence-derived exclusions, contradictions and previously missing Signal
support. Disqualification uses the same freshness check. Deterministic exclusions
remain explained by the account/version and immutable ICP definition. No events,
scheduler or background invalidation are introduced. Recalculation appends/reuses
an immutable result. Scores created before this correction have dependency version
zero and report non-current: their original full input set cannot safely be
reconstructed, so history is not rewritten or guessed. Explicit rescoring creates
a version-one result. Read-time evaluation increases query work; scale tuning is
outside this bounded correction.

Fact comparisons now preserve the declared type, canonical value and unit, and
known scoring keys enforce their expected string/integer/boolean type. Mixed or
contradictory observations yield unknown. Reversals validate every supplied evidence
record against both reviewed identities and the existing current-evidence rules
before recording a decision. Contact creation adds an unknown email assessment
only for email identities; no other channel system is added.

Signal creation rejects future observations and observations earlier than their
supporting evidence. A database trigger applies the same chronology constraint to
inserts/updates, and the existing expiry constraint remains. Future event dates
are allowed. Existing historical Signal rows are not rewritten; any subsequent
write must satisfy the invariant.

The review-only cleanup removes the unused `DocumentInput.purpose` field: document
registration creates metadata, not a purpose-specific authorization. Supplying the
removed field now fails the closed contract. Source purpose enforcement remains
unchanged. Signal acceptance now stores `acceptance_reason` on the versioned Signal
and exposes it in the read contract. Legacy acceptance reasons remain null; the
implementation does not fabricate past reasoning. These are bounded contract
corrections, not a general decision/approval engine.
