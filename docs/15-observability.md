# Part 21 — Audit and Observability

**OPS-018 AuditEntry v1:** `id`, `workspace_id`, `occurred_at`, `recorded_at`, `actor_type`, `actor_id`, `delegated_user_id?`, `auth_context_ref?`, `action_type`, `target_type`, `target_id`, `target_version_before?`, `target_version_after?`, `request_id`, `correlation_id`, `causation_id?`, `command_id`, `decision {allow|deny|require_approval|quarantine}`, `policy_version`, `approval_id?`, `approval_scope_hash?`, `idempotency_key_hash?`, `effect_id?`, `provider_request_id?`, `change_summary`, `redacted_diff_ref?`, `evidence_refs[]`, `model_run_ids[]`, `outcome`, `error_code?`, `payload_hash`, `previous_export_hash?`. Concise reason summaries only; no hidden model reasoning, secrets or unnecessary raw personal data.

Application DB roles can INSERT and SELECT permitted audit rows but not UPDATE/DELETE. Retention jobs use a separately controlled archival procedure. Export daily audit segments and manifests to restricted storage with checksums and separate credentials; if immutable retention controls are required, verify storage capability rather than describing ordinary Drive permissions as immutable storage. Hash chains detect some changes but do not replace access control or off-system copies.

**OPS-019 Structured logs** include timestamp, severity, environment, service, release SHA, workspace pseudonymous ID, request/trace/correlation IDs, command/job/attempt/effect IDs, handler, outcome, duration, provider/error code, retry-after, token/cost counters and redaction version. Business content lives in authorised records. Retain ordinary logs 30 days initially; audit/runtime references 12 months. Console log views filter credentials and personal data before display.

Metrics: API latency/error rate, job age/depth by priority, leases expired, retry/DLQ counts, handler success/failure, provider latency/429/auth failures, webhook persistence lag, reconciliation age/divergence, unconfirmed stops, uncertain effects, AI validation failures/usefulness/cost, quota reserved/used, source/knowledge expiry and backup/restore age. Distinguish provider request failure from business failure and model quality failure.

Initial alerts: any confirmed suppressed/duplicate send; cross-workspace denial spike or actual leak; unconfirmed opt-out >60 s; critical sync >5 min; DB unavailable >60 s; worker heartbeat >60 s; same job type three terminal failures; monthly budget 80% and exhaustion; any provider auth revocation; restore failure. Deduplicate by incident/workspace/provider and update existing alert rather than sending every retry. Console is primary attention record; use one founder-chosen notification route plus email fallback during implementation. P0 immediately; P1 within five minutes; P2 daily brief. Notification delivery failure is recorded and surfaced through independent monitoring. No messages are sent as part of this specification phase.

# Part 22 — Failure and Recovery Design

All cases retain causation, job/effect IDs and latest trustworthy state. “Notify” means eventual configured founder incident notification, not an action performed now.

| Failure | Automatic response and data state | Retry/quarantine | Founder notification and safe fallback |
|---|---|---|---|
| Apollo unavailable | Keep research pending; preserve known evidence, mark freshness | Bounded transient retries; auth/rights failure blocks connection | P2 unless affects deadline; authorised manual/public research, no invented enrichment |
| Verifier unavailable | New email eligibility remains unknown; do not reuse expired verification | Bounded reads; possible billed timeout retains reservation | P2/P1 if campaign imminent; pause new enrolments |
| Pipedrive unavailable | Pending commercial command remains pending; projection visibly stale | Retry reads; uncertain write reconciles before repeat | P1 for urgent sales; native CRM work with later reconciliation, no competing local master |
| Smartlead unavailable | Block release; request protective stop where possible; observed state unknown | No blind effect retry; safety retry contract | P0 for failed suppression, otherwise P1; native provider intervention; never claim already-queued sends stopped |
| OpenAI unavailable | Persist task waiting; no business state lost | Approved evaluated fallback only within cap | P2; deterministic brief/manual draft |
| Anthropic unavailable | Same, respecting workspace provider policy | No unapproved cross-provider fallback | P2; keep complex proposal pending |
| Malformed/refused/incomplete model output | Save run status, no promoted result | One format repair if appropriate within cap; refusal not circumvented; then fail/quarantine | Task owner; human completion |
| Job timeout/process death | Expire lease, fence stale worker; preserve attempt | Retry pure work; external dispatch→uncertain reconciliation | Escalate repeated failures; no loss of queued work |
| Duplicate event | Return receipt, skip already committed consumer | No duplicate side effect | Routine telemetry; incident only if attempted duplicate effect |
| Missing webhook | Scheduled reconciliation retrieves authoritative state | Poll with overlap/pagination | P1 when freshness threshold exceeded; pause dependent work |
| Old/out-of-order webhook | Apply protective information; fetch latest ordinary projection | Deduplicate, never reverse suppression | No alert for benign delay; critical lag escalates |
| Uncertain send/enrolment | Keep effect and authority reservation; stop additional conflicting work | Reconcile only; no automatic resend | P1/P0 depending impact; founder inspects provider receipts |
| Expired/stale approval | Deny dispatch, cancel prepared effects, pause affected native schedule if necessary | New approval required | Approval queue; no consent from silence |
| Budget exhausted | Stop paid discretionary tasks; retained queued work | No retry until cap/period/reservation resolved | Warning at 80%, P1 exhaustion; safety lane remains funded |
| Suppression conflict | Deny wins; local hold regardless of provider active state | High-priority monotonic stop, quarantine mismatch | P0 if known send/failed propagation; pause all affected sender scope |
| Cross-workspace query | Deny before returning record; audit safe metadata | Quarantine agent task; revoke suspect capability | P0 actual exposure, P1 attempted exploit; no “helpful” alternate lookup |
| Corrupted external mapping | Stop mapping-dependent processing | Quarantine raw event and IDs; reviewed correction | P1; no fuzzy company-name remap |
| Incorrect identity merge | Pause affected enrolments; preserve immutable history | Reviewed compensating split, reverify contacts | P1; founder evidence review before resume |
| Hallucinated claim | Reject/quarantine output and dependent draft | New task with supported evidence or approved generic wording | Reviewer/owner; repeated critical regression disables route |
| Prompt injection | Treat as source data; reject forbidden tool request | Quarantine suspicious task/source when needed | Security event; cannot grant tools or access another tenant |
| Founder unavailable | Continue current bounded L0–L2 authority; expire grants normally | Wait for L3/L4; protective stops continue | Escalate only to pre-authorised continuity contact; otherwise remain paused |
| n8n restart/outage | Canonical jobs unchanged; callbacks can arrive twice | Resubmit only idempotent connector task | P2; direct runtime handles critical schedules/stops |
| Google OAuth/ACL revoked | Stop retrieval, invalidate chunks/context and pending use | Reauth/review, no permission-broadening retry | P1 affected client; approved static snapshot only if rights remain valid |
| Calendar sync token invalid | Mark partial/stale and perform full bounded resync | Replace projection only after complete reconciliation | P2; preserve meeting IDs and recurrence keys |
| DB recovery from older backup | Start isolated with sends disabled; replay tombstones/suppression then reconcile all providers | Rebuild projections, not external effects | Founder recovery approval before send resumption |
| Provider schema changes | Contract validator rejects unknown material fields/status | Quarantine, update adapter under tests | P1 if safety stream affected; pause automation |
| Client terminates/source rights revoked | Suspend processing and sending; queue handoff/erasure | Track each provider receipt and unresolved task | Founder closure case; no cross-client reuse |
| Native provider configuration changed | Mark drift and request pause | New version/approval or restore reviewed exact config | P1; cannot rely on old campaign hash |
| Clock skew/DST change | Use DB UTC and zone rules; stale auth/timestamp checks fail safe | Correct infrastructure clock; no burst catchup sends | P1 if affects authority; regenerate schedule after review |
| Notification provider unavailable | Incident remains in console; alternate route if approved | Bounded idempotent notification retry | Independent uptime alert; no silent “delivered” status |

Recovery ordering is stop → preserve evidence → restore trusted local state → reapply erasure/suppression/access revocations → reconcile provider effects and commercial projections → validate invariants → founder authorises resume. Recovery is not “restart all failed jobs.”

