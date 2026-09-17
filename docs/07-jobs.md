# Part 12 — Job Runtime

**OPS-013 Job schema.** In addition to DATA-001: `job_type str`, `job_version int`, `workflow_run_id uuid?`, `subject_id uuid`, `input_ref uuid`, `input_hash char(64)`, `state JobState`, `priority enum(safety,interactive,normal,bulk)`, `available_at ts`, `deadline_at ts`, `idempotency_key str`, `attempt_count int`, `max_attempts int`, `timeout_seconds int`, `lease_owner str?`, `lease_expires_at ts?`, `heartbeat_at ts?`, `fence bigint`, `cancel_requested_at ts?`, `last_error_code str?`, `budget_reservation_id uuid?`, `origin_event_id uuid?`, `correlation_id uuid`, `waiting_on_resource_id uuid?`. Unique workspace/job_type/idempotency_key. `job_attempts` is append-only with job_id, attempt_no, worker_id, fence, start/end, outcome, sanitized error, provider request refs and cost refs; unique job/attempt_no.

Worker claims ready rows with a short transaction using `FOR UPDATE SKIP LOCKED`, orders safety first then age, sets a 60-second lease and increments fence. Heartbeat every 15 seconds. Each completion mutation includes the current fence and owner. Long model calls use bounded timeouts and heartbeats without holding a DB transaction. Lease loss means the old worker cannot commit state; it also cannot be trusted to “undo” an already initiated remote call, so the effect dispatcher owns separate effect state.

Use two process pools within the worker service: a reserved safety lane of one slot and a normal lane initially of four I/O tasks, further constrained by per-provider limits and workspace fairness. If the runtime cannot keep safety latency while busy, stop discretionary intake. Retries must not occupy a sleeping worker; set available_at and release the lease. Waits for humans are state records, never leased jobs.

**OPS-014 Retry classes.** Normal transient read/network/rate errors: maximum three attempts including initial, full-jitter delay 5–30 s then 30–120 s, honour longer Retry-After within job deadline; deadline expiration becomes dead_letter or review. Never retry malformed requests, 401/403, source-right denial or unsupported model capabilities unchanged. Safety stop calls use a separate bounded sequence up to ten attempts over 15 minutes while escalating after 60 seconds and declaring red by five minutes; repeated stop is allowed only when adapter contract verifies idempotent/monotonic stopping. After exhaustion, keep incident open and retry only through a reviewed recovery task. Already running provider sequences must not be called locally stopped.

| Job type | Handler and inputs | Timeout/deadline | Cost/resume/retry rule |
|---|---|---|---|
| research_account | intelligence; account, source and ICP refs | 180 s / 24 h | Data and AI caps separately reserved; checkpoints per fetch |
| verify_contact | prospecting; contact/source refs | 45 s / 4 h | One verification charge per logical request unless definitively failed |
| recalculate_score | deterministic score handler | 10 s / 1 h | No AI; same input hash idempotent |
| prepare_campaign_messages | communications; frozen target batch ≤25 | 300 s / 24 h | One bounded AI task per draft; complete batch manifest only after all pass |
| deploy_campaign / enroll_contact | sequencer effect handler | 30 s / approved window | No retry on ambiguous side effect; reconcile |
| stop_enrollment / pause_campaign | safety dispatcher | 10 s per call / 15 min retry window | Reserved safety lane; no discretionary budget dependency |
| ingest_reply / propagate_suppression | safety handler then classification | 10 s local / immediate | Persist hold first; provider action independently tracked |
| classify_reply | communications; restricted thread | 60 s / 1 h | Failure leaves hold and human task |
| sync_provider / reconcile_effect | adapter-specific | 60 s page / 30 min run | Page cursor checkpoints; no effect creation by reconciliation |
| prepare_meeting_brief | sales; meeting version and context | 180 s / 2 h before meeting target | Meeting changes supersede job; late bookings run immediately |
| generate_daily_brief | reporting then optional AI | 120 s / 08:05 local | One schedule slot; deterministic snapshot if model fails |
| knowledge_refresh / retention_sweep | catalogue/privacy | 120 s page / 24 h | Recheck ACL per document; erase chunks/caches with receipts |
| health_scan / budget_reconcile | platform | 30 s / 2 min | No AI, priority above bulk |

**OPS-015 Scheduling.** Worker scheduler reads durable schedules each 15 seconds; advisory lock elects an emitter, uniqueness prevents duplicate jobs if two instances overlap. Use local calendar slot plus IANA zone as idempotency key. At 08:00 Asia/Karachi (03:00 UTC at the current zone offset), emit the brief once per local day. Calculate offsets from zone data rather than hard-code UTC conversion. After downtime, one overdue brief is generated and marked late; do not email a backlog of missed briefs. Other schedules explicitly choose skip, one-catchup or bounded-catchup. SaaS owns sequence touch timing; Company OS owns release, expiry and pause supervision.

n8n MAY deliver an internal notification or call an approved connector read task; it passes a Company OS job ID and scoped service token. n8n execution ID is telemetry, not job identity. Completion callbacks submit a typed result validated by the application. n8n workflow exports belong in Git. Workflow restart cannot lose canonical progress. Native sequencer state is reconciled, never reconstructed by replaying enrolment calls.

**OPS-016 External-effect protocol.**

1. Within a short transaction, lock the business object, approval, relevant quotas and budget in fixed order. Revalidate all current conditions. Create a unique `prepared` effect with request hash and reserve authority/cost; commit.
2. Dispatcher atomically changes prepared→dispatching with fence. Immediately before the network call, recheck cancellation, expiry, suppression and policy epoch. If invalid, cancel and safely release reservations.
3. Send one request using the provider idempotency token if supported and verified. Without it, persist a correlation marker in a provider-supported field if possible; this helps reconcile but is not a guarantee.
4. Definitive success→confirmed, settle reservation and approval use; definitive rejection→rejected, release only proven unused resources. Network timeout or process death after dispatching→uncertain. Never reset uncertain to prepared automatically.
5. Reconcile via provider IDs, supported client-reference lookup or authoritative campaign/message history. Absence on one eventually consistent read is not proof of failure. Unresolvable uncertainty produces a founder case and no further send.

A leased worker plus idempotency table provides local at-most-once dispatch for a logical effect, not global exactly-once sending. A provider's internal duplicate-send bug remains a provider incident. Multi-touch sequences are covered by the approved full manifest and native sequencer guarantees, not by pretending each touch was locally dispatched. All outbound automation remains gated by EXC-001.

**OPS-017 Budget mechanics.** Reserve pessimistic input/output/tool cost using a dated price configuration; include maximum repair/fallback calls inside the task cap. Reserve provider credit units as well as USD, and workspace plus company daily/monthly caps atomically. Unknown pricing means paid dispatch blocked. If invoice reconciliation later differs, record variance, freeze affected route and investigate; do not claim a provider can never charge beyond an estimate. Provider-issued hard limits complement local controls. Actual spend + outstanding reservations must remain within approved cap for any new work. A failed request can still be billable. Critical deterministic stop operations continue when AI/research budget is exhausted; maintain funded base infrastructure and a separately governed safety reserve.

