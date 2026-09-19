# Phase 6A local synthetic demonstration

Use Windows PowerShell with the repository's locked Python/Node environment.
No provider keys or internet calls are needed for this demonstration.

```powershell
npm.cmd run db:start
npm.cmd run migrate
npm.cmd run build
npm.cmd run dev
```

The existing database must have the Phase 5 synthetic seeds. Never reset budgets,
approval history or scopes to make a demonstration pass. An exhausted fixture
should report its real denial. The fault runner below instead creates a disposable
synthetic database and removes only that database when finished.

Open the local console, sign in as Synthetic User A and select System Health.
The **Long execution safety demo** form queues local fixtures. Open **Jobs and dead
letters**, then the newest job. Refresh to inspect attempts, long execution ID,
fence, timing, forced termination, effect reservation and event trace.

1. Select `sleep_success`; observe success and no forced termination.
2. Select `infinite_cpu`; observe hard timeout, forced termination and bounded retry.
3. Select `cooperative_cancel`; open its running job and request cancellation.
4. Repeat with `ignore_cancel`; observe escalation after the grace period.
5. Select `child_crash`; observe permanent failure while the worker continues.
6. Run the fence fixture below: stop renewal, expire the synthetic lease, claim a
   higher fence and verify the earlier execution cannot finish the job.
7. Select `fake_remote_accept_then_hang`; after timeout inspect `uncertain` effect
   and retained reservation. No resend occurs.
8. Allow the fake receipt's 30-second visibility delay; existing safety-lane
   reconciliation confirms the receipt and settles the reservation exactly once.
9. The governed fixture runs the same protocol under a real exact synthetic grant,
   including authority expiry during the long response wait.
10. Saturate four normal slots using the capacity fixture; the safety task completes.
11. Inspect timeout and escalation counts plus active pool capacity in System Health.
12. Run the stop-file fixture; active children terminate, intake stops and the
    remaining queued job has no new attempt.
13. Run the parent-crash fixture; Windows closes job handles and children die.
14. Recover the expired durable lease; a higher fence owns recovery and the prior
    claim cannot commit. Abrupt death without a finish receipt stays visibly
    unconfirmed in health; durable recovery does not fabricate cleanup evidence.
15. Inspect execution/attempt IDs, `job.long_*` audit records and effect receipts.

Reproduce the complete fault demonstration (including the real 64-second workload):

```powershell
node scripts/phase6a-faults.mjs --tb=short
```

Focused demonstrations use the same real-role assertions, for example:

```powershell
node scripts/phase6a-faults.mjs -k fence_loss
node scripts/phase6a-faults.mjs -k governed_long_effect
node scripts/phase6a-faults.mjs -k safety_capacity
node scripts/phase6a-faults.mjs -k worker_stop_file
node scripts/phase6a-faults.mjs -k parent_crash
```

The test owner's lease-clock adjustments apply only to the disposable database,
simulating lease loss without modifying production or persistent demo records.
The renewal test and fake receipt visibility delay use actual elapsed time. The source includes no named pipe, temporary child directory, provider
endpoint or live effect. Ctrl+C requests graceful worker shutdown; the local
launcher also supports `npm.cmd run stop`. Linux behavior is not certified here.

Stop at independent review. No Phase 6B or provider capability is authorized.
