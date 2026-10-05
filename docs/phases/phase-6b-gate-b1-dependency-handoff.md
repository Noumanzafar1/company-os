# Phase 6B Gate B1 dependency security correction

Status: Next.js security update implemented; NOT RELEASE-READY.
BRACES UPSTREAM PATCH UNAVAILABLE. Stop for independent review; no security waiver.

## Authority, baseline and preservation

Independent review accepted both B1 source corrections: migration privilege
preservation and credential/capability binding. This task authorizes dependency
security investigation and a same-minor Next.js patch only. Those architectures,
all B1 source, migrations 0001-0027, previous correction evidence and archives are
preserved byte-for-byte. No compatibility source change was needed.

Branch: phase-6b-gate-b-live-provider-preflight.
HEAD/main: 007977c8655b2d7bfca662f77e17befed68d6f12. Work remains unstaged/uncommitted.
Full source/status and archive hashes were recorded before dependency changes.
The unchanged accepted source-correction ZIP has SHA-256
2c758d7817be3471aefc4d162c91138354ea20287db4e72141c2d2afe31671f9.
No old draft database was reused; browser verification uses a newly created
loopback disposable database, and Python fixtures create separate disposable DBs.

## Exact original audit evidence

`npm audit --audit-level=moderate --json` returned exit 1. Sanitized JSON is retained
under ignored .local evidence; the review evidence file contains only relevant
package/advisory/lock data, not environment or account information.
Six affected package entries represent TWO underlying advisories:

| Advisory | Package/version installed before update | Severity | Affected range | Path / scope | npm fixAvailable |
| --- | --- | --- | --- | --- | --- |
| GHSA-vcvr-r3jv-pc5j; no CVE listed by GitHub | next 16.3.5 | critical | >=16.2.0 <16.3.6 | console -> next; production | next 16.3.8, isSemVerMajor=false |
| GHSA-vfj7-8cjw-p6xm / CVE-2026-93687 | braces 3.0.3 | high | <=3.0.3 | console dev -> eslint-config-next -> @next/eslint-plugin-next -> fast-glob -> micromatch -> braces | eslint-config-next 14.2.35, isSemVerMajor=true; rejected downgrade |

The other four high entries are propagated dependency findings for micromatch,
fast-glob, @next/eslint-plugin-next and eslint-config-next, not four additional
advisories. The evidence inventory records each installed version, npm range,
exact dependency edge and fixAvailable object before and after.

Official sources checked at execution:

- https://github.com/advisories/GHSA-vcvr-r3jv-pc5j
- https://github.com/vercel/next.js/releases/tag/v16.3.8
- https://registry.npmjs.org/next/16.3.8
- https://registry.npmjs.org/eslint-config-next/16.3.8
- https://github.com/advisories/GHSA-vfj7-8cjw-p6xm
- https://github.com/micromatch/braces/releases
- https://raw.githubusercontent.com/micromatch/braces/master/package.json
- https://registry.npmjs.org/braces/latest

## Next.js security correction

Official npm's stable 16.3.x version list ends at 16.3.8, and the maintainer release
page identifies it as a security release. The ImageResponse critical advisory is
patched from 16.3.6; 16.3.8 includes that correction and subsequent same-minor fixes.
Both next and eslint-config-next are pinned exactly from 16.3.5 to 16.3.8.
The normal npm install workflow regenerated package-lock.json. No force audit fix,
major/minor jump, override, package removal or unrelated direct dependency change.
The Next critical advisory is absent from the post-update audit (critical count 0).

A source search across apps, packages and tests found no next/og or ImageResponse
usage. This observation did not replace the required upgrade. API/BFF/auth source
and configuration are unchanged; the full browser gate exercises login, cookies,
logout, forged/missing CSRF, open redirects and tenant isolation on the new version.

### Every lockfile change

There are 13 changed package-map entries, no additions/removals: the workspace
metadata, two intended direct packages and ten transitive packages. Each package
below moves from 16.3.5 to 16.3.8; full before/after metadata, URLs and integrity
values are included in the evidence JSON.

- next (direct production)
- eslint-config-next (direct development)
- @next/env
- @next/eslint-plugin-next
- @next/swc-darwin-arm64
- @next/swc-darwin-x64
- @next/swc-linux-arm64-gnu
- @next/swc-linux-arm64-musl
- @next/swc-linux-x64-gnu
- @next/swc-linux-x64-musl
- @next/swc-win32-arm64-msvc
- @next/swc-win32-x64-msvc

The workspace entry changes only the two pins. next updates its aligned env/SWC
references; eslint-config-next updates its aligned plugin reference. Other changed
package fields are version, resolved tarball URL and integrity. All eight platform
SWC entries remain represented, including Ubuntu/Linux. Other lock entries are
identical. Root package.json and all other direct pins remain unchanged.

## Remaining audit and upstream braces status

BRACES UPSTREAM PATCH UNAVAILABLE.

The final chain is:

eslint-config-next 16.3.8 -> @next/eslint-plugin-next 16.3.8 -> fast-glob 3.3.1
-> micromatch 4.0.8 -> braces 3.0.3.

All five exact node_modules package entries have dev=true in package-lock.json.
The root dependency edge is a devDependency; nested prod edges shown by npm explain
are dependencies of that development-only chain, not a production root path.

Current npm braces latest is 3.0.3 and the published version list has no newer
release. The upstream package.json still says 3.0.3; its GitHub releases page has
no release artifacts. The advisory explicitly lists patched versions: None.
Current micromatch 4.0.8 still requires braces ^3.0.3; latest fast-glob 3.3.3 still
requires micromatch ^4.0.8. Updating either would not remove this advisory, and the
Next plugin pins fast-glob 3.3.1. No unsupported update was attempted.

The post-update audit reports five high entries and no critical/moderate/low/info
entries, all from this one braces advisory. Its suggested eslint-config-next
14.2.35 downgrade was not used. No patch was fabricated or vendored; no fork,
override, advisory suppression, audit threshold change or CI omit-dev change exists.

### Runtime bundle and practical tooling exposure

Fresh production output inspection found no audited-chain package in 29 NFT
trace manifests and no package markers in 115 server/browser JavaScript files.
This supports absence from this generated runtime output; it is not a production
deployment inventory or proof against arbitrary bundled code. The package remains
installed in the development dependency tree, so the full audit correctly fails.

Inspection of the installed Next ESLint plugin shows fast-glob is used by
getRootDirs to process settings.next.rootDir patterns. Company OS's unchanged
ESLint configuration supplies no custom rootDir; the helper uses context.cwd.
This vulnerable chain belongs to lint/build tooling rather than an application
request handler. The advisory concerns availability: sufficiently nested hostile
glob patterns can exhaust the tooling process stack. Malicious/unreviewed lint
configuration or future glob inputs could expose developer/CI processes. No
production request-to-pattern flow was found; that does not justify suppressing
the audit or granting a security exception. Independent review must decide whether
to wait for upstream or authorize a separate time-bounded exception with controls.

## Regression

| Check | Final result |
| --- | --- |
| npm.cmd run check | PASS |
| Full Python | 494 passed, 0 skipped, 1 existing warning; 689.63 seconds |
| Focused B1 | 70 passed, 0 skipped, 1 existing warning; 119.07 seconds |
| Console | 2 passed, 0 skipped |
| Contracts / lint / types / boundaries | PASS; mypy 69 source files |
| Production build | PASS on Next 16.3.8, 21 generated pages |
| Chrome Playwright E2E | 8 passed, 0 skipped; 1.1 minutes reported |
| Authentication/BFF | PASS browser regression; source/configuration unchanged |
| Migration privilege equivalence / round trips / populated refusal | PASS |
| Credential substitution / secret canaries / network ban | PASS |
| npm audit --audit-level=moderate | FAIL, exit 1: 5 high, 0 critical; braces chain only |
| Python dependency audit | 57 packages, 0 findings; 2026-10-05T05:33:34.929614+00:00 |
| pip check | PASS, no broken requirements |
| git diff --check / source and archive integrity | PASS |

No different vulnerability or compatibility failure appeared. No compatibility
source changes were made. This is local Windows/Chrome evidence, not a new protected
Ubuntu CI run. The complete cross-platform Next SWC lock entries are preserved.
API/worker services shut down cleanly after E2E.

No safety test was skipped or weakened. One existing Starlette/AnyIO deprecation
warning remains. Canonical npm run check excludes the separately required npm
audit; a check PASS does not make the dependency-security gate green.

## Changed files and review artifact

Only these repository files are included in the dependency delta:

- apps/console/package.json
- package-lock.json
- docs/phases/phase-6b-gate-b1-dependency-handoff.md
- docs/phases/phase-6b-gate-b1-dependency-evidence.json

The ZIP adds DEPENDENCY_CORRECTION_FILE_LIST.txt, containing that exact inventory.
Archive: company-os-phase-6b-gate-b1-dependency-correction-delta.zip.
Its detached .zip.sha256 records the digest. No previous ZIP, .git, real .env,
secret, node_modules, build/cache, local DB or raw environment-bearing audit log
is included. Source-byte/hash/inventory/CRC/secret scans are checked. All prior
review archives and source-correction evidence remain unchanged.

## Live provider status

OpenAI live calls: 0
Anthropic live calls: 0
Authenticated provider administrative requests: 0
Authorized B1 live spend: $0
Observed B1 live spend: $0
Production AI routes: 0

## Gate B2 and phase boundary

B2 NOT AUTHORIZED. Phase 7 has NOT begun. No real credential resolution, provider
request, business data, business outbound, commit, push, PR, merge or deployment.
Stop for independent review with the unpatched dev-only upstream advisory visible.
