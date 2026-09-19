# ADR-023 — Bounded synthetic child execution

Status: implemented under explicit Phase 6A authority; independent review pending.
Extends ADR-021/022 without changing job, approval, budget or effect ownership.

Correction review: architecture accepted in principle (PASS WITH FIXES). The
bounded correction tolerates broken/already-closed pipe cleanup only after tree
termination and reaping; containment creation, attachment and termination errors
remain visible. Exit observation is followed by fresh monotonic deadline/control
checks before parsing and admitting a result. Stop-file observation sets the
shared stop event before lane scheduling and again inside the claim transaction;
active work retains the existing bounded cancellation path. No schema change.
Portable regressions run in the normal suite. Formal merge/closure still requires
the protected Ubuntu GitHub CI to pass after separately authorized publication;
local Windows evidence does not establish managed-Linux production readiness.

Use one fresh interpreter per long execution, a closed 8 KiB JSON envelope/result,
an allowlisted environment and a fixed executable entry point. No pickle, handler
module names, arbitrary URLs, input filesystem paths, DB credentials or provider
secrets cross the boundary. The child is a trusted synthetic program, **not an OS
sandbox for malicious code**. Unknown handlers/fields fail closed.

Two bounded dispatch lanes retain four normal slots (configurable 1–4) and one
reserved safety slot. Dispatch coordinators use threads instead of credentialed
process-pool children, so the main worker owns every kill-on-close handle. Actual
long workloads execute in independent processes. Existing shared commands,
scheduling, leases, retry delays and safety priority remain authoritative. There
is no broker, autoscaling or general supervisor service. The configured cap is
per worker instance, as with the previous pools; this is not a global quota.

The parent measures an elapsed monotonic deadline and requests cooperative
cancellation over stdin. A bounded grace is followed by process-tree termination
and reaping. A separate watcher reads cancellation/fence state; a database stall
cannot stall the process deadline loop. Lease renewal remains on its independent
15-second thread. Result admission rechecks DB fence/owner/lease, cancellation,
input/spec binding and consequential authority. A child result cannot settle an
effect without the separate fake receipt ledger. Failed/late results never gain
new authority. A read-only timeout uses Phase 4 bounded transient retry; ambiguous
effects retain existing budget/use reservations and enqueue existing reconciliation.

On Windows an unnamed non-inherited Job Object with KILL_ON_JOB_CLOSE contains
the execution and descendants. No envelope is written until job attachment passes;
before attachment, EOF from a dead parent exits without starting a workload.
Closing the parent's last job handle on abrupt death terminates members. Failure
to establish containment admits no workload. POSIX uses a new process group,
group termination and stdin-EOF watcher; it needs separate Linux evidence before
a deployment claim. No child is launched through a shell. The parent also kills
descendants after clean child exit. No named pipes or temporary execution files
are used. A blocked input-reader thread is bypassed only at interpreter shutdown
after output is flushed, using an explicit process exit.

The loopback fake HTTP server is per execution with a generated port and opaque
execution UUID path. Its bounded acceptance callback invokes the existing fake
receipt adapter in a separate short scoped transaction, including final Phase 5
authority checks. It can retain a receipt while withholding the HTTP response.
That ledger is synthetic remote evidence; response loss cannot authorize resend.
No real remote service, adapter credential, model or provider is configured.

Migration 0019 adds immutable `long_task_specs` and durable `long_executions`.
Specifications are bound before the first attempt; execution records bind the
existing immutable start attempt/fence and retain finish/abandon evidence. RLS,
actor checks, same-workspace FKs and append/terminal guards apply. API may insert
specs but cannot mutate execution records; worker can record execution but cannot
configure inputs. No new role, dependency or retention category is introduced.
Migration 0020 adds the pool heartbeat component and corrects pre-admission locking
to lock mutable jobs rather than immutable inputs. It is additive because 0019
had already run on disposable test databases; the applied revision was preserved.
Operational evidence follows existing R3 conventions. Downgrade refuses to discard
execution history; use a matched backup after draining/stopping the runtime.

References: [Windows job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information),
[job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[Python subprocess](https://docs.python.org/3.12/library/subprocess.html).
These contracts guide implementation; the handoff records what this workstation
actually proved. No production throughput, real-provider cancellation or Linux
process-lifecycle claim follows from synthetic Windows tests.
