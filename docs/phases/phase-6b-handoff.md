# PHASE 6B HANDOFF



## Gate Status



PHASE 6B CORE COMPLETE — LIVE PROVIDER PREFLIGHT REQUIRED

Stop at independent review. This is a local core gate result, not Phase 6B live
closure or permission to commit, enable providers or begin Phase 7.



## Git



Accepted Phase 6A main: `41e27ff8cb211b1d3a80d702995cad2a9f28567e`.

Reviewed feature ancestor: `fc6921d148ea4d7d163119e5da3560caf653011c`.

Origin was fetched and the baseline verified before creating

`phase-6b-ai-gateway-evaluation`. Changes remain uncommitted. Existing review ZIPs

were preserved. No commit, push, PR or merge was performed.



## Objective



Implement the user-authorized Phase 6B Gate A: a provider-neutral proposal gateway

which cannot own identity, business truth, approval, budgets or external effects.

The canonical specification retains its Phase 1 design status. The governing

implementation change is the explicit 109-section Phase 6B request and

[phase brief](phase-6b-brief.md). Nouman remains the acceptance reviewer.



## Architecture



[ADR-024](../adr/024-governed-ai-gateway.md) extends the existing runtime and

authority boundaries and remains pending independent review. API and worker use

shared application commands, the existing job queue, transaction-local tenant

context, pessimistic reservations and human decisions/manifests/uses. No new

workflow engine, general agent runtime, vector store or AI memory exists.



## AITask



AI-001 is a closed immutable task with task/version, workspace, subject/evidence

references, allowed providers, context, current policy, schema, synthetic

sensitivity, deadline, token/cost limits and maximum calls. Browser requests accept

only the synthetic task type and a closed scenario. API-057 returns the durable

task/job reference. Actor-scoped command receipts plus a workspace logical-key

lock make duplicate submission idempotent.



## Context Packs



AI-002 packs contain versioned synthetic evidence and document references, scoped

excerpts, policy, authorization/permission epochs, timestamps, omissions,

conservative token bounds and a canonical content hash. Each task gets an

independently revocable fixture source. These are synthetic document/evidence

fixtures, not general knowledge ingestion or unrestricted retrieval. Access,

source rights/version, workspace epoch, active route, freeze, policy and expiry

are rechecked before calls, during execution and before result admission/read.

Revocation withholds both context and derived results.



## Prompt Registry



Immutable, versioned, content-hashed prompt records label source material as

untrusted data. Only evidence, excerpts and omissions enter the provider user

input. Task authority and capability configuration never come from source text.



## Schema Registry



The immutable schema registry binds the route to a provider-neutral strict-object

schema. Full local Pydantic validation enforces bounded claims, unknowns,

uncertainties and an empty action array even where provider schema subsets omit

length/format constraints. No chain-of-thought field is requested or stored.



## AIRoutes



AI-003 immutable route versions bind model snapshot, prompt/schema/price versions,

context policy, provider options, sensitivity, region policy, token/cost limits

and timeout. A separate mutable lifecycle pointer permits draft, evaluated,

active, superseded and disabled states. Only fake technical routes are seeded;

the fake OpenAI route is the explicitly provisioned synthetic bootstrap. Live

providers have no active route. Missing or disabled routes fail closed.



## Route Promotion



Frozen candidate/current comparisons produce immutable evaluation records. A

founder request binds the exact route content hash, evaluation and dataset

binding, prior active route and rollback route. The existing fresh-MFA human

decision creates one manifest/use for one zero-spend technical activation.

Database triggers reject worker promotion and activation without this exact use.

Promotion does not activate a provider or grant business action authority.



## Provider Connections



DATA-048 is limited to scoped AI connection metadata, status, environment and

capability report. Real connection rows are unconfigured, with null credential

references; database constraints prevent enabling them in this core release.

Fake connections are explicitly enabled synthetic fixtures.



## Fake OpenAI Adapter



Deterministic bounded responses cover success, format repair, malformed output,

refusal, incomplete output, invalid evidence, injection, unsafe output, invalid

usage, overload, rate limits, timeouts and uncertain calls. No network is used.



## Fake Anthropic Adapter



Implements the same neutral port and adversarial scenarios with distinct provider

and model attribution. The evaluation harness uses the same frozen dataset for

both routes. Agreement between the two fakes is not evidence of business facts.



## OpenAI Adapter



Official pinned SDK translation uses Responses with strict JSON schema,

store=false, no tools, explicit token limits, fixed HTTPS transport and zero SDK

retries. Refusal, incomplete output, request ID, reported model and usage are

normalized. Only mock HTTP contract tests ran; no real API call occurred.



## Anthropic Adapter



Official pinned SDK translation uses Messages/output_config.format, explicit

max_tokens and no tools. Cache-read/cache-creation usage and stop reasons are

normalized. The closed explicit client relies on the pinned SDK's tested exact-type
discovery gate; see ADR 024 and the correction handoff for the precise mechanism.

Only mock HTTP contract tests ran; no real API call occurred.



## Provider Secret Boundary



The fixed trusted runner receives no inherited database passwords, session

tokens, ambient provider keys or unrelated environment. The only inherited

Windows variables are SystemRoot/WINDIR. The one selected synthetic credential

travels in a bounded second stdin message after process containment, separately

from the execution envelope. It is never in argv, disk or model context.

The current channel accepts only synthetic credentials and a fixed mock transport.

Provider mismatch is rejected before launch. Output and metadata redact the

selected key; errors are closed codes and raw headers/responses are not logged.

This is not a hostile-code sandbox.



## Provider Preflight



[Provider research](phase-6b-provider-preflight.md) records official documentation,

SDK versions, exact candidate snapshots and the difference between documented and

account-verified capabilities. Live account, entitlement, billing, price, rate,

region and retention fields remain unverified. A credential environment variable

cannot enable live calls. Further reviewed wiring and separate founder authority

are required before Gate B can run.



## AIResult



AI-004 retains only a locally validated proposal or an explicit refused,

incomplete or quarantined outcome, with claim/evidence map, unknowns,

uncertainties, validation defects, route/provider/model attribution, usage,

reservation, cost and latency. Accepted means an accepted proposal, never a

business-state transition or approved external action.



## ModelRun Accounting



Each possible chargeable attempt gets a durable ModelRun and unique request key

before child launch. The database binds the active job lease, reservation,

provider/model, prompt and price. Retries and repairs create new counted rows.

Terminal calls cannot be rewritten. Crash recovery changes an unresolved started

call to uncertain and prevents automatic replay.



## Cost / Budgets



Reservations use maximum input/output exposure and check the remaining call cap,

task and route cost cap, current workspace calendar-day/month budgets and the

existing company cap under serialization. Usage settles with the immutable price

version. Cached and cache-creation tokens have separate rates. Missing, invalid or

ambiguous usage retains pessimistic exposure. Technical prices are simulated USD;

none of these fixtures incurred provider spend. Expired/unprovisioned budget

periods deny work; they do not renew automatically.



## Retry / Timeout / Uncertainty



SDK retries are zero. A format repair is one separately reserved call, never a

repair of evidence, policy, refusal or secret violations. Retryable overload/rate

failures release the job slot and respect Retry-After plus bounded runtime delay.

Uncertain transport/process outcomes retain reservations and do not replay.

The Phase 6A supervisor owns hard deadlines, cancellation, process-tree cleanup

and bounded IPC; late responses cannot bypass fencing or context revalidation.

No cross-provider fallback is configured; the denied-fallback fixture remains on

its original provider.



## Output Validation



Provider-constrained output is insufficient. Local byte/field bounds, closed

schema, forbidden capabilities, usage bounds and current-context checks apply.

Invalid raw output is discarded; only bounded defect codes persist. An unsafe

output cannot reach the normal proposal path through a repair.



## Claim / Evidence Validation



The closed task supports only `fixture_colour=blue` with an exact evidence UUID

from the current pack. A fabricated evidence ID or unsupported red value is

quarantined even if its JSON is valid. Missing business facts remain unknown.



## Tool Boundary



Allowed tools and proposed actions are empty closed tuples. The model cannot

fetch URLs, select workspaces, read files, run SQL/shell/browser actions, choose

providers, mutate routes, spend outside reservations or delegate. Provider

transport destinations are fixed and redirects/proxies are disabled.



## Evaluation Harness



AI-005/DATA-054 use four frozen, separately labelled synthetic datasets: seed,

development, holdout and adversarial. Evaluations enqueue ordinary governed

AITasks for both routes, then aggregate their durable outcomes and accounting.

Metrics include expected outcomes, schema validity, refusal, incomplete,

quarantine, evidence rejection, injection/tenant/secret violations, call count,

latency and cost per useful output. No model judge overrides hard controls.



## Evaluation Results



Evidence and exact measured metrics are recorded in the phase manifest and

[offline evaluation artifacts](phase-6b-evidence/README.md). Technical pass means the predeclared fixture outcomes matched,

including expected rejections. It does not mean all outputs were schema-valid or

that a real model met quality targets. Samples are small; p95 and confidence

intervals are unavailable where not justified. Founder edit rate and business

quality remain FOUNDER_LABELLED_DATASET_REQUIRED.



## Founder UI



`/system/ai` shows provider status, budgets, frozen routes/evaluations, scenario

submission and run states. Details show context freshness/hash, references,

unknowns, defects, calls, usage, cost, latency and trace. The approvals page shows

the exact route/evaluation/rollback scope and a dedicated promotion command.

There is no model picker. Existing authenticated BFF/CSRF/idempotency boundaries

protect mutations. Ordinary synthetic login cannot fabricate MFA.



## System Health



AI health distinguishes enabled fakes from unconfigured real providers, counts

waiting/refused/incomplete/quarantined work, exposes budget holds and flags missing

evaluation/preflight. No real-provider health is inferred from mock success.



## Security



Original security gates remain enforced. Dependency boundaries permit concrete

SDK imports only in the AI SDK module; application commands cannot import concrete

providers. The browser receives no database credentials. Company administration

does not confer founder promotion authority. Source text has no authority.



## RLS



All eleven new tables enforce FORCE RLS using the existing transaction-local

workspace/principal/epoch model. Cross-table references include workspace ID.

API/worker are non-owner, NOSUPERUSER and NOBYPASSRLS. Immutable configuration,

context, results and evaluations are append-only. The worker receives no new

workspace-table grant; a narrowly scoped authorization predicate checks current

active workspace state. Populated cross-tenant reads and forbidden writes are

tested using actual runtime database roles.



## Tests



Baseline implementation evidence recorded in the manifest: 407 Python tests passed,
zero skipped; 78 focused AI checks passed; 8 Chrome tests passed; production build,
npm audit, Python dependency audit and migration round trips passed. Ubuntu CI was
not run because publication is not authorized. The correction cycle's final stable-source
results supersede these counts in phase-6b-correction-handoff.md and the regenerated manifest.

No failing security assertion is skipped or weakened. Live-provider and Linux

execution results must not be inferred from local Windows evidence.



## Performance



Contained fake-call latency is recorded in the evaluation artifacts, including

process startup and cleanup. Observed per-route p50 values across the exported

splits were 359–391 ms on this Windows machine. Hard timeout and mid-call revocation are exercised.

Existing Phase 6A lifecycle/safety-capacity tests remain in the full gate. These

small local runs are not production throughput or live-provider latency claims.



## Migrations



One linear Alembic history advances 0020 to 0026. 0021 adds AI records and usage

attribution; 0022 adds exact human route authority; 0023 adds narrow workspace and

call-binding guards; 0024 corrects the reservation column and shared-trigger

record access; 0025 requires recent evaluation of the still-current comparison

route. Corrections were added as new revisions after earlier revisions

had been applied in test databases. The review correction adds 0026 for locked
evaluation freshness; revisions 0001–0025 remain unchanged in this correction cycle.

Hashes are in the existing migration manifest and phase manifest. Startup checks

the expected head and never creates tables.



## Changed Files



The phase manifest contains the complete changed-path list and source hashes.

Main additions are the AI contracts/adapters/validation/evaluation modules, shared

application commands, contained provider runner, scoped persistence/migrations,

API/console inspector, security/regression tests and the review evidence.



## Known Limitations



- No live provider, account or paid-call evidence. Gate B remains required.

- No business dataset or quality certification; synthetic technical routes only.

- No arbitrary tools, general KB retrieval, real-data ingestion or agent workflow.

- Core credentials are synthetic-only; live secret resolution/dispatch requires

  further reviewed enablement after separate founder authorization.

- Windows evidence is local. Protected Ubuntu CI must run before closure; no push

  was authorized to trigger it.

- Uncertain calls deliberately retain exposure. There is no fabricated usage

  reconciliation or automatic credit release when provider billing is unknown.

- Budget/calendar configuration and SDK/model/price preflight expire and require

  explicit reviewed provisioning; no automatic live fallback exists.



## Rollback



Before migration, preserve a matched local source/database baseline. Empty-schema

upgrade/downgrade round trips run in disposable databases. Once AI tasks,

evaluations or consumed route authority exist, downgrade refuses to discard that

history. Preserve/export audit records and restore a matched 0020 baseline backup

for rollback; do not run destructive downgrade against populated review data.



## Live Provider Authorization Status



No separate founder provider list and dollar cap were supplied. Authorized live

spend is zero. No real API call, provider enablement or production activation was

performed. Review the core source before requesting Gate B authorization.



## Phase Boundary



AI-001–005, the technical portions of AI-024/025, API-057, DATA-048 AI subset,

DATA-054 and TEST-008/010/011/017/022 are mapped in the phase manifest. This phase

adds only the closed gateway contract and synthetic technical evaluations.



## Phase 7 Readiness



Phase 7 has NOT begun. No Phase 7 feature, autonomous workflow, external send or

production deployment is authorized. Stop at independent review.





## Local Core Demo



Run `npm run dev`, sign in as Synthetic User A, then open `/system/ai`.

Create success, refusal, repair, incomplete, forged-evidence, injection, budget and

timeout scenarios. Follow the durable task/job link. A repair shows two calls;

unknown usage retains its reservation. Revoke a current synthetic context to see

both context and derived output withheld. User B cannot read User A's task URL.



Run the seed/development/holdout/adversarial comparisons from the frozen dataset

selector. Refresh until their evaluation appears. Request exact route review and

inspect the scope in Approvals. Activation requires an actual fresh-MFA founder

session; ordinary synthetic sign-in cannot grant it. The offline test MFA fixture

is confined to the test launcher and does not change normal authentication.



For reproducible browser acceptance, stop ordinary services, build, then run

`PLAYWRIGHT_CHANNEL=chrome node scripts/phase6a-e2e.mjs` (PowerShell: set the

environment variable first). The runner creates and removes its own random

synthetic database. `npm run check` likewise uses a disposable database.



The original full review archive is preserved. This correction produces only
`company-os-phase-6b-correction-delta.zip`, with repository-relative changed files
and archive-only CORRECTION_FILE_LIST.txt. Review tooling and the old tree inventory
are retained under ignored .local; they are excluded from future commit inventory.
See phase-6b-correction-handoff.md for correction results and the archive SHA-256.
