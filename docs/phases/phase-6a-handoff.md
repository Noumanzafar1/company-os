# PHASE 6A CORRECTION HANDOFF

## Correction Gate

Independent review: PASS WITH FIXES; execution-isolation architecture accepted in
principle. All bounded corrections and required final local gates passed.
Independent correction review and protected Ubuntu GitHub CI are still required.
Phase 6A is not formally merged or closed. No publication authority is inferred.

## Fix 1 — IPC Cleanup Robustness

After process-tree termination and root reaping, closing stdin/stdout tolerates
OSError (including BrokenPipeError) and ValueError for already-closed streams.
Reader joins remain bounded. No raw exception or pipe data is logged. Containment
creation, attachment and termination failures are outside this suppression.
A regression injects close-time lifecycle errors around real exited children;
success, no-result and malformed-result classifications remain unchanged. Twenty
successive fresh children complete without escaping cleanup. Existing timeout,
cancellation, root/descendant cleanup tests remain; attachment failure still
propagates and never releases a handler envelope outside containment.

## Fix 2 — Final Deadline Admission

Fresh control and monotonic-deadline checks follow observed child exit, precede
result parsing and follow validation before returning an accepted result.
Invalidation discards the result. Existing grace-period discard and consequential
uncertainty rules are unchanged. Eight deterministic tests hold the real child
exit/reap observation boundary, then make HARD_TIMEOUT, CANCELLED, SHUTDOWN or
LEASE_LOST effective before admission. No approximate timeout sleep drives these
races. Existing timely success and late-result database fencing tests remain.

## Fix 3 — Shutdown Intake Gate

Stop-file observation sets the shared stop event. The main loop rechecks before
each lane submission. Slots recheck the file, and the claim transaction checks
again after connection/context acquisition, immediately before the claim command.
Both lanes use the same intake predicate. Already-running children retain bounded
shutdown cancellation. Existing startup removal of a prior run's stop marker is
unchanged; the new checks govern intake during the current run.

The original capacity-one shutdown test is retained. New tests cover both lanes
with a file already present, file arrival during claim-connection acquisition,
arrival during maintenance before scheduling, and a real worker with three normal
slots, one active long child and queued normal/safety work. A test admission barrier
holds spare slots so the stop race is deterministic. Both queued jobs keep zero
attempts; the active child is reaped, its pure job is retryable, and the worker exits.

## Fix 4 — Publishing Hygiene

`apps/console/next-env.d.ts` is restored byte-for-byte from accepted Phase 5 after
build verification. It is excluded from overall implementation changed_paths,
but included in this delta because the previous review archive contained the
generated production references. `scripts/build_phase6a_review.py` is removed from
the implementation set and retained only under ignored `.local/`. Apply that
removal when reviewing the delta against the original archive. Reproducible
Phase 6A test runners remain. No new full repository ZIP is created.
The new Phase 6A `CORRECTION_FILE_LIST.txt` is archive-only; do not apply that
inventory over the repository's unchanged historical Phase 4 inventory of the
same name. `REPOSITORY_TREE.txt` remains only in the original full review archive.

## Windows Lifecycle

Real Windows child spawn, repeated short executions, expected pipe cleanup,
cooperative/hard cancellation, root/descendant termination, parent death and
shutdown tests are required in the final result below. No test substitutes a mock
process for the actual execution. Narrow test seams force otherwise rare races.

## Linux Portability Status

Tests use portable subprocess/stream wrappers and are collected by the unchanged
normal `pytest` suite. Existing `foundation-required` on `ubuntu-latest` invokes
`npm run check`, including these tests, after publication is separately authorized.
Local Linux lifecycle was not run. Static typing is not a lifecycle guarantee.
No Docker, WSL or cloud infrastructure was added. Protected Ubuntu GitHub CI MUST
pass before Phase 6A is formally merged/closed; no managed-Linux production
readiness is claimed.

## Tests

- Database start and migrate: PASS; head unchanged at `0020_long_spec_lock`.
- `npm.cmd run check`: 335 Python tests passed in 493.30 s,
  zero skips, two upstream warnings; both console tests and contracts/lint/types/
  boundary checks passed.
- `npm.cmd run build`: PASS, 19 generated pages.
- Chrome `node scripts/phase6a-e2e.mjs`: 7 passed in 53.2 s,
  zero retries/skips, running real local API/worker/console services.
- `node scripts/phase6a-faults.mjs`: 68 passed in 206.29 s,
  zero skips, two upstream warnings.
- Focused correction/shutdown selection: 26 passed, 42 deselected, 56.45 s.
- npm audit: zero vulnerabilities. Online Python audit: 49 packages,
  zero findings, checked 2026-09-18T17:42:58.314459+00:00.
- Linux-platform mypy: PASS, 53 source files; static evidence only.
- `git diff --check`: PASS; baseline generated file restored after build.

Focused selection is additional diagnostic evidence; no safety test is skipped,
deleted or weakened in the full/fault gates. The initial focused run passed; its
subsequent typing check found an IO[bytes]/BinaryIO annotation mismatch, corrected
before stable-source gates. The first full run had 334 passes and one failure
in `test_effect_intent_and_uncertainty[effect_lost-uncertain]`:
an older eligible safety job ran before the uncertainty fixture's own
reconciliation. The test now drains the real ordered safety lane with a fixed
20-claim bound until its own effect settles, retaining every original receipt,
job, workflow and settlement assertion. No runtime policy was changed. Final
full and fault results above supersede that failed run. Two upstream test-client
deprecations remain.

## Performance

Final full-gate single samples (milliseconds):

| Handler | Spawn/envelope | Total slot time | Grace/cleanup | Forced |
| --- | ---: | ---: | ---: | --- |
| immediate_success | 0.0 | 281.0 | 0.0 | False |
| sleep_success | 16.0 | 516.0 | 0.0 | False |
| infinite_cpu | 16.0 | 1828.0 | 312.0 | True |
| cooperative_cancel | 0.0 | 813.0 | 0.0 | False |
| ignore_cancel | 15.0 | 1140.0 | 312.0 | True |

Spawn-to-envelope release excludes interpreter readiness. Immediate-success total
includes initialization, IPC and cleanup. Cancellation samples request stop at
800 ms; total minus 800 ms estimates request-to-slot-return latency. Infinite CPU
has a 1,500 ms hard deadline. Sub-tick operations may measure zero on Windows.
Single samples are not throughput/SLA claims; no tuning scope was added.

## Changed Files

Correction-cycle changed files (delta contents):

- `apps/console/next-env.d.ts`
- `apps/worker/main.py`
- `docs/adr/023-long-execution-isolation.md`
- `docs/phases/phase-6a-handoff.md`
- `docs/phases/phase-6a-manifest.json`
- `packages/company_os/workflow/isolation.py`
- `packages/company_os/workflow/runtime.py`
- `tests/integration/test_long_runtime.py`
- `tests/integration/test_runtime.py`
- `tests/unit/test_long_isolation.py`

Removed from implementation/review source: `scripts/build_phase6a_review.py`;
retained only as ignored local tooling. Overall implementation changed_paths
exclude that helper and the restored `next-env.d.ts`.

## Migration Status

No schema change. Head remains `0020_long_spec_lock`. Migrations 0001–0020 and the
migration manifest match the start-of-correction SHA-256 snapshot. Existing
migration round trips and repeat upgrade remain in the full gate. Rollback and
history preservation limits from the original handoff remain unchanged.

## Security

Windows Job Object containment, bounded JSON, child environment allowlist,
transaction-local workspace context, RLS, runtime roles, authority, budgets,
effect uncertainty/reconciliation and safety capacity are preserved. Only expected
post-reap stream cleanup is suppressed. Containment failures remain fail-closed.
No new dependency, privileged child input or provider credential.

## Git

Branch remains `phase-6a-network-runtime-safety`. HEAD, protected main and
origin/main remain `9d9010f62e890275760eaa7a312ed119f7c28ec0`.
No commit, push, PR, merge or deployment; index remains empty. All 11 previous
review ZIPs are unchanged, including original Phase 6A review SHA-256
`30ae727f91474346908050a8c4418d4369b912a4ce60df47fd18e6c0f4fc797b`.

## Phase Boundary

No OpenAI, Anthropic, LLM API, AI Gateway, prompts, model routing, embeddings,
real provider, provider credentials, real outbound or production deployment.
Phase 6B has NOT begun. Only these review corrections were implemented.

## Known Remaining Debt

Per-worker rather than cluster-wide capacity, trusted-code rather than hostile-code
sandboxing, external provider guarantees, 200-target authority tuning, production
SLA/alerting and conservative historical health semantics remain unchanged.

## Phase 6B Readiness

Not authorized. Independent correction review, separately authorized publication
and passing protected Ubuntu CI precede formal Phase 6A closure. None authorizes
Phase 6B without an explicit founder decision.

---

The following original implementation handoff is retained unchanged as historical
review evidence. Its test counts and changed paths describe the original cycle;
the correction sections above and corrected manifest govern the current source.

# PHASE 6A HANDOFF

## Gate Status

All required local gates passed. Independent review remains mandatory. Nouman is
the repository owner and acceptance reviewer. No commit or publication authority
is inferred from implementation or test results.

## Git

Accepted Phase 5 baseline: `9d9010f62e890275760eaa7a312ed119f7c28ec0`.
Fresh `git fetch origin` verified local main equals origin/main and contains
reviewed feature `51afcf30dddf79bdc1d775280f9deb151f937964`.
Branch: `phase-6a-network-runtime-safety`, created from that origin/main.
HEAD remains the accepted baseline. Protected main is unchanged. No commit,
push, PR, merge or deployment. Previous review ZIPs remain untracked and preserved;
their hashes are recorded in the new manifest.

## Objective

Extend the existing runtime with an enforceable boundary for synthetic long work.
The parent retains lease, fence, deadline, cancellation, lifecycle and admission
control. A child cannot write business state or confer authority. Phase 4 durable
jobs/effects and Phase 5 exact authority remain the system of record.

Requirement slices: SYS-001/002/006/007/014/018/019/022/024; OPS-013–019;
SEC-003/006/008/009; TEST-001/004/005/007/009/010/012/027/029/031.
These are synthetic runtime slices, not completion of future provider requirements.

## Execution Isolation Architecture

ADR-023 extends ADR-021/022. Four normal dispatch coordinators (configurable 1–4)
and one safety coordinator retain the existing scheduling lanes. Coordinators
are threads; each long workload gets a fresh interpreter contained by its parent.
This replaces the credentialed process-pool coordination layer so the main worker
owns Windows kill-on-close handles. It preserves shared application commands,
DB scheduling, leases, retries, waits, effects and the reserved safety lane.
No broker, autoscaling, dependency or general process-supervisor platform was added.

## Long Task Contract

`LongSpec`, `ExecutionEnvelope` and `ExecutionResult` are closed Pydantic contracts.
The envelope binds execution/workspace/job/start-attempt/fence, input reference and
combined immutable input/spec hash, handler/version, timeout/grace/connect/read
limits, correlation/trace, optional manifest/reservation and a parent-bound local
port. The child never receives an arbitrary hostname, URL, code/module name,
filesystem input path, credential or ambient environment. Defaults normalize
before hashing. Job timeout metadata is synchronized with the immutable spec;
the execution boundary rejects a spec exceeding its job's timeout.

## Process Lifecycle

Persist execution identity before launch. Spawn the fixed interpreter with `-I`,
attach OS containment before releasing the envelope, record the child PID in
scoped audit, supervise and reap. Terminal evidence retains sanitized lifecycle
events, timings, outcome and forced-termination flag. Job start/finish records
remain append-only. Recovery marks unfinished executions abandoned without
inventing a result or rewriting their attempts.

## Hard Timeout

The parent enforces the elapsed deadline independently of handler behavior and
database polling. Deadline invalidation wins over a result already in the pipe.
It signals cancellation, grants 0.05–2 seconds, then terminates the execution tree
and waits for the child. CPU loops, ignored cancellation and blocked local HTTP
cannot keep their execution slot forever. Pure timeouts use the existing bounded
transient retry scheduler, releasing the lease between attempts.

## Cooperative Cancellation

The parent observes durable cancellation through a separate scoped watcher.
An input control message wakes cooperative handlers. The immutable attempt history
and cancellation audit remain. The cooperative fixture exits during grace without
forced termination. Cancellation before claim creates no execution or reservation.

## Forced Termination

Windows uses an unnamed Job Object with KILL_ON_JOB_CLOSE and no inherited job
handle. The hard-stop path terminates the job tree and reaps its root. Parent death
closes the last handle. Before containment attachment, a child has no envelope and
exits on stdin EOF. Tests exercise an actual descendant and verify both root and
descendant disappear. Containment setup failure admits no handler.

## Lease / Fence Integration

Existing lease renewal runs every 15 seconds in separate short transactions.
A real 64-second workload crosses the original 60-second lease while remaining
leased. Loss of renewal is simulated independently of workload execution; expired
leases are recovered and claimed with a higher fence. The original completion is
rejected. A second fixture holds an actual valid child result at the admission
boundary, replaces the worker, then delivers the old result and proves rejection.
No mocked success substitutes for the child transport in that test.

## Parent Crash Recovery

Tests forcibly terminate the supervising process during work, observe Windows
child cleanup, recover the durable expired lease and reject the original claim.
The execution remains traceable even without a finish receipt. Maintenance records
abandonment; System Health reports cleanup confirmation unavailable. It does not
declare an orphan physically reaped merely because the lease was recovered.

## Child Crash Recovery

Non-zero exit, abrupt exit, no result, malformed JSON, oversized output and corrupt
result identity are isolated from the worker. Malformed/permanent failures enter
the existing dead-letter path, preserving attempts and incidents. They do not
receive blind retries. Another child can execute after a hard timeout.

## IPC

Anonymous stdin/stdout pipes carry at most 8 KiB per envelope/result. No pickle or
arbitrary executable serialization is used. Output is read with a hard memory
bound and schema/binding validation; raw output and stderr are not logged. A
successful result received during timeout grace is discarded. Child final exit
occurs after output flush, avoiding interpreter shutdown waiting on a blocked
control-reader lock. No named pipes or temporary child directories are created.

## Synthetic Network Boundary

A per-execution server binds only 127.0.0.1 on an OS-assigned port. Fixed fixtures
cover success, delay, accept-and-hang, no response, connection drop, malformed
response and rejection. Connect, read and total limits are distinct. The local
server's acceptance callback uses the existing fake receipt adapter in its own
short transaction, then releases that transaction before withholding a response.
No real HTTP provider endpoint or provider-specific timeout value is present.

## External Effect Uncertainty

The existing prepare → dispatch → confirmed/rejected/uncertain protocol is reused.
Timeout, cancellation or unusable output after possible acceptance keeps the
effect uncertain. There is no reset to prepared and no automatic resend. The
existing safety reconciliation reads the fake receipt ledger and settles once.
The acceptance fixture waits for the real 30-second fake visibility delay; it
does not edit immutable receipt history to pass.

## Authority / Budget Integration

Effect preparation reserves the existing budget/quota and exact manifest use.
The synthetic acceptance callback rechecks fence, cancellation, deadline, enabled
endpoint, current authority, budget and final temporal authority immediately
before receipt insertion. Child output alone cannot confirm a charge or effect.
Admission checks current authority again. Expiry during the response wait cannot
renew authority; accepted-but-uncertain work retains reservations until the
existing reconciliation path resolves it. Proven prepared non-use retains the
existing cancellation/release behavior. Historical uses and spend are not reset.

## Worker Capacity / Safety Lane

`LONG_EXECUTION_CAPACITY` defaults to 4 and accepts only 1–4. It limits normal
execution per worker instance; there is one independent safety coordinator.
Four real long children are saturated while safety work completes. This is a
bounded local test, not a global multi-instance quota or production throughput
claim. Pool capacity is advertised through scoped runtime heartbeats.

## Shutdown

Stop file and signal handlers stop intake, set the shared cancellation event and
drain bounded children. Executor cleanup also signals stop on exceptional exit.
The real worker stop-file test proves its active child disappears, the interrupted
pure job becomes retryable and a queued job receives no attempt. Windows abrupt
termination is separately tested. Interactive Ctrl+C delivery was not separately
automated; no stronger console-control guarantee is claimed.

## System Health

The existing System Health view adds active/oldest execution, timeout and escalation
counts, stale completion count, unconfirmed orphan cleanup, live normal capacity
and reserved safety slots. Missing capacity heartbeat is UNKNOWN. Job detail shows
execution ID/fence, state/outcome, elapsed time and forced termination. The
stale-completion counter uses immutable audit evidence, so rejection remains
visible even if recovery already finalized the execution as abandoned. The local
synthetic demo form uses the same authenticated, scoped, CSRF-protected command
path. No dashboard subsystem or new business authority was added.

## Security

Child environment is an allowlist containing only Windows runtime root variables
where required. Tests plant synthetic canaries under DB, migration, worker,
session, provider-key and arbitrary variable names and verify none are inherited.
The child gets no database connection or direct mutation port. RLS, actor guards,
same-workspace foreign keys, exact manifests and non-owner/NOSUPERUSER/NOBYPASSRLS
roles remain. API cannot mutate execution records; workers cannot configure specs.
The populated-tenant regression now creates both new tables' rows and checks their
actual wrong-workspace behavior, including the API's stronger UPDATE denial.
Source guards continue to reject provider imports/dependencies and now reject
provider endpoints, model execution markers and later-phase schema additions.

## Tests

- `npm.cmd run db:start` and `npm.cmd run migrate`: PASS; head `0020_long_spec_lock`.
- `npm.cmd run check`: PASS; 310 Python tests, 2 upstream warnings,
  450.42 seconds, zero skips. Contracts, Ruff, mypy (53 source files),
  phase boundaries, ESLint, TypeScript and console Vitest all passed.
- `npm.cmd run build`: PASS; 19 generated pages.
- Chrome `node scripts/phase6a-e2e.mjs` invoking canonical
  `node scripts/ci-services.mjs e2e`: 7 passed in 49.9 seconds, no retries or skips.
- `node scripts/phase6a-faults.mjs`: 43 passed in 180.90 seconds,
  two upstream warnings, zero skips.
- `npm.cmd audit --audit-level=moderate`: zero vulnerabilities.
- `.venv/Scripts/python.exe scripts/audit_python.py --online`: 49 packages,
  zero findings, checked 2026-09-18T13:19:25.916022+00:00.
- `mypy --platform linux packages/company_os apps/api apps/worker`: PASS,
  53 files. Static portability evidence only.
- `git diff --check`: PASS; only line-ending normalization advisories.

Browser execution uses `scripts/phase6a-e2e.mjs`, which creates a fresh synthetic
database and invokes the canonical runner against running API/worker/built console.
It drops only its generated database. The persistent demo's budgets/history are
not reset. Phase 6A faults likewise use a separate seeded database so new charges
cannot consume the older regression fixtures' deliberately small caps. No security
assertion is skipped or weakened. Two upstream test-client deprecations remain.

Development failures exposed and corrected: blocked child-reader shutdown;
immutable-input row-lock privilege mismatch; default-number hash normalization;
JSON evidence adaptation; retry fixture interference; browser navigation race;
test-budget interference and missing populated rows for the new tenant tables.
An intermediate full run also overlapped source changes, so newly spawned
processes saw a different timeout contract; only the final stable-source run is
acceptance evidence. Earlier failures are not represented as passes. A subsequent 83-minute run
correctly rejected an expired one-hour authority grant and exposed queue
interference in the populated-tenant fixture. The fixture now prioritizes its
long job; the authority expiry rule is unchanged. The final complete rerun passed.

## Performance

Real fresh-child samples from the final full gate (milliseconds; single samples,
not a statistical benchmark):

| Handler | Spawn/envelope release | Total slot occupancy | Grace/cleanup | Forced |
| --- | ---: | ---: | ---: | --- |
| immediate_success | 0.0 | 234.0 | 0.0 | False |
| sleep_success | 0.0 | 422.0 | 0.0 | False |
| infinite_cpu | 16.0 | 1813.0 | 313.0 | True |
| cooperative_cancel | 0.0 | 812.0 | 0.0 | False |
| ignore_cancel | 0.0 | 1125.0 | 312.0 | True |

The immediate-success total includes interpreter initialization, bounded IPC and
cleanup; spawn/envelope release alone excludes child readiness. Cancellation is
requested at 800 ms, so its observed latency is total occupancy minus 800 ms.
The infinite-CPU deadline is 1,500 ms. IPC byte-arrival spans were below the
Windows timer resolution in these samples (reported 0 ms), not literally free.
The manifest retains all raw timing samples. No production throughput or
remote-provider latency guarantee follows.

## Migrations

Head: `0020_long_spec_lock`, following immutable Phase 5 head 0018.
0019 adds immutable specs and durable execution identity/evidence with FORCE RLS,
actor guards and composite references. 0020 corrects configuration locking by
locking mutable job rows, preserving immutable input privileges, and permits the
pool heartbeat component. The correction is additive because 0019 had already
been exercised. Migrations 0001–0018 remain unchanged; normalized migration hashes
are in the manifest. Startup never creates schema. No new dependency or role.

The canonical fixture validates 0018 → head → 0018 → head, all existing earlier
round trips and repeat head upgrade. The local synthetic database is upgraded;
its existing budgets, approvals and history are preserved. Tests run as real API
and worker roles; only fixture provisioning/controlled lease faults use the owner.

## Changed Files

Exact source paths changed relative to the accepted Phase 5 baseline (also
hashed in the manifest):

- `AGENTS.md`
- `apps/api/runtime.py`
- `apps/console/app/system/command/route.ts`
- `apps/console/components/runtime.tsx`
- `apps/console/components/shell.tsx`
- `apps/console/next-env.d.ts`
- `apps/worker/main.py`
- `database/migrations/manifest.json`
- `database/migrations/versions/0019_long_execution.py`
- `database/migrations/versions/0020_long_spec_lock.py`
- `docs/adr/023-long-execution-isolation.md`
- `docs/phases/phase-6a-brief.md`
- `docs/phases/phase-6a-demo.md`
- `docs/phases/phase-6a-handoff.md`
- `docs/phases/phase-6a-manifest.json`
- `packages/company_os/application/long_tasks.py`
- `packages/company_os/application/runtime.py`
- `packages/company_os/long_contracts.py`
- `packages/company_os/persistence/database.py`
- `packages/company_os/persistence/runtime.py`
- `packages/company_os/reporting/runtime.py`
- `packages/company_os/runtime_contracts.py`
- `packages/company_os/workflow/fake_network.py`
- `packages/company_os/workflow/isolation.py`
- `packages/company_os/workflow/long_child.py`
- `packages/company_os/workflow/long_runtime.py`
- `packages/company_os/workflow/process_tree.py`
- `packages/company_os/workflow/runtime.py`
- `packages/contracts/api.d.ts`
- `packages/contracts/openapi.json`
- `scripts/boundaries.py`
- `scripts/build_phase6a_review.py`
- `scripts/phase6a-e2e.mjs`
- `scripts/phase6a-faults.mjs`
- `scripts/phase6a_e2e_database.py`
- `tests/conftest.py`
- `tests/contract/test_contracts.py`
- `tests/e2e/long-runtime.spec.ts`
- `tests/integration/test_long_runtime.py`
- `tests/integration/test_runtime.py`
- `tests/unit/test_core_boundaries.py`
- `tests/unit/test_long_isolation.py`

## Known Limitations

- Windows 11 build 26200, Python 3.12.14 and Node 24.16.0 are the measured local
  environment. Linux process lifecycle was not executed here; separate Linux
  faults are required before deployment. Static portability checks are not that proof.
- This isolates trusted registered synthetic code; it is not a sandbox against
  arbitrary malicious code running under the same OS user.
- Per-worker caps do not constitute cluster-wide admission control. No autoscaling.
- Kernel kill-on-close does not produce a database cleanup receipt after abrupt
  parent death. Unconfirmed cleanup remains visible rather than silently green.
- Loopback receipts do not prove real-provider cancellation, billing, idempotency,
  response timing, rights, retention or native outbound guarantees.
- Existing 200-target authority validation tuning debt and upstream test-client
  deprecations remain. No external alert route, live budget or production SLA exists.

## Rollback

Stop API/worker/console; preserve review source and any wanted synthetic state.
Empty/pre-execution migration round trips are tested. Once execution history or
pool heartbeat history exists, downgrade is deliberately fail-closed through
history guards; do not disable guards or delete evidence to force rollback.
Restore a matching Phase 5 database backup with its matching baseline checkout.
Do not run Phase 5 code against the Phase 6A head, or Phase 6A code against 0018.
Forward correction is preferred when retaining new history. No rollback, commit
or destructive persistent-database reset was performed.

## Phase Boundary

Synthetic Phase 6A only. No OpenAI, Anthropic, LLM/provider API, AI gateway, model
routing, prompts, embeddings, vector DB, Apollo, Smartlead, ZeroBounce, Pipedrive,
Google APIs, n8n Cloud, real outbound, campaigns, real client data, credentials,
paid calls or deployment. Original Phase 1 design status is preserved.
The source-only review ZIP excludes secrets, environments, dependencies, builds,
caches, DB data, media, temporary files, Git metadata and earlier review ZIPs.
It includes its repository tree. Its SHA-256 is reported separately to avoid
self-referential manifest/archive hashing.

## Phase 6B Readiness

Not authorized. Independent architectural review and explicit founder decisions
remain prerequisites. This work does not admit a real model/provider handler.
Reproducible local steps are in `phase-6a-demo.md`.

PHASE 6A IMPLEMENTATION COMPLETE — AWAITING INDEPENDENT REVIEW
