# Phase 6B Gate B1 security exception handoff

Status: PASS WITH EXC-003. Return for independent review; no publication.

## Authority and integrity

The founder accepted the prior dependency correction and authorized exactly one
time-bounded development-dependency risk acceptance. EXC-003 is recorded in
ADR-026 after checking the existing EXC-001/002 and ADR-001–025 registries.
Acceptance date 2026-10-05; owner and review owner Nouman; hard expiry
2026-11-05T00:00:00Z. No automatic renewal.

Branch: phase-6b-gate-b-live-provider-preflight.
HEAD, local main, origin/main and read-only remote main check:
007977c8655b2d7bfca662f77e17befed68d6f12.
All work remains unstaged and uncommitted. Accepted B1 application source,
migrations 0001–0027, dependency manifests/lock and prior review archives remain
byte-for-byte unchanged from the task baseline. Build-generated next-env.d.ts was
restored to its verified baseline bytes. No commit, push, PR, merge or deployment.

The earlier dependency handoff/evidence is retained as historical supporting
material. Its raw-audit blocker is now addressed by this separately authorized
policy; its five high findings are not claimed to be fixed.

## Advisory and scope

GHSA-vfj7-8cjw-p6xm / CVE-2026-93687: braces 3.0.3 stack-exhaustion denial of service,
high, CWE-674. **THIS IS NOT A CLAIM THAT THE PACKAGE IS SAFE.**

Exact path:
`@company-os/console -> eslint-config-next 16.3.8 -> @next/eslint-plugin-next 16.3.8 -> fast-glob 3.3.1 -> micromatch 4.0.8 -> braces 3.0.3`.

All five installed entries are development-only in both lock and installed-tree
evidence; actual package manifests match the locked dependency edges. The collector
enumerates all incoming edges and rejects extra parents/nested duplicates.
Full npm audit reports five high entries, all exclusively propagated from this
single advisory. No critical, moderate, low or informational entries remain.

Fresh public GitHub/npm evidence at 2026-10-05T13:19:16.406Z confirms no supported
patched braces release, latest 3.0.3 and first_patched_version null. npm's offered
eslint-config-next 14.2.35 downgrade remains prohibited. Official evidence URLs:

- https://github.com/advisories/GHSA-vfj7-8cjw-p6xm
- https://api.github.com/advisories/GHSA-vfj7-8cjw-p6xm
- https://registry.npmjs.org/braces

## Policy and compensating controls

The full audit runs at the unchanged moderate threshold, prints the complete
structured findings, and saves sanitized JSON. Its raw exit is still 1. The
separate Company OS checker exits 0 only for a clean full audit or exact valid
EXC-003 evidence. Unknown/error/malformed/missing inputs fail. No ignored exit
code, `|| true`, package override, fork, vendor patch, downgrade or lint removal.

The production-only text and structured audits both report zero vulnerabilities.
They supplement the full audit. The gate verifies all GHSA/CVE, severity/scope,
version, path, dev-classification, expiry and remediation conditions.

Fresh upstream evidence is fetched on each real invocation; unit fixtures are
offline and cannot be selected by the CLI. New patch/release/fix evidence, another
advisory, severity/scope drift, invalid clock, expiry, production classification
or output hits invalidate the exception. Registry/GitHub failure or rate limits
fail closed. This is a check at invocation, not a background monitoring service.

The accepted ESLint config is exact-source pinned (CRLF normalized), preserving
Next Core Web Vitals and TypeScript coverage and absence of settings.next.rootDir.
Additional configs and package eslintConfig fields fail. Any dynamic/computed or
brace-pattern configuration requires review/removal of the exception.

Fresh Next 16.3.8 webpack production output passed: 29 NFT traces, 70 server JS
files and 45 browser JS files, zero chain markers. Required production manifest
and its files are verified. The evidence records 144 inspected file hashes. This
is bounded trace/marker evidence for this build method, not proof against every
possible transformation or deployment. The actual production build is retained
only locally; its output is excluded from the review ZIP.

Only the existing CI dependency-security step is replaced and moved after the
unchanged build and browser gates. Playwright clears test-results at startup;
placing the scan after it preserves audit evidence in the existing always-uploaded
artifact. All other gates remain, and the new policy tests join npm run check.
No protected Ubuntu run was triggered; this task provides local Windows/Chrome
evidence and proposed CI source for independent review.

## Regression

| Check | Result |
| --- | --- |
| npm.cmd run check | PASS |
| Full Python | 494 passed, 0 skipped; 1 existing warning; 673.82s |
| Focused B1 | 70 passed, 0 skipped; 1 existing warning; 116.22s |
| Final offline exception tests | 46 passed, 0 failed, 0 skipped |
| Console tests | 2 passed, 0 skipped |
| Contracts / Ruff / mypy / ESLint / TypeScript / boundaries | PASS |
| Production build | PASS; Next 16.3.8 webpack; 21 generated pages |
| Chrome E2E | 8 passed, 0 skipped |
| Migrations / privilege equivalence / downgrade protections | PASS |
| Credential substitution / secret canaries / network ban | PASS |
| Full npm audit | Raw exit 1; five high propagated entries; all other counts zero |
| EXC-003 policy | PASS_WITH_EXCEPTION; exit 0 |
| Production-only npm audit | PASS; zero vulnerabilities |
| Python dependency audit | 57 packages, zero findings |
| pip check / git diff --check | PASS |

The canonical run passed the initial 43 policy cases. Three additional hardening
cases were added while its unchanged Python suite was running; the final complete
46-case suite was rerun with the exact CI Node command and passed. No Python,
application, dependency, migration, build or browser source changed during this run.

The initial restricted Node child-process attempt was blocked by local sandbox
permissions, before npm or test execution. Authorized local tool execution passed.
No test or security policy was weakened. One existing Starlette/AnyIO deprecation
warning remains in the Python suites. Console/browser color-environment warnings
do not represent test failures.

The offline policy matrix covers clean/exact acceptance; hard expiry and clock
boundaries; GHSA/CVE mismatch; additional/changed advisory propagation; production
classification; exact path/version drift; duplicate nodes; supported fix/patch
availability; malformed/missing audit and upstream evidence; production findings;
static/dynamic/custom ESLint settings; lost lint coverage; runtime hits/missing or
malformed output; severity/CVSS/scope drift; and CI artifact ordering.

Full/focused Python tests run with the existing external-network ban, synthetic
credentials and disposable loopback databases. They include migration privilege
equivalence, empty-schema/head and no-history round trips, populated downgrade
refusal, credential substitution before dispatch/child, secret canaries and real
network denial. No safety tests are skipped. The browser run uses a new disposable
database; its API/worker services shut down after success.

## Changed paths and artifact

This task changes/adds exactly eight repository files:

- .github/workflows/ci.yml
- scripts/check.mjs
- scripts/audit_npm.mjs
- tests/security/audit_npm.test.mjs
- tests/security/fixtures/npm-exc-003.json
- docs/adr/026-dev-dependency-security-exception.md
- docs/phases/phase-6b-gate-b1-security-exception-handoff.md
- docs/phases/phase-6b-gate-b1-security-exception-evidence.json

The review ZIP additionally includes unchanged supporting apps/console/package.json,
package-lock.json, the prior dependency handoff/evidence and a ZIP-only exact
inventory: SECURITY_EXCEPTION_FILE_LIST.txt. Total: 13 entries.
Archive: company-os-phase-6b-gate-b1-security-exception-review.zip.
Its detached .zip.sha256 records its digest. It supplements the independently
reviewed B1/source-correction/dependency artifacts; no prior ZIP is embedded.
Source/hash/CRC/inventory/secret checks are required before packaging completes.

The package excludes secrets, real .env, node_modules, builds, caches, local DBs,
raw environment data and previous archives. Sanitized policy evidence retains all
audit findings, upstream scope, exact dev-chain evidence and bounded build hashes.

Rollback: restore the original failing full npm audit security step and remove
this exception tooling after review. No dependency downgrade or migration change.
Requirement mapping: SEC-009/010, TEST-001/017/019 and the explicit Gate B1
security-exception brief. Residual risks and invalidation rules are in ADR-026.

## Live provider status and boundaries

OpenAI live calls: 0
Anthropic live calls: 0
Authenticated provider administrative requests: 0
Authorized B1 live spend: $0
Observed B1 live spend: $0
Production AI routes: 0

No real provider credential resolution occurred. Normal AI execution remains
fake-only; the closed live-preflight implementation has not been exercised live.
B2 NOT AUTHORIZED. Phase 7 has NOT begun. Stop for independent review.
