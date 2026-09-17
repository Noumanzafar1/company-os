# Part 23 — Testing Strategy

**TEST-001 Tenant isolation.** Seed A/B workspaces with identical names/domains and distinct secrets. Attempt reads, writes, joins, nested resources, list filters, exports, AI context, documents, cache reuse and webhook remapping. No A identity may return B content. Run with actual runtime DB roles, not migration owner. Test connection-pool context reset after success/error/cancellation.

**TEST-002 Suppression.** An active suppressed contact cannot be approved for new enrolment or released under an existing grant. Lead archive/reopen, identity merge, new campaign and changed email casing cannot bypass a matching suppression. Global check returns no other client's metadata.

**TEST-003 Opt-out race.** Against instrumented provider test recipients, send an opt-out one second before scheduled follow-up; capture receipt/persistence/provider-stop/dispatch timestamps. Test provider-native opt-out, mailbox reply, Company OS UI suppression and delayed/missing webhook independently. Required outcome: no send after the relevant provider execution boundary accepted the stop, and all locally known suppression prevents new local release. The stronger original one-second requirement remains OPEN until the provider contract and evidence resolve EXC-001; a mocked test cannot pass it. No live outbound release if unresolved.

**TEST-004 Duplicate effect.** Concurrent workers/replayed callbacks/new HTTP request IDs share the same logical effect key; provider is called once locally. Lost response never triggers a second unsafe call. Provider-native sequence duplicate behavior also tested.

**TEST-005 Stale approval.** Expire/revoke an approval while a job waits and immediately before dispatch. No effect starts under expired authority; already remote-scheduled work follows tested expiry/stop behavior.

**TEST-006 Material revision.** Change recipient address, cohort member, sender, content, claims, price, schedule, cap, offer or policy after approval. Every material change invalidates the grant. Removing a suppressed recipient cannot add a replacement.

**TEST-007 Ambiguous provider result.** Simulate provider accepts then response drops and worker crashes. Persist uncertain state, retain use/cost reservation, reconcile authoritative receipt, do not resend.

**TEST-008 Claim support.** Fabricate a plausible fact or cite a real source that does not support it. Schema validity alone cannot pass; message remains quarantined. Expired/retracted evidence blocks previously prepared outward claim.

**TEST-009 Budget concurrency.** Fifty simultaneous requests compete for a cap of ten charges. At most ten pessimistically priced requests dispatch; daily/workspace/company caps hold. Unknown billed outcomes retain reservations; correction records cannot free twice.

**TEST-010 Secret isolation.** Canary keys in runtime cannot appear in context, AI results, console, logs, traces, query strings, exports or error bodies. Malicious provider text asking for environment variables cannot access them.

**TEST-011 Injection/SSRF.** Malicious websites/emails request another workspace, extra tools, arbitrary URL exfiltration or metadata-service access. No permission change or network request succeeds. Test redirects/DNS rebinding/file URLs/oversized payloads.

**TEST-012 Restart/lease fencing.** Kill worker after claim, after commit and during external call. No accepted job vanishes, stale worker cannot commit, pure work resumes and uncertain effects remain held.

**TEST-013 Event atomicity.** Crash between proposed state and outbox/receipt writes. Either all local changes commit or none do. Duplicate/out-of-order events cannot revert final safety state.

**TEST-014 Webhook authenticity.** Bad signature/basic token/channel token rejected; unknown provider ID quarantined; delayed authenticated opt-out applied; workspace payload spoof ignored; duplicate acknowledges only persisted receipt.

**TEST-015 CRM ownership.** Native CRM change while local proposal is pending causes conflict/re-fetch, never dual-master overwrite. Native invalid stage appears with a warning and cannot bypass contract/payment onboarding gates.

**TEST-016 Mapping/identity.** Duplicate domains/subsidiaries do not auto-merge; corrupted mapping quarantines; reviewed merge and reversal preserve history and pause/recheck affected contacts.

**TEST-017 Document revocation.** Revoke Drive access after context assembly and during model execution. Future retrieval and output promotion stop; chunks/caches invalidate. Approved snapshot hashes detect edits.

**TEST-018 Auth/session/RBAC.** Disabled user/service, expired token, revoked membership, missing MFA, CSRF request and unapproved OAuth redirect all fail. Admin does not inherit business approval; AI cannot record L4 human acceptance.

**TEST-019 Environment containment.** Staging cannot dispatch to a real address even with a production-like payload, changed UI flag or provider sandbox failure. Enforce adapter environment assertion, recipient/domain allowlist and no production sending credential.

**TEST-020 Restore.** Restore database/files/config into isolated environment, measure RPO/RTO, reapply deletion/suppression ledger, reconcile post-backup provider activity, prove no deleted personal data resurfaces and no external effects replay.

**TEST-021 Provider limits/paging.** Exercise multiple pages, empty intermediate pages, end cursor, expired cursor, 429/Retry-After and credits exhausted. No skipped rows, infinite loop or query assumed complete after cap.

**TEST-022 AI failure/cost.** Refusal/truncation/schema failure/timeout produce bounded attempts and retained accounting. Unapproved fallback provider never receives context. Model promotion requires evaluation record.

**TEST-023 Brief/metrics.** Missing CRM/bank/reply stream produces unavailable/stale, never zero. Every number resolves to its metric definition and contributing snapshot. Currency, denominator, dedupe, late event and DST cases pass.

**TEST-024 Campaign drift/expiry.** Modify provider copy/sender/timing outside Company OS; detect drift and pause. Grant expiry cannot leave ungoverned remote follow-ups running; capability failure blocks release.

**TEST-025 Human takeover.** A newly assigned employee can find task inputs, SOP, prior attempts, evidence, pending authority and next step; they cannot see another workspace. Claim races produce one owner.

**TEST-026 Client gates.** Won deal without executed contract/deposit or approved credit cannot start delivery. Submitted deliverable without authorised acceptance never appears as accepted in client report.

**TEST-027 Safety capacity.** Saturate AI/research queue and exhaust its budget; suppression still gets the reserved worker slot and deterministic stop work. Infrastructure failure alerts externally.

**TEST-028 Retention/rights.** Source permission expires or client closes; downstream use/exports stop, deletion propagates and holds are respected. Audit metadata remains useful without unnecessary personal payloads.

**TEST-029 Reliability/performance.** Load envelope in Part 3 meets latency/queue targets; failed dependency is visible; no unbounded backlog retries. Confirm one day's API and workflow usage attribution reconciles.

**TEST-030 Founder absence.** No approval for 72 hours: permitted bounded work continues, grants expire, new external action waits and nothing interprets silence as consent.

**TEST-031 Build boundaries.** CI rejects prohibited imports, generated-contract drift, secret commits, unversioned migrations and unapproved dependencies. Phase output stops at the named gate.

**TEST-032 Provider deletion/export.** Test records/files exported with provenance and deleted in every connected test system; provider limitations become explicit retention exceptions before production.

Test layers: unit tests for normalization/scoring/state/policy/budget; real PostgreSQL integration tests for constraints/RLS/concurrency; adapter contract tests from redacted vendor fixtures and controlled account tests; workflow tests for durable transitions and replay; security tests for auth/isolation/SSRF; AI evaluations from AI-024; fault injection for crashes/network ambiguity; end-to-end founder approval→fake provider→reply→stop→brief. Live tests use founder-owned test mailboxes only, not real prospects. Contract tests do not prove native sequencer atomicity.

Every release has a test result manifest containing commit, migration head, environment, fixture/evaluation versions, passed/failed/skipped IDs and known limitations. Zero unresolved critical-control failures is mandatory. Staging shadow mode runs for five working days before live outbound; compare proposed work with founder decisions. A green unit-test suite alone never opens the live-sending gate.

