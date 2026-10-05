# ADR-026 — EXC-003: temporary development-only braces security exception

Status: founder authorized the exact risk acceptance on 2026-10-05; implementation
and regression evidence returned for independent review before publication.
Owner and review owner: Nouman (founder/repository acceptance reviewer).
Hard expiration: **2026-11-05T00:00:00Z**. No automatic renewal.

The existing registry was inspected before allocation: the canonical product
overview assigns EXC-001 (remote-send boundary) and EXC-002 (early control screens);
the ADR sequence ends at ADR-025. This record allocates EXC-003 and ADR-026 without
changing the Phase 1 design status or either previous exception.

**THIS IS NOT A CLAIM THAT THE PACKAGE IS SAFE.**

This is a bounded risk acceptance because no supported upstream correction
currently exists and current Company OS exposure is limited to development tooling.
It authorizes no provider preflight, production route, business action or Phase 7.

## Advisory and exact accepted scope

- GHSA-vfj7-8cjw-p6xm; CVE-2026-93687; high severity, CWE-674.
- braces 3.0.3, affected range <=3.0.3. CVSS 3.1: 7.5
  (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H`).
- Exact development dependency path:
  `@company-os/console -> eslint-config-next 16.3.8 -> @next/eslint-plugin-next 16.3.8 -> fast-glob 3.3.1 -> micromatch 4.0.8 -> braces 3.0.3`.
- The five high npm entries may be accepted only as propagation of this ONE
  advisory. Any other finding, including a low/info finding, rejects the exception.
- Acceptance date: 2026-10-05. Expiration is exclusive: at the stated UTC instant,
  the exception fails. A clean full audit uses no exception and remains acceptable.

The upstream advisory reports recursive AST walkers without depth guards. Deeply
nested hostile brace patterns can terminate Node through stack exhaustion. The
relevant impact is developer/CI lint process availability, including blocked
engineering delivery. There is no accepted production request-to-pattern path.
Malicious or newly dynamic lint configuration could invalidate that assessment.

Official evidence is fetched on every exception gate invocation, without provider
credentials: [GitHub advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
and [npm braces registry](https://registry.npmjs.org/braces). At acceptance, GitHub
lists no first patched version and npm has no newer stable release than 3.0.3.
The current npm fix suggestion is eslint-config-next 14.2.35, a prohibited downgrade
from the accepted 16.3.8 security update. No fork, vendored patch, overrides,
severity threshold reduction or removal of Next lint rules is authorized.

## Evidence and compensating controls

`node scripts/audit_npm.mjs` executes full
`npm audit --audit-level=moderate --json`, prints all findings and saves structured
evidence under `test-results/npm-security`. Exit 1 is accepted only when its parsed
report and every other exception condition validate. Audit process failures,
malformed/error JSON, unknown exit codes or inconsistent counts fail the gate.
Full audit is never replaced by the production-only scan.

It separately executes `npm audit --omit=dev --audit-level=moderate`, then obtains
its JSON counts. Any moderate/high/critical production finding fails. The full
audit still rejects all additional findings at any severity.

The checker verifies the lockfile, npm installed-tree metadata and actual installed
package manifests. Every accepted package must have its sole exact node_modules
location, version and `dev: true`. All incoming dependency edges must equal the
reviewed chain, including workspace devDependency and dependency range strings.
Duplicate/nested nodes, alternative parents, changed package versions or production
classification fail. `npm ci` remains the CI installation method.

The console's ESLint configuration is pinned as exact source (normalizing only
CRLF). It retains Core Web Vitals and TypeScript presets, has no custom settings,
and therefore supplies no `settings.next.rootDir`. Exact-source comparison rejects
dynamic/computed settings, alias imports and brace-expression configuration rather
than trying to execute or infer the safety of arbitrary JavaScript. Additional
repository ESLint config files and package `eslintConfig` entries fail. Any config
change needs review/removal of this exception. Dependency and generated directories
are excluded from this bounded repository-config inventory.

The installed Next plugin's get-root-dirs helper uses fast-glob only for configured
`settings.next.rootDir`; absent that setting, it defaults to the lint context cwd.
The accepted configuration retains all existing Next lint coverage.

After the existing production build, the checker requires BUILD_ID, parses the
required-server-files manifest and every discovered NFT trace, and scans server
and browser JavaScript for all five chain package markers. Missing/empty evidence,
malformed traces or a chain hit fail. Evidence records file counts, relative paths
and SHA-256 hashes. This is a bounded inspection of Next's generated NFT traces
and server/static JavaScript from the accepted build method. It is not mathematical
proof against all transformed/minified code or all possible deployment forms.

CI replaces only its dependency-security step with this gate, placing it after
the unchanged production build and browser gate to inspect fresh output and avoid
Playwright clearing audit evidence from test-results. Existing install, backend,
checks, browser and artifact gates remain. Offline checker tests join `npm run check`.
The existing always-uploaded `test-results/` artifact includes audit evidence.
No ignored exit, `|| true`, cached-evidence CLI or automatic renewal exists.

## Immediate invalidation and remediation

The exception fails immediately when observed evidence shows any of:

- Expiration, invalid clock or unavailable/malformed required evidence.
- A supported patched braces release or changed upstream patch/release evidence.
  Any newer stable release or changed latest tag fails conservatively for review;
  the checker does not assume that an unreviewed release is safe.
- A changed npm fix suggestion, including a supported update. Apply and verify a
  supported correction; do not silently accept or automatically install it.
- Different GHSA/CVE, any additional advisory, or changed severity, CVSS, weakness,
  description, affected range/functions or propagation graph.
- Exact path/version/dev-classification drift, production findings or bundle hits.
- ESLint configuration drift, including untrusted/dynamic rootDir or brace globs.

Checks run on invocation; this is not a background monitor between CI runs.
Public registry/GitHub outages or rate limits fail closed rather than accepting
stale evidence. Raw audit remains visible. No provider/account API is contacted.
Strict metadata/config checks may block harmless changes; that is an intentional
review trigger rather than an expanded risk acceptance.

Remediation owner Nouman must arrange a supported update and rerun full regression
when available. Remove the exception once the full audit is clean. Any extension
past expiry requires explicit founder renewal after another independent review.
Rollback is removal of this gate/exception in favor of the original failing full
audit step; it does not justify downgrading dependencies or editing migrations.

Requirement mapping: SEC-009/010, TEST-001/017/019 and the explicit Phase 6B Gate B1
security-exception brief. This changes only development dependency-security policy,
not runtime authority, data ownership, provider contracts or migrations.
