# Phase 6B Gate B1 - reviewed test enablement

Authority: the founder's reviewed B1 instruction and subsequent explicit one-time
exception for unpublished migration 0027. Core remains CLOSED. Accepted blockers
GB-001 through GB-007 may now be resolved through implementation and offline tests.

B1 authorizes ZERO real OpenAI/Anthropic requests, ZERO real credential resolution
and USD 0.00 live spend. B2 is a later, independently reviewed and separately
authorized execution. The prior USD 5.00 B2 ceiling is not active in B1.

## Starting state and scope

Continue on `phase-6b-gate-b-live-provider-preflight` based on protected main
`007977c8655b2d7bfca662f77e17befed68d6f12`. The initial blocked assessment made no
runtime edits. Its documents and ZIP remain available as historical evidence.

Ordinary submission remains fake-only. The distinct founder-authorized technical
preflight path must share AITask, ContextPack, ModelRun, validation, AIResult,
reservations and Phase 6A containment. Real connections may be testing only;
no real route may become active or generally available. Required account/model,
price, report, tenant, context, authority and budget checks fail closed.

Only one selected credential may be resolved after durable reservation and fresh
checks, then delivered separately through bounded stdin after containment. B1
uses synthetic canaries and mock transports. There are no model tools/actions,
SDK retries, automatic repair, fallback or uncertain replay. Each provider binding
has one task and at most one ModelRun. A dedicated gate budget covers both providers.

## Migration exception

Migrations 0001-0026 remain byte-for-byte unchanged. Before editing 0027, verify
and record: it is not on protected main, never pushed, not in a merged PR, used
only in local development, the rollback target is disposable with no history,
and historical migration hashes are unchanged. These conditions were verified.
A newly created loopback database with 98 empty application tables was rolled back
from 0027 to 0026 before revision. The previous development database was untouched.

Exactly one additive migration is used: `0027_phase6b_live_preflight`. Its hash is
recorded in the canonical manifest. Verify empty -> head, 0026 -> 0027, no-history
0027 -> 0026 -> 0027, repeated upgrade and populated-history downgrade refusal.
The exception is limited to this unreleased cycle. Published 0027 becomes immutable.

## Acceptance and boundaries

Run the canonical checks, full Python suite, focused B1 safety matrix, actual-role
RLS/concurrency tests, build, Chrome E2E, npm/Python audits and artifact scans.
Report exact results, limitations and all changed paths. No skipped safety tests.
Create the B1 review ZIP and detached SHA-256; preserve historical archives.

Requirement mapping: SYS-002/012/014/019/022; AI-001-005; DATA-048/053/054;
SEC-003/009/010; TEST-001/009/010/011/012/017/018/019/022/031.
ADR-025 records the extension to ADR-024. The handoff records acceptance evidence.

No commit, push, PR, merge, production activation, real business data, external
business outbound, deployment, Gate B2 execution or Phase 7 work is authorized.
