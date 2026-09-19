# Phase 6A — Long-running network runtime safety

Explicit founder authorization supersedes the historical Phase 5-only gate.
Accepted Phase 5 baseline: `9d9010f62e890275760eaa7a312ed119f7c28ec0`, verified
after fetching origin; local main equals origin/main and contains reviewed
feature commit `51afcf30dddf79bdc1d775280f9deb151f937964`.
Branch: `phase-6a-network-runtime-safety`. Previous review ZIPs remain untouched.

Implement an enforced child-process execution boundary around existing durable
jobs, leases, fences, authority, budgets, effects and reconciliation. Only closed
synthetic handlers and loopback fake HTTP are permitted. Parent controls deadlines,
cancellation, lease renewal, process cleanup and result admission. Child input and
JSON output are bounded and validated; no secrets or database access are supplied.

Validate cooperative and forced cancellation, CPU/network hangs, malformed IPC,
parent/child death, replacement workers, late results, authority expiry, uncertain
effects, safety capacity, shutdown and Windows process-tree cleanup. Run the full
Phase 2–5 gate plus dedicated faults and record actual performance and OS limits.
Use additive migrations after 0018 only; preserve earlier migration bytes.

Requirements: SYS-001/002/006/007/014/018/019/022/024;
OPS-013–019; SEC-003/006/008/009; TEST-001/004/005/007/009/010/012/027/029/031.
The attached 44-section founder brief governs detailed acceptance. ADR-023 records
the execution extension; canonical Phase 1 design status remains unchanged.

Stop with handoff, manifest and complete review archive for independent review.
No commit, push, PR, merge, deployment, provider integration, credentials, paid calls,
AI gateway or Phase 6B. Any unproven critical acceptance condition means NOT READY.

---

## Complete founder implementation prompt

The following preserves the authorized acceptance criteria for independent review.

# COMPANY OS — PHASE 6A IMPLEMENTATION

## Phase

Phase 6A — Long-Running Network / Model Runtime Safety Gate

Phase 5 has passed independent architectural review, correction review,
protected pull-request CI, post-merge CI, and is formally CLOSED.

Phase 6A is a mandatory safety prerequisite before any real OpenAI,
Anthropic, provider, or other long-running network workload may be
introduced.

This is NOT yet the AI Gateway implementation.

Do NOT integrate OpenAI.
Do NOT integrate Anthropic.
Do NOT use provider API keys.
Do NOT begin Phase 6B.

---

# 1. STARTING GIT STATE

Before modifying anything:

1. Fetch origin.
2. Verify local main equals origin/main.
3. Verify protected main contains the reviewed Phase 5 feature commit:

51afcf30dddf79bdc1d775280f9deb151f937964

4. Record the current protected main SHA as the accepted Phase 5 baseline
   in the Phase 6A brief and manifest.

5. Do NOT develop directly on main.

6. Create:

phase-6a-network-runtime-safety

from current origin/main.

7. Preserve all previous review ZIPs as untracked local artifacts.

8. Do not push the Phase 6A branch.

Independent review is required before commit/push authorization.

---

# 2. GOVERNING AUTHORITY

Read before implementation:

- AGENTS.md
- CLAUDE.md
- docs/02-architecture.md
- docs/05-state-machines.md
- docs/06-events.md
- docs/07-jobs.md
- docs/08-policy-approvals.md
- docs/09-ai-gateway.md
- docs/10-agent-contracts.md
- docs/14-security.md
- docs/15-observability.md
- docs/16-testing.md
- docs/17-deployment.md
- docs/19-implementation-roadmap.md
- docs/20-open-decisions.md
- docs/requirements.md
- ADR-021
- ADR-022
- Phase 4 final handoff
- Phase 5 final handoff

The accepted architecture remains authoritative.

The specific unresolved prerequisite is:

No long-running/provider/AI handler may be admitted until timeout,
fencing and cancellation behavior has been explicitly validated.

Phase 6A exists to close that prerequisite.

---

# 3. OBJECTIVE

Build and prove a safe execution boundary for future long-running
network/model tasks.

After Phase 6A, Company OS should be able to execute a synthetic
long-running handler while safely handling:

- hard timeout;
- cooperative cancellation;
- uncooperative cancellation;
- network hang;
- stalled subprocess;
- worker crash;
- process termination;
- stale lease;
- stale completion;
- replacement worker;
- retries;
- uncertain external state;
- budget reservation;
- authority expiry;
- shutdown;
- orphan cleanup.

The core invariant is:

A timed-out, cancelled, crashed or stale worker must never later become
authoritative again.

---

# 4. ABSOLUTE PHASE BOUNDARY

DO NOT IMPLEMENT OR CONNECT:

- OpenAI
- Anthropic
- any LLM API
- AI Gateway
- AI task routing
- model selection
- prompts
- context packs
- embeddings
- vector database
- Apollo
- Smartlead
- ZeroBounce
- Pipedrive
- Google APIs
- n8n Cloud
- real outbound
- campaigns
- production deployment
- real client/prospect data

No real provider credentials.

No paid API calls.

Use only local/synthetic test workloads and fake network services.

---

# 5. DO NOT REDESIGN PHASES 4 OR 5

Preserve:

- durable jobs;
- leases;
- fencing;
- retries;
- waits;
- dead letters;
- external-effect uncertainty;
- reconciliation;
- budget accounting;
- authority manifests;
- policy enforcement;
- approval use accounting;
- RLS;
- safety lane;
- System Health.

Phase 6A extends the execution boundary.

It must not replace the existing runtime.

---

# 6. THREAT MODEL

Design against these failures.

## Handler hangs forever

Example:

while True:
    pass

or blocking I/O that never returns.

Company OS must regain worker capacity.

## Cooperative cancellation

Handler observes cancellation and exits cleanly.

## Uncooperative cancellation

Handler ignores cancellation.

Runtime must eventually terminate/isolate it.

## Job lease expires

Old execution must not commit.

## Replacement worker claims work

Only current fence may commit.

## Parent worker crashes

Child execution must not become an uncontrolled orphan.

## Child crashes

Job receives truthful failure state.

## Worker shutdown

No uncontrolled children remain.

## Network hangs

Synthetic server accepts connection and never responds.

Timeout must be enforced independently of library goodwill where
necessary.

## Response arrives after timeout

Stale result must not commit.

## External action ambiguity

If the synthetic remote service may have accepted an effect before
timeout, use Phase 4 uncertain-effect semantics.

Do not blindly retry.

## Authority expires during execution

Phase 5 execution rules remain authoritative.

Long computation does not extend authority automatically.

---

# 7. EXECUTION ISOLATION

Determine the smallest robust execution-isolation architecture.

Strongly evaluate running long-running handlers in a child process
rather than inside the worker process/thread itself.

The parent worker should retain control over:

- deadline;
- cancellation;
- lease renewal;
- fence;
- child lifecycle;
- result validation.

The child should receive only a bounded execution envelope.

Do not give child workers unrestricted database credentials.

Do not give synthetic handlers secrets.

If the canonical architecture supports another approach, document the
decision carefully.

---

# 8. EXECUTION ENVELOPE

Define a typed long-task execution envelope containing only what is
required.

Potential fields:

- execution_id
- workspace_id
- job_id
- attempt_id
- fence
- handler_type
- handler_version
- input_reference
- input_hash
- hard_timeout_seconds
- cancellation_grace_seconds
- correlation_id
- trace_id
- authority_reference if consequential
- budget reservation reference where applicable

Do not include:

- database passwords
- authentication tokens
- arbitrary environment variables
- hidden host filesystem paths
- provider secrets

---

# 9. HARD TIMEOUT

Implement enforceable timeout behavior.

The timeout must not depend solely on the handler voluntarily checking
the time.

Required behavior:

deadline reached
    ↓
request cooperative termination
    ↓
short bounded grace period
    ↓
if still alive:
terminate execution isolation
    ↓
record truthful result
    ↓
release/retain resources according to effect certainty
    ↓
worker capacity becomes available again

Do not silently leave zombie processes.

---

# 10. CANCELLATION

Support:

## Cooperative cancellation

Handler receives cancellation signal and exits.

## Hard cancellation

If handler ignores the cancellation request beyond the allowed grace
period, execution isolation is terminated.

Cancellation must preserve:

- job history;
- attempt history;
- audit;
- resource accounting;
- effect uncertainty.

Do not rewrite history.

---

# 11. STALE RESULT PROTECTION

Even if a child process returns a valid result, the parent must not
commit it unless:

- job still belongs to this attempt;
- current fence matches;
- lease is current where required;
- cancellation has not invalidated execution;
- authority remains valid where execution requires authority;
- result matches expected input hash/version.

A child process is not authority.

The database/runtime decides whether the result may commit.

---

# 12. LEASE RENEWAL

Long execution must not block lease renewal.

Lease renewal should continue independently while the handler runs.

Test:

- handler runs longer than original 60-second lease;
- heartbeat/renewal continues;
- replacement worker cannot claim valid leased work.

Also test:

- lease renewal process dies;
- lease expires;
- another worker claims;
- original child later returns;
- old result is rejected through fence mismatch.

---

# 13. CHILD PROCESS CRASH

Simulate:

- clean non-zero exit;
- abrupt termination;
- malformed result;
- no result;
- corrupted result envelope.

Classify safely.

Do not retry malformed/permanent failures blindly.

Use existing Phase 4 retry classes.

---

# 14. PARENT PROCESS CRASH

Simulate parent death while child execution is active.

After restart:

- durable job remains authoritative;
- expired lease may be recovered;
- orphan execution cannot later commit through stale fence;
- orphan child is reaped/terminated where possible.

Document OS-specific behavior.

Do not claim stronger guarantees than tests establish.

---

# 15. PROCESS TREE TERMINATION

On Windows, terminating a parent does not always guarantee all
descendants disappear automatically.

Design/test bounded process-tree cleanup appropriate to the supported
local environment.

Do not add a giant process-supervisor platform.

But prove that the execution model does not knowingly leave runaway
synthetic child workloads.

---

# 16. SYNTHETIC NETWORK SERVICE

Create a local-only fake HTTP service or equivalent synthetic adapter
supporting scenarios such as:

- immediate success
- delayed success
- response slower than timeout
- connection accepted then no response
- connection drop
- malformed response
- remote acceptance followed by local timeout
- eventual reconciliation
- cancellation before remote acceptance
- cancellation after remote acceptance

No internet/provider needed.

---

# 17. NETWORK TIMEOUT LAYERS

Future real providers will require multiple timeout classes.

Design the boundary so later adapters can distinguish:

- connection timeout;
- read timeout;
- total task deadline.

Phase 6A may demonstrate them using the fake local service.

Do not configure real provider-specific values.

---

# 18. EXTERNAL SIDE-EFFECT RULE

If a future network task is purely read-only:

timeout may become retryable according to normal policy.

If it may have caused an external side effect:

timeout alone does NOT prove failure.

Use:

confirmed
rejected
uncertain

from the existing Phase 4 external-effect model.

Do not create another uncertainty mechanism.

---

# 19. BUDGET / AUTHORITY

Synthetic long tasks should demonstrate integration with existing
Phase 4/5 controls.

Before a chargeable/material task:

- budget reserved;
- authority current;
- effect intent persisted where consequential.

If task definitively never executed:

release safely.

If outcome uncertain:

retain reservation/use until reconciliation.

If authority expires during long read-only computation:

do not let that create new consequential authority.

---

# 20. WORKER CAPACITY

A stuck child must not permanently consume the complete worker.

Preserve the Phase 4 safety lane.

Test:

- all normal slots occupied by long tasks;
- one safety/reconciliation task still runs;
- timed-out workloads release their capacity.

Do not introduce unbounded process spawning.

---

# 21. CONCURRENCY LIMIT

Define a small bounded maximum number of long execution children.

Do not make it auto-scale.

Prefer explicit configurable caps.

The safety lane remains reserved.

---

# 22. SHUTDOWN

On graceful worker shutdown:

1. stop accepting new work;
2. signal active long tasks;
3. allow bounded grace;
4. terminate remaining child workloads;
5. avoid false success;
6. preserve durable state for later recovery.

Test this.

---

# 23. EXECUTION RESULT CONTRACT

Child result should be a closed schema.

Potential status:

- succeeded
- rejected
- transient_failure
- permanent_failure
- cancelled
- uncertain

Include:

- execution ID
- handler version
- output reference
- sanitized error code
- duration
- optional fake remote receipt reference

Never trust arbitrary pickled Python objects or executable payloads.

Use JSON/typed transport or another bounded safe representation.

---

# 24. IPC SECURITY

If IPC is required between parent and child:

- use bounded structured messages;
- enforce maximum size;
- validate schema;
- no arbitrary code loading;
- no pickle from untrusted child data;
- no secrets;
- handle truncated/malformed messages.

---

# 25. RETRY SEMANTICS

Retry remains controlled by Phase 4.

A hard timeout on a PURE internal/read-only job may be retryable.

A hard timeout after possible external effect must become uncertain.

Do not conflate:

process timeout

with:

definitive external failure.

---

# 26. HEALTH / INCIDENTS

System Health should surface:

- active long executions;
- oldest active execution;
- timed-out execution count;
- cancellation escalation count;
- orphan-cleanup failures;
- stale child completion attempts;
- execution pool capacity;
- long-task safety-lane health.

Avoid dashboard bloat.

Only add useful founder/operator visibility.

---

# 27. AUDIT

Trace:

job
→ attempt
→ long execution
→ child start
→ cancellation/timeout
→ termination
→ result
→ authority/effect state
→ reconciliation if required

Do not log raw sensitive inputs.

---

# 28. DATABASE SCOPE

Prefer reusing existing:

- jobs
- job_attempts
- external_effects
- incidents
- runtime heartbeats
- audit

Add a dedicated long-execution table only if necessary to represent
durable identity/state cleanly.

If required, create additive migrations beginning after current Phase 5
head.

Do NOT edit migrations 0001–0018.

---

# 29. MIGRATION DISCIPLINE

If Phase 6A needs migrations:

- Phase 5 head → Phase 6A head
- downgrade → Phase 5 head
- re-upgrade
- existing earlier round trips remain valid
- repeat upgrade

Do not create schema on startup.

If no database schema change is required, explicitly document why.

---

# 30. REQUIRED SYNTHETIC HANDLERS

Create bounded synthetic handlers for tests.

At minimum:

1. immediate_success
2. sleep_success
3. cooperative_cancel
4. ignore_cancel
5. infinite_cpu
6. child_crash
7. malformed_result
8. transient_read_timeout
9. fake_remote_success
10. fake_remote_accept_then_hang
11. fake_remote_reject
12. delayed_result_after_lease_loss

No real provider calls.

---

# 31. REQUIRED TESTS

## Hard Timeout

Run an uncooperative infinite handler.

Expected:

- timeout reached;
- child killed;
- worker remains alive;
- slot released;
- job reaches correct durable state;
- no zombie remains.

## Cooperative Cancel

Cancel long cooperative task.

Expected:

- child exits during grace;
- no hard kill required;
- job cancelled;
- history preserved.

## Uncooperative Cancel

Ignore cancellation.

Expected:

- bounded grace;
- forced termination;
- durable cancellation/failure;
- no stale success.

## Fence Test

Worker A runs long task.

Lease renewal stops.

Worker B claims with higher fence.

A later returns.

Expected:

A result cannot commit.

## Parent Crash

Parent process dies mid-task.

Restart runtime.

Expected:

durable recovery;
no uncontrolled final commit from old execution.

## External Uncertainty

Fake server accepts effect then hangs.

Expected:

uncertain;
no automatic resend;
reconciliation owns recovery.

## Shutdown

Worker shuts down with active long children.

Expected:

bounded cleanup;
no new work;
state recoverable.

## Capacity

Normal long-execution pool saturated.

Expected:

safety work still runs.

## Malformed IPC

Child sends invalid result.

Expected:

rejected/quarantined safely;
worker remains healthy.

---

# 32. WINDOWS-SPECIFIC TESTING

Because current development runs on Windows, explicitly test:

- child process spawn;
- cancellation;
- forced termination;
- process-tree cleanup;
- named pipe/IPC behavior if used;
- temporary directory cleanup;
- Ctrl/termination semantics where applicable.

Do not claim Linux behavior was proven unless separately tested.

The architecture should remain deployable to managed Linux later.

Avoid Windows-only domain abstractions where unnecessary.

---

# 33. PERFORMANCE

Measure:

- child startup overhead;
- cancellation latency;
- hard timeout cleanup latency;
- result IPC overhead;
- slot recovery time.

No production throughput claim.

---

# 34. SECURITY

No child receives:

- MIGRATION_DATABASE_URL
- DATABASE_URL
- service-role credentials
- founder session token
- provider API key
- unrestricted environment

Child execution should operate with the minimum bounded input required.

Add tests inspecting child environment.

---

# 35. PHASE BOUNDARY TESTS

CI should reject Phase 6A if implementation adds:

- openai package/import
- anthropic package/import
- real HTTP provider endpoints
- model names
- model routing
- prompt execution
- embeddings
- AI task tables
- external provider credentials
- real outbound

Local fake HTTP testing is allowed.

---

# 36. DO NOT IMPLEMENT AI GATEWAY YET

Do not create fake OpenAI/Anthropic classes merely to anticipate Phase 6B.

Phase 6A should build generic long-network-workload safety.

Phase 6B will later attach AI tasks to that proven boundary.

---

# 37. LOCAL DEMO

Provide a reproducible demo:

1. start Company OS
2. trigger long success
3. trigger hard timeout
4. trigger cooperative cancel
5. trigger uncooperative cancel
6. crash child
7. stop lease renewal and prove stale result rejected
8. trigger fake remote accept + timeout
9. inspect uncertain effect
10. reconcile
11. saturate normal execution pool
12. prove safety task still runs
13. shut down with active children
14. restart and inspect durable recovery
15. inspect System Health and audit trace

---

# 38. ACCEPTANCE CONDITIONS

Phase 6A passes only if:

- hard handler timeout is enforceable;
- uncooperative handler can be terminated;
- cooperative cancellation works;
- child crash cannot crash worker;
- parent crash cannot create stale authority;
- fencing rejects late results;
- lease renewal continues independently;
- shutdown cleans bounded child processes;
- long tasks cannot starve safety capacity;
- uncertain external effect remains safe;
- retries distinguish read-only from consequential ambiguity;
- authority/budget semantics remain correct;
- child environment contains no privileged secrets;
- IPC is bounded/validated;
- full Phase 2–5 regression suite passes;
- no OpenAI/Anthropic/AI gateway exists.

If any critical condition fails:

PHASE 6A NOT READY

Do not weaken the gate.

---

# 39. FULL REGRESSION

Run the complete canonical test gate:

npm.cmd run db:start
npm.cmd run check
npm.cmd run build

$env:PLAYWRIGHT_CHANNEL='chrome'
node scripts/ci-services.mjs e2e

npm.cmd audit --audit-level=moderate
.\.venv\Scripts\python.exe scripts/audit_python.py --online
git diff --check

Also run a dedicated Phase 6A fault suite exercising the synthetic
long-running handlers.

Use the elevated/non-sandboxed Windows environment as required.

No skipped safety tests.

---

# 40. DOCUMENTATION

Create:

docs/phases/phase-6a-brief.md

At completion:

docs/phases/phase-6a-handoff.md

Create an ADR if the execution-isolation architecture materially
extends ADR-021.

Update AGENTS.md with the Phase 6A stop gate.

Do not authorize Phase 6B in AGENTS.md.

---

# 41. MANIFEST

Create:

docs/phases/phase-6a-manifest.json

Include:

- accepted Phase 5 baseline SHA;
- branch;
- migration head;
- changed paths;
- requirement IDs;
- execution architecture;
- tests;
- migration hashes;
- source hashes;
- security assertions;
- phase boundary;
- review archive metadata.

---

# 42. REVIEW ARCHIVE

Create:

company-os-phase-6a-review.zip

Include complete repository source required for independent review and:

REPOSITORY_TREE.txt

Exclude:

- .git
- .env
- secrets
- node_modules
- .venv
- builds
- caches
- local DB
- screenshots/videos
- previous ZIPs
- temporary files

Report SHA-256.

---

# 43. DO NOT COMMIT OR PUSH

At completion:

STOP.

Do not:

- commit
- push
- create PR
- merge
- begin Phase 6B
- add OpenAI
- add Anthropic

Independent review comes first.

---

# 44. REQUIRED HANDOFF

Produce:

# PHASE 6A HANDOFF

## Gate Status

## Git

## Objective

## Execution Isolation Architecture

## Long Task Contract

## Process Lifecycle

## Hard Timeout

## Cooperative Cancellation

## Forced Termination

## Lease / Fence Integration

## Parent Crash Recovery

## Child Crash Recovery

## IPC

## Synthetic Network Boundary

## External Effect Uncertainty

## Authority / Budget Integration

## Worker Capacity / Safety Lane

## Shutdown

## System Health

## Security

## Tests

## Performance

## Migrations

## Changed Files

## Known Limitations

## Rollback

## Phase Boundary

## Phase 6B Readiness

End with exactly:

PHASE 6A IMPLEMENTATION COMPLETE — AWAITING INDEPENDENT REVIEW

or:

PHASE 6A NOT READY

Do not begin Phase 6B.