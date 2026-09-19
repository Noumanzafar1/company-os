# ADR-024 — Governed AI requests and isolated provider execution

Status: implementation proposal under explicit Phase 6B Gate A authority;
independent review required. Extends ADR-007/009/014/021/022/023.

AI is a proposal port. Only the closed synthetic gateway task executes in this
phase. Context, routes, prompts, schemas, prices and datasets are immutable.
Lifecycle pointers and append-only results preserve every prior version. Current
membership, resource permissions, source rights, policy and deadlines are checked
before each call and again before output admission. Untrusted content is a labelled
data section; it cannot configure a provider, tool, route, budget or destination.

The existing PostgreSQL job runtime owns leases, fences and reserved safety
capacity. AI work uses normal slots. The Phase 6A supervisor contains a fixed trusted
provider runner; no database credentials, ambient environment or executable tool
capabilities enter it. This is not a hostile-code sandbox. Bounded typed IPC is
extended for AI context and normalized output. Raw provider errors, hidden reasoning
and request headers are never persisted or logged.

Real SDK translation is confined to the AI provider module. Official `openai` and
`anthropic` Python SDK dependencies are added to the one hashed lock. Both use
max_retries=0, explicit HTTP timeouts, fixed first-party HTTPS endpoints, disabled
environment proxies/redirects, no tools, and local schema/evidence validation.
OpenAI Responses uses store=false; that is not a claim of zero provider retention.
Account-specific data policy, region, entitlement, limits and pricing fail closed
until a dated preflight report and separate live spending authority exist.

For a separately authorized live implementation, the parent must resolve only the
selected credential reference after live prechecks.
If enabled in a separately authorized future preflight, the one required key is
delivered once over the contained runner's anonymous stdin, separately from the
execution envelope. It never enters argv, inherited environment or disk. Only
fixed trusted runner code can consume it; it is unavailable to context/tools.
Gate A runtime dispatch is fake-only. Its implemented separate stdin channel
accepts only an explicitly selected synthetic credential and a fixed no-network
SDK probe; it cannot be used to enable live calls. Offline SDK tests inject a mock HTTP transport
and synthetic credentials; no real account is contacted.

Each chargeable attempt has a unique immutable request key and a durable start
before launch. Phase 4 reservations cover pessimistic input/output across bounded
repair/fallback and workspace/company caps. Unknown/invalid usage or process loss
retains maximum exposure; no automatic retry of an uncertain request. A repair is
a separate recorded call, at most once, only for repairable format failures.

Promotion binds the entire route, evaluation dataset/result, prompt, schema,
context policy, task and price version through human authority. Only fake technical
routes may be active. Production promotion always returns
FOUNDER_LABELLED_DATASET_REQUIRED and requires a later authorized workflow phase.
No real provider key, subscription or successful smoke call activates a route.

Operational records use existing R3 conventions. No vector store, generic AI
memory, new broker, new runtime owner or alternate migration history is added.

The worker uses a narrow security-definer Boolean predicate owned by the existing
company_auth role to confirm the selected workspace's active state and epoch; it
receives no new SELECT grant on workspace or membership tables. Model-call inserts
also bind the route/provider/model/price/prompt, active job lease and reservation
in PostgreSQL. Applied revisions are corrected with subsequent revisions.

Synthetic document/evidence fixture records are scoped and separately revocable.
They are not a general document ingestion or retrieval system. Tools and actions
are empty closed tuples in this phase; there is no model-driven resource fetch.
Daily/monthly synthetic budget rows have calendar periods and deny work once no
current provisioned period exists. No automatic paid budget renewal exists.

## Independent-review corrections (Gate A)

Migration 0026 adds no tables or duplicate context bodies. The immutable
`ai_evaluations.batch_id` references immutable batch run IDs; each run's immutable
identity references an immutable ContextPack containing source versions, hashes,
permission epochs and requester identity. Both frozen cohorts are checked against
the dataset's ordered cases and exact route IDs. This is the durable input manifest.

`ai_evaluation_inputs` is a fixed-search-path, scoped security-definer helper owned
by the existing NOLOGIN company_auth role. It takes the existing workspace authority
advisory lock, then shared row locks in a fixed order: workspace, sorted principals,
sorted memberships, sorted service identities, policies, route states, sources,
provider connections. No API/worker table grants change. The non-login helper owner
receives SELECT on the relevant AI tables with a membership-scoped RLS policy and
UPDATE privileges only where PostgreSQL requires them for FOR SHARE. It never writes
these rows. Runtime roles cannot assume company_auth. This preserves FORCE RLS and
avoids giving workers identity-directory or configuration mutation privileges.

Current workspace/epoch, membership/service expiry, source rights/state/expiry,
evidence version, document permission epoch, context expiry, policy, route and
registry hashes/configuration are rechecked. Completed evaluation evidence uses its
ContextPack expiry; the old task execution deadline does not expire a completed
sample. No new inference may bypass its ordinary execution deadline. Finalization
keeps stale samples in the original denominator and records STALE_EVALUATION_CONTEXT;
either cohort's staleness forces technical_fail. Proposal and promotion return
EVALUATION_STALE. Existing exact Phase 5 guards remain, with additional checks on
approval-use insertion, activation and a deferred activation check at commit.
Shared locks serialize revocation; history is never rewritten after a completed
activation. Populated evaluation history blocks downgrade to 0025; restore a matched
baseline backup if rollback is required. Empty-schema migration round trips remain
supported.

The explicit Anthropic client has a closed constructor accepting only the selected
key, timeout and HTTP client. Pinned anthropic 1.7.0 uses exact type identity in
`_client._is_base_client`; the subclass skips its default-credentials chain and
`_warn_env_shadow` home/profile probe. A regression intercepts both functions and
positively demonstrates the base class does enter the warning probe with an explicit
key. This is a tested pinned-SDK dependency, not a general property of inheritance.
The contained child still strips parent environment, receives the synthetic key
only after containment, uses trust_env=False and a fixed no-network mock transport.
The probe asserts its actual minimal environment. Canary tests cover parent keys,
profile/config files and variables, HOME/USERPROFILE/APPDATA/XDG paths, request body,
response and captured logs. The child has no database credentials or audit writer.
SDK upgrades must reverify these assumptions. Live-provider behavior remains untested.
