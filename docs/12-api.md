# Part 18 — API Specification

## Shared REST contract

**API-001** Base `/v1`; tenant routes use `/workspaces/{w}` abbreviated **W** below. UUID path IDs only. Browser traffic uses the authenticated console session and delegated identity; API verifies issuer/audience/signature/expiry and current membership. Service tokens are short-lived, audience-bound and operation-scoped. Webhook routes use connection-specific authentication and never user cookies.

GET responses: `200 {data,meta:{request_id,workspace_id,as_of,source,freshness,record_version?},next_cursor?}`. Collections use opaque signed cursor over `(sort_value,id)`, default 50/max 200, whitelisted filters/sorts, no raw SQL. Every object carries its version. `404` covers both absent and inaccessible IDs to avoid tenant existence leaks. Exports are explicit commands, not unlimited list calls.

Commands accept `Idempotency-Key` (UUID or opaque 8–128 chars), `If-Match` version for an existing target, closed typed body and optional approval reference. Create commands use a unique request key rather than If-Match. Same key+same semantic body returns the original result; same key+different body returns `409 IDEMPOTENCY_CONFLICT`. Key scope is workspace+actor+command type; effect-key scope remains separate and durable across new HTTP keys. Auth/policy is rechecked on every retrieval of a cached command response.

Synchronous internal command response: `200/201 {command_id,result_id,record_version,events[]}`. Async/effect response: `202 {command_id,job_id?,effect_id?,status_url,state}`. A 202 never means the provider completed the action. Errors: `400 INVALID_REQUEST`, `401 UNAUTHENTICATED`, `403 FORBIDDEN`, `404 NOT_FOUND`, `409 VERSION_CONFLICT|INVALID_TRANSITION|IDEMPOTENCY_CONFLICT`, `422 VALIDATION_FAILED|UNSUPPORTED_CLAIM`, `423 POLICY_BLOCKED|SUPPRESSED|APPROVAL_REQUIRED|APPROVAL_EXPIRED|STALE_CONTEXT`, `429 QUOTA_EXCEEDED`, `503 DEPENDENCY_UNAVAILABLE`. Error object: `{error:{code,message,request_id,retryable,field_errors?,safe_details?}}`.

Auth abbreviations: **R** permitted workspace reader; **RW** researcher; **SDR** communications role; **S** salesperson; **C** client-ops role; **F** founder with MFA for grants; **ADM** system admin; **SV** scoped service. These are capability profiles, not hardcoded user names. Part 20 defines role permissions. Audit **Q** = access metadata, restricted read/export logged; **C** = command attempt/result/actor/diff/events; **X** = C plus authority/effect/receipt. All POST rows use command idempotency and C/X unless explicitly stated. Approval column lists runtime authority; no endpoint may directly set arbitrary lifecycle `state`.

## Schemas used by endpoints

Use DATA entities as response DTOs with classified fields filtered by role. Named input schemas are closed objects:

- `CreateAccount {display_name,primary_domain?,country_code?,identity_discriminator,source_id,evidence_refs[]}`; `IdentityCorrection {field_changes:AllowedIdentityFields,evidence_ids[],reason}`; `ResearchRequest {icp_version_id,source_ids[],max_cost_usd}`.
- `CreatePerson {display_name,source_id,employment?:{account_id,title,evidence_id}}`; `CreateContact {person_id?,account_id?,kind,value,source_id}`; `CreateLead {account_id,person_id?,contact_point_id?,icp_version_id,offer_version_id}`.
- `EvidenceInput` = DATA-014 without common/derived fields; `SignalInput` = DATA-016 candidate fields; `ScoreRequest {subject_id,icp_version_id,evidence_ids[]}`; `EligibilityRequest {contact_point_id,purpose,policy_version_id}`.
- `CampaignDraft {name,icp_version_id,offer_version_id,sender_id,policy_version_id,schedule,limits,client_authority_ref?}`; `CampaignRevision {base_version_id,changes,reason}`; `FreezeCohort {lead_contact_pairs[],rendered_message_ids[],exclusions[]}`; `ApprovalRequest {action_type,target_id,target_version,scope_hash,expiry,usage_limit,cost_limit}`; scope is reconstructed server-side, not trusted from hash alone.
- `Grant {decision:approve/reject/revise,rationale,expected_scope_hash}`; `Release {campaign_version_id,approval_id}`; `Stop {reason,incident_id?}`; `DraftRequest {task_type,subject_refs,context_version_refs}`.
- `CRMCreate {account_id,meeting_id?,engine,proposed_stage,amount?,currency?,amount_basis,next_action,next_action_at,evidence_refs}`; `CRMChange {expected_provider_snapshot_hash,allowed_changes,evidence_refs,approval_id?}`; `MeetingOutcome {attendance,notes_document_id,consent_status,evidence_refs}`.
- `TaskCreate {type,subject_id,accountable_role,due_at?,input_refs,sop_version_id?}`; `TaskResolve {output_ref,outcome,reason?}`; `DecisionInput {subject_id,decision_type,outcome,summary,evidence_refs,review_at?}`.
- `DocumentRegister {connection_id,external_file_id,classification,purpose}`; `UploadIntent {folder_resource_id,title,media_type,byte_count,sha256}`; `SourceApprovalInput {source_id,rights_document_version_id,allowed_purposes,allowed_fields,expires_at}`.
- `AIRequest {task_type,task_version,subject_refs,context_refs,max_cost_usd}`; server builds policy/tools/provider allowlist. `JobRetry {reason,changed_cause_ref}`; `PolicyActivate {policy_version_id,decision_id}`; `BudgetChange {period,category,new_limit,decision_id}`.
- `ExportRequest {resource_type,explicit_filter,purpose,max_records,recipient_or_folder,approval_id}`; `EngagementStart {contract_ref,payment_or_credit_ref,scope_version_id}`; `AcceptanceInput {deliverable_id,decision,evidence_document_version_id}`.

## Endpoint registry

Each row states purpose, auth, input→output, errors beyond common ones, audit and approval. GET rows use Q and no idempotency header; POST rows use the shared command behavior. These inherited rules are part of every endpoint contract.

| ID | Method/path | Purpose and auth | Input → output | Extra errors; audit; approval |
|---|---|---|---|---|
| API-002 | GET `/me` | Current user/workspaces; authenticated | none→UserProfile + memberships | SESSION_REVOKED; Q; L0 |
| API-003 | POST `/auth/logout` | End app session; user | empty→204 | Session-local idempotent; C; no approval |
| API-004 | GET W`/accounts`, GET W`/accounts/{id}` | Account list/detail; R | filters/ID→AccountPage/Account | Common; Q; L0 |
| API-005 | POST W`/accounts` | Create sourced identity; RW/SV | CreateAccount→Account | IDENTITY_CONFLICT; C; L1 |
| API-006 | POST W`/accounts/{id}/propose-correction` | Preserve identity conflict; RW | IdentityCorrection→Task | SOURCE_NOT_ALLOWED; C; L1 |
| API-007 | POST W`/accounts/{id}/research` | Queue research; RW/SV | ResearchRequest→Job | RIGHTS_EXPIRED/BUDGET; C; L1 under source policy |
| API-008 | POST W`/identities/merge` | Reviewed same-tenant merge; F | survivor_id,retired_id,decision_id→Task | ACTIVE_EFFECT/TYPE_MISMATCH; X; L3 |
| API-009 | GET W`/people`, GET W`/people/{id}` | People/relationships; R | filters→PersonPage/Person | Common; Q restricted; L0 |
| API-010 | POST W`/people`, POST W`/contact-points` | Register sourced person/contact; RW/SV | CreatePerson/CreateContact→entity | IDENTITY_CONFLICT; C; L1 |
| API-011 | POST W`/contact-points/{id}/verify` | Verify email; RW/SV | source_policy_id,max_cost→Job | UNSUPPORTED_CHANNEL/BUDGET; X; L2 source policy |
| API-012 | GET W`/leads`, GET W`/leads/{id}` | Lead worklist/provenance; R | filters→LeadPage/Lead | Common; Q; L0 |
| API-013 | POST W`/leads` | Create prospecting relationship; RW | CreateLead→Lead | DUPLICATE_LEAD; C; L1 |
| API-014 | POST W`/leads/{id}/assess-eligibility` | Deterministic assessment; RW/SV | EligibilityRequest→assessment | STALE_EVIDENCE; C; L1 |
| API-015 | POST W`/leads/{id}/qualify` | Human sales qualification; F/S | evidence_refs,next_action,decision_id→Lead | REQUIRED_EVIDENCE_MISSING; C; L3 |
| API-016 | POST W`/leads/{id}/disqualify`, POST W`/leads/{id}/archive` | Explicit lifecycle command; RW/F | reason,evidence_refs→Lead | ACTIVE_ENROLLMENT; C; L1 or human judgment |
| API-017 | GET W`/evidence`, POST W`/evidence` | Read/register observation; R / RW/SV | filter / EvidenceInput→page/Evidence | INVALID_REFERENCE/RIGHTS; Q/C; L0/L1 |
| API-018 | POST W`/evidence/{id}/retract` | Withdraw unsupported evidence; RW/F | reason,replacement_id?→receipt | Common; C; L1 protective |
| API-019 | GET W`/signals`, POST W`/signals` | Signal review; R / RW/SV | filter / SignalInput→page/Signal | BAD_EVENT_DATE; Q/C; L0/L1 candidate |
| API-020 | GET W`/scores/{id}`, POST W`/scores/calculate` | Explain/recompute score; R / RW/SV | ID / ScoreRequest→Score | POLICY_VERSION_MISSING; Q/C; L0 calculation/L1 persistence |
| API-021 | GET W`/campaigns`, GET W`/campaigns/{id}` | Campaign scope/execution; R | filter/ID→page/detail | Common; Q; L0 |
| API-022 | POST W`/campaigns` | Create draft; SDR/F | CampaignDraft→Campaign | SOURCE_POLICY_MISSING; C; L1 |
| API-023 | POST W`/campaigns/{id}/versions` | Explicit revision; SDR/F | CampaignRevision→Version | VERSION_CONFLICT; C; L1, invalidates grant |
| API-024 | POST W`/campaigns/{id}/freeze-cohort` | Fix audience/messages; SDR | FreezeCohort→manifest | DUPLICATE_CONTACT/QA_MISSING; C; L1 |
| API-025 | POST W`/campaigns/{id}/run-qa` | Validate exact version; SDR/SV | version_id→Job | MANIFEST_INCOMPLETE; C; L1 |
| API-026 | POST W`/campaigns/{id}/request-approval` | Assemble review case; SDR | ApprovalRequest→Approval | QA_FAILED; C; request only |
| API-027 | POST W`/campaigns/{id}/release` | Deploy bounded cohort; F/SV | Release→Effect/Job | PREFLIGHT_FAILED/SUPPRESSED/STALE_GRANT; X; L2 granted L3 scope |
| API-028 | POST W`/campaigns/{id}/pause`, POST W`/enrollments/{id}/stop` | Protective stop; SDR/F/SV | Stop→Effect/Job | PROVIDER_UNCERTAIN; X; L1 |
| API-029 | POST W`/campaigns/{id}/request-resume` | New approval after pause; F/SDR | version_id,resolution_refs→Approval | INCIDENT_UNRESOLVED; C; L3 required |
| API-030 | GET W`/messages`, GET W`/messages/{id}` | Draft/outcome with source link; SDR/S | filters/ID→page/Message | Common; Q restricted; L0 |
| API-031 | POST W`/messages/draft` | Prepare exact message; SDR/SV | DraftRequest→Job | SUPPRESSED/STALE_CONTEXT; C; L1 |
| API-032 | POST W`/messages/{id}/request-approval` | Substantive reply approval; SDR/S | ApprovalRequest→Approval | CLAIM_QA_FAILED; C; request only |
| API-033 | POST W`/messages/{id}/dispatch` | Send approved substantive reply via verified provider capability; F/SV | approval_id→Effect | PREFLIGHT_FAILED/SUPPRESSED/STALE_GRANT; X; L2 exact L3 grant |
| API-034 | GET W`/interactions` | Read observed history; SDR/S/C | subject/date filters→InteractionPage | Common; Q restricted; L0 |
| API-035 | POST W`/suppressions` | Immediate protective block; RW/SDR/F/SV | contact_id,scope,reason,source_ref→Suppression | Invalid broad scope returns narrower protective hold; X; L1 |
| API-036 | POST W`/suppressions/{id}/request-release` | Evidence of changed permission; F | decision_id,permission_evidence→Task | NO_VALID_PERMISSION; C; L3 review, no direct unsuppress |
| API-037 | GET W`/opportunities`, GET W`/opportunities/{id}` | CRM-backed pipeline/detail; R | filters/ID→projection | Source stale included in meta; Q; L0 |
| API-038 | POST W`/opportunities/create-in-crm` | Create accepted commercial record; F/S | CRMCreate→Effect | CRM_CONFLICT/PREFLIGHT; X; L3 |
| API-039 | POST W`/opportunities/{id}/request-change` | Material CRM change; F/S | CRMChange→Effect or Approval | PROVIDER_VERSION_CONFLICT; X; L3; won L4 human decision |
| API-040 | GET W`/meetings` | Calendar projection; R | date range→MeetingPage | Common; Q; L0 |
| API-041 | POST W`/meetings/{id}/record-outcome` | Attendance and consent; F/S | MeetingOutcome→Meeting | EVIDENCE_MISSING; C; human L1 record |
| API-042 | POST W`/meetings/{id}/prepare-brief` | Meeting preparation; S/SV | expected_meeting_version→Job | STALE_MEETING; C; L1 |
| API-043 | POST W`/opportunities/{id}/prepare-proposal` | Draft from approved worksheet; S/F | worksheet_id,scope_version_id→Job | PRICE_NOT_APPROVED; C; L1 draft |
| API-044 | POST W`/proposals/{id}/request-dispatch-approval`, POST W`/proposals/{id}/dispatch` | Review/send exact proposal; S then F/SV | ApprovalRequest / approval_id→Approval/Effect | TERMS_UNRESOLVED/STALE_GRANT; C/X; L3 and L4 price record |
| API-045 | GET W`/tasks`, POST W`/tasks` | Shared work queue; R / authorised role | filter / TaskCreate→page/Task | RESOURCE_NOT_ALLOWED; Q/C; L0/L1 |
| API-046 | POST W`/tasks/{id}/claim`, POST W`/tasks/{id}/resolve` | Human/service handover; matching role | empty / TaskResolve→Task | ALREADY_CLAIMED/ACCEPTANCE_REQUIRED; C; L1 |
| API-047 | POST W`/decisions` | Record human decision; F | DecisionInput→Decision | HUMAN_REQUIRED; C; L3/L4 record |
| API-048 | GET W`/approvals`, GET W`/approvals/{id}` | Review exact scope/diff; F or requester read | filter/ID→page/ApprovalCase | Common; Q; L0 |
| API-049 | POST W`/approvals/{id}/decide` | Grant/reject/revise; F fresh MFA | Grant→Approval | MFA_REQUIRED/SCOPE_CHANGED/EXPIRED; C; L3 |
| API-050 | POST W`/approvals/{id}/revoke` | Withdraw authority; F/security SV | reason→Approval | Common; X; L1 protective |
| API-051 | GET W`/jobs`, GET W`/jobs/{id}` | Runtime state and safe logs; F/ADM | filters/ID→page/detail | Common; Q; L0 |
| API-052 | POST W`/jobs/{id}/retry`, POST W`/jobs/{id}/cancel` | Controlled recovery; F/ADM | JobRetry / reason→Job | UNCERTAIN_EFFECT/CAUSE_UNCHANGED; C; L1; no effect reset |
| API-053 | GET W`/events` | Trace/correlation history; F/ADM | subject/correlation/cursor→EventPage | Common; Q restricted; L0 |
| API-054 | GET W`/documents`, POST W`/documents/register` | Catalogue known file; R / C/RW | filters / DocumentRegister→page/Document | ACL_UNVERIFIED; Q/C; L0/L1 |
| API-055 | POST W`/documents/upload-intent` | Prepare private upload; authorised role | UploadIntent→bounded upload grant | DESTINATION_NOT_ALLOWED; X; L2 approved folder |
| API-056 | GET W`/knowledge/search` | Scoped approved retrieval; R/SV | q,kind,limit≤20→excerpts+refs | STALE_KNOWLEDGE; Q restricted; L0 |
| API-057 | POST W`/ai-tasks`, GET W`/ai-tasks/{id}` | Request/inspect bounded AI work; authorised role/SV | AIRequest / ID→Job/AIResult | NO_APPROVED_ROUTE/BUDGET; C/Q; L1 |
| API-058 | GET W`/metrics`, GET W`/daily-brief` | Traceable metrics/brief; R | period/definition_version→MetricEnvelope[]/DailyBrief | Missing data represented, not zero; Q; L0 |
| API-059 | GET W`/attention`, POST W`/attention/{id}/snooze` | Decisions and review timing; F | filters / until,reason→items/item | CRITICAL_ITEM_CANNOT_HIDE; Q/C; L0/L1 |
| API-060 | GET W`/health` | Integration/runtime freshness; F/ADM | none→WorkspaceHealth | Common; Q; L0 |
| API-061 | GET `/health/live`, GET `/health/ready` | Hosting probes; minimal public response | none→status only | 503 if not ready; no sensitive fields; no approval |
| API-062 | POST `/webhooks/{provider}/{connection_token}` | Durable callback intake; provider auth | raw verified payload→202 or duplicate 200 | AUTH_FAILED/UNSUPPORTED_SCHEMA; X observation; not human approval |
| API-063 | POST `/service/jobs/{id}/result` | n8n bounded completion; SV capability | expected_fence,result_ref→receipt | BAD_FENCE/WRONG_WORKSPACE; C; no arbitrary status |
| API-064 | POST W`/sources/{id}/request-approval`, POST W`/policies/activate` | Rights/policy management; F | SourceApprovalInput / PolicyActivate→Approval/Policy | INVALID_RIGHTS/STALE_DECISION; C; L3 |
| API-065 | POST W`/budgets/request-change` | Budget change case; F | BudgetChange→Approval | INVALID_PERIOD; C; L3 |
| API-066 | POST W`/exports/request` | Bounded authorised export; F | ExportRequest→Approval/Job | RIGHTS_DENIED/TOO_LARGE; X; L3 |
| API-067 | GET W`/clients`, GET W`/engagements/{id}` | Client work/risks; C/F | filters/ID→page/detail | Common; Q; L0 |
| API-068 | POST W`/engagements/start-onboarding` | Enforce contract/payment gate; F | EngagementStart→Engagement | CONTRACT_OR_PAYMENT_MISSING; C; L2 recorded scope |
| API-069 | POST W`/deliverables/{id}/record-acceptance` | Human acceptance; F/authorised delivery lead | AcceptanceInput→Acceptance | HUMAN_REQUIRED/WRONG_SCOPE; C; L4 human record |
| API-070 | POST W`/engagements/{id}/request-close` | Handoff/revocation/deletion plan; F/C | scope_refs,retention_plan→Approval | OPEN_OBLIGATION; C; L3 |
| API-071 | POST W`/privacy-requests` | Register rights request; F/C/SV | subject_id,kind,source_ref→PrivacyRequest | INVALID_SUBJECT; C; L1 protective |
| API-072 | GET W`/provider-connections`, POST W`/provider-connections/{id}/preflight` | Capability status/test request; F/ADM | none / test_profile→report/Job | SECRET_UNAVAILABLE; Q/C; L1 test; live effects separately approved |

Managed authentication handles sign-in, recovery and MFA; do not build password endpoints. Auth provider redirects and session bootstrap are frontend integration details with CSRF/state/PKCE as applicable, specified and tested in Phase 2. No generic DELETE or PATCH-status endpoints exist for approvals, campaigns, jobs or commercial stage. Unlisted functionality stays disabled until added to the contract and phase gate.

