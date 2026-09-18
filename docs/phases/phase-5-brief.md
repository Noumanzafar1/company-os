# Phase 5 — Policy, approvals and founder control

Authority: Nouman's explicit Phase 5 request, 18 September 2026. Phase 4 is
closed at `bf12861bc9b711a3669ba62c2ab56596035b5d0e`. Development branch:
`phase-5-policy-approvals-founder-control`. Independent review precedes any
commit, push, PR or merge. Phase 6, real providers and deployment are excluded.

The numbered specification and accepted ADRs govern. This brief supersedes only
the old phase authorization in AGENTS.md. No architectural control is waived.

## Schema map — before migration

| Object | Implement | Table | Owner | Purpose | Deferred dependency |
|---|---|---|---|---|---|
| DATA-045 policy | Yes | policies | Policy | Active immutable version pointer | Real business policy |
| DATA-045 version | Yes | policy_versions | Policy | Closed rules, effective/expiry bounds | Provider rules |
| Action definition | Code registry | None | Policy | Closed actions and executor classes | Future phase actions |
| Command receipt | Yes | authority_command_receipts | Policy | Immutable command response and idempotency key | None |
| DATA-046 request | Yes | approval_requests | Policy | Exact immutable proposal and lifecycle | Real campaign cases |
| DATA-046 manifest | Yes | approval_manifests | Policy | Immutable human authority | None |
| Exact targets/snapshot | Yes | approval_targets | Policy | Typed tenant FK, version and payload evidence | Real campaign recipients |
| DATA-047 use | Yes | approval_uses | Policy | One reservation per canonical effect | None |
| Use resolution | Yes | approval_use_results | Policy | Append-only consume/release evidence | None |
| Policy decision | Yes | policy_decisions | Policy | Immutable evaluation and reasons | None |
| Human decision/revocation | Yes | approval_decisions | Policy | Immutable MFA/actor/reason history | L4 commercial records |
| Freeze | Yes | authority_freezes | Policy | Protective workspace/action hold | Real integration classes |
| Synthetic target | Yes | authority_test_targets | Test fixture | Mutable version, rights and suppression demonstration | Real target adapters |
| Execution authority reference | Yes | authority_bindings | Policy/runtime | Bind immutable runtime input to exact manifest | Real effects |
| Authority snapshot | Embedded in manifest/target rows | No separate table | Policy | IDs, hashes, versions, bounded values | None |
| Provider connections | No | Existing fake_endpoints only | Runtime | Offline fake adapter | Later provider phases |
| AI/campaign/payment/contract | No | None | Future modules | Documentation boundaries only | Phase 6+ |

## Required gate

Implement SYS-002/005/006/014/016/019/022/023/025; SEC-001/003/004/006/007/008;
DATA-045/046/047 and synthetic DATA-022/023/052/053/057 integration;
API-048/049/050/059/060/064 subsets; UI-003/014/015; TEST-001/002/004/005/006/
007/009/010/018/019/028/030/031. Provider tests remain explicitly fake evidence.

Policy activation invalidates prior outstanding grants (DATA-045, TEST-006).
All grants require fresh verified MFA (SEC-008), including preauthorization.
L4 has no executable route. Safety contraction never authorizes replacements.
Unknown or missing authority fails closed. The database clock determines expiry.
Authority and budget reserve in one transaction; dispatch rechecks authority.
An uncertain effect retains its use until reconciliation proves an outcome.

Verification must include all preceding regressions, populated runtime-role RLS,
50-way use contention, mutation/expiry/revocation tests, migration round trips,
API/contracts, console/build/browser gates, dependency audits and diff checks.
Report exact evidence and limitations in phase-5-handoff.md; never infer PASS.
