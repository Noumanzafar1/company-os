# Part 20 — Authentication, Permissions and Secrets

**SEC-008 Managed authentication.** Use Supabase Auth as initial managed identity provider, subject to MFA/session feature preflight. No public signup; invite-only users. Founder/admin must enroll MFA before privileged actions. Reauthenticate for role grants, secret binding, policy promotion and production release; grant approvals require a recent MFA assertion, default ≤10 minutes. The API verifies identity independently of UI visibility. Membership revocation takes effect on next request/dispatch, without waiting for JWT expiry.

Proposed session policy: access token ≤15 min where supported, rotating refresh session, 12-hour absolute app session, 30-minute idle expiry for privileged console use; exact managed-service configuration must be tested. Store browser session in secure HttpOnly SameSite cookies; CSRF token plus Origin checks on state changes. No bearer tokens in localStorage. Public webhook connection tokens identify a registered connection and are not sufficient authentication by themselves; redact sensitive path tokens as well as query parameters. OAuth callbacks use state and PKCE where supported, fixed allowlisted redirect URIs, least scopes and encrypted refresh tokens outside business rows. Do not log callback codes.

| Role | Read scope | Permitted command scope | Explicit limits |
|---|---|---|---|
| Founder | Assigned workspaces including authorised summaries | Approvals, strategy, budget, release and recorded human decisions | No hidden cross-client export; L4 executions remain human |
| Researcher | Assigned account/evidence/contact records | Research, draft facts, corrections, eligibility checks | No sends, campaign release, secrets, commercial price |
| SDR | Assigned campaigns and required threads | Message drafts, approval requests, protective stops | No authority grant or unapproved substantive replies |
| Salesperson | Assigned CRM projections/meeting context | Discovery records, proposal prep, commercial change requests | Price/terms/signature require founder decision |
| Account manager | Assigned client engagement and reports | Internal tasks, report prep, risk cases | No client prospect reuse or financial execution |
| Delivery lead | Assigned scope, deliverables and evidence | Submit work; acceptance only when explicitly authorised by scope | AI/service cannot inherit human acceptance permission |
| Finance reviewer | Authorised cost/financial source projections | Reconciliation notes and preparation tasks | No payment tool or bank credential |
| System administrator | Health/config/technical metadata | Controlled retries, preflight, deployment preparation | Not automatically business approver or all-client content reader |
| AI task service | Exact context capability | Typed proposal/result submission | No direct SQL, secrets, external sends, role changes |
| Integration service | Bound connection/operation/workspace | Observation ingestion and approved effect execution | No grant or unbounded provider access |
| Scheduler | Schedule/job metadata only | Emit due jobs, inspect heartbeats | No prospect/document content |

**SEC-009 Secrets.** Local `.env` is gitignored, minimal and development-only; `.env.example` contains names/placeholders. Test uses fake credentials. Staging and production have separate keys/projects. Render environment secrets or an approved secret store hold provider keys, DB passwords, token-signing keys and OAuth encryption keys. Business tables store secret references, never values. Render documents environment variables/secrets as a supported mechanism. [Render environment variables and secrets](https://render.com/docs/configure-environment-variables).

Service processes receive only the secrets required for their configured role. Initial modular deployment is not perfect process-level isolation: a compromised worker could expose the keys loaded into that process. Minimise loaded adapters, separate the sequencer dispatcher runtime/credentials if live risk requires it, and record that deployment choice at Phase 10. This is a process boundary within the monolith, not a microservice redesign. No model-facing tool can read the environment or arbitrary local files.

Rotate on exposure, provider event, staff departure or planned policy interval (initial review every 90 days; rotate where supported without unnecessary downtime). Record credential version and last successful check. Dual-key rotation temporarily supports old/new webhook verification where provider supports it. Redact Authorization, API-key headers, query-string keys, OAuth codes, cookies and personal message bodies from logs/traces. Founder master accounts remain in a password manager with independent recovery access; agents never receive the founder's browser session. Emergency admin access is time-limited, reasoned and audited, with revocation after the incident.

**SEC-010 Prompt-injection/egress boundary.** Retrieved web content, email and documents cannot modify permissions, roles, destinations, budgets or instructions. Tools validate IDs and schema independently of text. Public fetch uses strict outbound restrictions, small content limits, timeouts and safe parsers; do not execute downloaded code or macros. AI never gets arbitrary URL POST or email send. Proposals to share or export go through the same approval API. No production data is copied into coding-tool prompts without an approved classification/purpose policy; use fixtures and redacted traces.

