# Phase 4 — Events, durable jobs and system health

Authority: Nouman's explicit Phase 4 implementation request, 17 September 2026.
Phase 3 is closed at `e8c896a8fd7669472d9488b83840526ce847ce20`.
Branch: `phase-4-events-jobs-health`. No commit, push, PR, merge, production
deployment, real provider, AI, outbound or Phase 5 work is authorized.
Numbered specifications and accepted ADRs remain the design authority.

## Schema map (before migrations)

| Canonical object | Implement now? | Table(s) | Deferred dependency | Reason |
|---|---|---|---|---|
| DATA-050 events/outbox/receipts | Yes | events, outbox, consumer_receipts | Future business consumers | Immutable envelopes; atomic consumption; effect-disabled replay |
| DATA-050 inbox | Yes | webhook_inbox | Provider authentication | Fake authenticated durable callbacks only |
| DATA-051 workflows/jobs/attempts/dependencies/schedules | Yes | workflow_runs, jobs, job_attempts, job_dependencies, schedules, schedule_slots | Human approval resolution | Durable generic waits; no approval engine |
| DATA-052 effects | Yes | external_effects | Provider connections, policy versions, approval uses | Fake-only registry and fixed runtime contract; ADR-021 |
| DATA-053 accounting | Yes | budgets, budget_reservations, usage_entries, quota_buckets | Live funded budgets, AI pricing | Fixed-precision synthetic accounting |
| DATA-057 health/incidents/attention | Phase 4 subset | runtime_heartbeats, incidents, incident_evidence, runtime_attention | Full founder prioritization, external alerts | Technical visibility and bounded snooze only |
| DATA-057 audit | Extend existing | audit_entries | Approval/model references, off-system export | Runtime causation and typed trace references |
| DATA-048 provider connections | No | fake_endpoints (local substitute) | Preflight, credentials, live activation | No real provider connection is represented |
| DATA-049 mapping/cursors | Fake subset | fake_observations | Real provider sync | Synthetic ordering and reconciliation only |
| Fake remote ledger | Test adapter only | fake_receipts | Real remote provider | Independent commit simulates remote acceptance/lost response |
| Runtime input | Yes | runtime_inputs | Business payloads | Closed, immutable, bounded synthetic inputs |
| DATA-045–049 authority | No | None | Phase 5 | No general policy, approval manifests or authority accounting |
| DATA-054 AI | No | None | Phase 6 | No models, context packs or AI budget logic |

## Implementation and review gate

Implement SYS-001/002/007/014/019/022/024; DATA-050–053 and runtime DATA-057;
EVT-001/002/027/029/030/035/038/039; OPS-001–004/006/008/012–019;
API-051–053/059–063; UI-015 and SEC-001/003/008/009 subsets.
Keep Phase 2/3 security and business behavior. New tenant tables require FORCE
RLS and composite tenant foreign keys. API and worker share application commands.
Use PostgreSQL, 60-second leases, 15-second heartbeats and scheduler ticks,
one reserved safety process and four ordinary processes. No sleeping lease waits.
Run migration round trips, all regressions, fault/concurrency/security/runtime
tests, contracts, build, browser tests and dependency/secret checks. Record exact
results and any gaps in the handoff. A missing critical gate means NOT READY.
Stop for independent review; no Phase 5 authorization follows from completion.

Additional physical support: `company_runtime_caps` is restricted global synthetic
configuration; `reservation_budget_caps` is the tenant-scoped reservation/cap join;
`runtime_completions` is the tenant-scoped append-only fake completion receipt.
These belong to DATA-053 and API-063's Phase 4 subsets, per ADR-021.
