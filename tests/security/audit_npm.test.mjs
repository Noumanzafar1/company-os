import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { evaluate, inspectRuntime, checkRuntime } from '../../scripts/audit_npm.mjs';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/npm-exc-003.json', import.meta.url), 'utf8'));
const now = () => new Date('2026-10-05T12:00:00Z');
const clean = JSON.stringify({ auditReportVersion: 2, vulnerabilities: {}, metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 } } });
function changeAudit(e, edit) { const a = JSON.parse(e.fullAudit); edit(a); e.fullAudit = JSON.stringify(a); }
function denied(name, edit, message) {
  test(name, () => { const e = structuredClone(fixture); edit(e); assert.throws(() => evaluate(e, now()), message); });
}

test('zero vulnerabilities passes without using exception, even after expiry', () => {
  assert.deepEqual(evaluate({ fullAudit: clean, productionAudit: clean }, new Date('2027-01-01')), { status: 'PASS', exception: null, vulnerabilities: 0 });
});
test('exact five propagated entries pass with EXC-003 before expiry', () => {
  const report = evaluate(fixture, now());
  assert.equal(report.status, 'PASS_WITH_EXCEPTION');
  assert.equal(report.exception, 'EXC-003');
  assert.equal(report.vulnerabilities, 5);
});
for (const timestamp of ['2026-11-05T00:00:00Z', '2026-11-06T00:00:00Z', '2026-10-04T23:59:59Z', 'invalid']) {
  test(`rejects expiry/clock boundary ${timestamp}`, () => assert.throws(() => evaluate(fixture, new Date(timestamp)), /expired|clock/));
}
test('last millisecond before expiration is allowed', () => assert.equal(evaluate(fixture, new Date('2026-11-04T23:59:59.999Z')).status, 'PASS_WITH_EXCEPTION'));
denied('different GHSA rejected', e => changeAudit(e, a => a.vulnerabilities.braces.via[0].url = 'https://github.com/advisories/GHSA-other'), /Unauthorized/);
denied('different CVE rejected', e => e.upstream.advisory.cve_id = 'CVE-2026-00000', /CVE/);
denied('additional advisory on a chain package rejected', e => changeAudit(e, a => a.vulnerabilities.micromatch.via.push({ url: 'https://github.com/advisories/GHSA-other' })), /Additional/);
denied('additional unrelated low finding rejected', e => changeAudit(e, a => {
  a.vulnerabilities.other = { name: 'other', severity: 'low', via: ['another'], nodes: ['node_modules/other'] };
  a.metadata.vulnerabilities.low = 1; a.metadata.vulnerabilities.total++;
}), /Unexpected advisory/);
denied('lock production classification rejected', e => e.lock.packages['node_modules/braces'].dev = false, /classification/);
denied('installed production classification rejected', e => e.installed.packages['node_modules/braces'].dev = false, /classification/);
denied('workspace production dependency rejected', e => e.consolePackage.dependencies['eslint-config-next'] = '16.3.8', /Production dependency/);
denied('version drift rejected', e => e.lock.packages['node_modules/braces'].version = '3.0.4', /version/);
denied('incoming path drift rejected', e => e.lock.packages['node_modules/micromatch'].dependencies.braces = '*', /path drift/);
denied('additional incoming parent rejected', e => e.lock.packages['node_modules/other'] = { dependencies: { braces: '^3.0.3' } }, /path drift/);
denied('nested duplicate installed dependency rejected', e => e.installed.packages['node_modules/other/node_modules/braces'] = { version: '3.0.3', dev: true }, /duplicated/);
denied('safe npm fix available rejected', e => changeAudit(e, a => a.vulnerabilities.braces.fixAvailable = { name: 'eslint-config-next', version: '16.3.9', isSemVerMajor: false }), /Remediation/);
denied('unknown boolean npm remediation rejected', e => changeAudit(e, a => a.vulnerabilities.braces.fixAvailable = true), /Remediation/);
denied('upstream first patched version rejected', e => e.upstream.advisory.vulnerabilities[0].first_patched_version = '3.0.4', /Supported patch/);
denied('new stable braces even without latest tag rejected', e => e.upstream.braces.versions['3.0.4'] = {}, /New stable/);
denied('upstream latest tag changed rejected', e => e.upstream.braces['dist-tags'].latest = '3.0.4', /release changed/);
denied('malformed audit JSON rejected', e => e.fullAudit = '{', /JSON/);
denied('missing audit evidence rejected', e => delete e.fullAudit, /Missing audit/);
denied('npm error object is not an audit', e => e.fullAudit = '{"error":{"code":"E503"}}', /Invalid audit/);
denied('mismatched vulnerability totals rejected', e => changeAudit(e, a => a.metadata.vulnerabilities.high = 0), /totals/);
denied('missing upstream evidence rejected', e => delete e.upstream, /CVE/);
denied('missing production audit rejected', e => delete e.productionAudit, /Missing audit/);
denied('production vulnerability rejected', e => e.productionAudit = e.fullAudit, /Production audit/);
denied('custom settings.next.rootDir rejected', e => e.eslintConfig += "export const settings = { next: { rootDir: ['{a,b}/**'] } };", /rootDir/);
denied('computed dynamic configuration rejected', e => e.eslintConfig += "const key = 'root' + 'Dir'; const settings = {[key]:process.env.INPUT};", /rootDir/);
denied('alternate ESLint config rejected', e => e.configFiles.push('eslint.config.js'), /Additional ESLint/);
denied('removing Next lint rules rejected', e => e.eslintConfig = 'export default [];', /rootDir/);
denied('production bundle hit rejected', e => e.runtime.hits.push({ file: 'server/chunk.js', kind: 'javascript-marker' }), /production output/);
denied('missing production build evidence rejected', e => delete e.runtime, /Missing production/);
denied('empty trace evidence rejected', e => e.runtime.traceCount = 0, /Missing production/);
denied('advisory severity drift rejected', e => e.upstream.advisory.severity = 'critical', /severity/);
denied('advisory CVSS v4 scope change rejected', e => e.upstream.advisory.cvss_severities.cvss_v4.score = 9.1, /CVSS/);
denied('advisory description scope change rejected', e => e.upstream.advisory.description += ' Remote code execution.', /scope/);

function buildFixture(action) {
  const root = mkdtempSync(resolve(tmpdir(), 'company-os-exc-003-'));
  const build = resolve(root, 'apps/console/.next');
  mkdirSync(resolve(build, 'server'), { recursive: true });
  mkdirSync(resolve(build, 'static'), { recursive: true });
  writeFileSync(resolve(build, 'BUILD_ID'), 'synthetic');
  writeFileSync(resolve(build, 'required-server-files.json'), '{"version":1,"config":{"distDir":".next"},"files":[".next/BUILD_ID"]}');
  writeFileSync(resolve(build, 'server/main.js'), 'console.log("synthetic");');
  writeFileSync(resolve(build, 'static/main.js'), 'console.log("synthetic");');
  writeFileSync(resolve(build, 'server/main.js.nft.json'), '{"version":1,"files":["../safe.js"]}');
  try { action(root, build); } finally {
    assert.ok(resolve(root).startsWith(resolve(tmpdir(), 'company-os-exc-003-')));
    rmSync(root, { recursive: true, force: true });
  }
}
test('runtime collector inspects real trace and server/browser files', () => buildFixture(root => {
  const report = inspectRuntime(root); checkRuntime(report);
  assert.equal(report.traceCount, 1); assert.equal(report.serverJsCount, 1); assert.equal(report.browserJsCount, 1);
  assert.equal(report.inspected.length, 3);
}));
test('runtime collector detects trace package paths', () => buildFixture((root, build) => {
  writeFileSync(resolve(build, 'server/main.js.nft.json'), '{"version":1,"files":["../../../node_modules/braces/index.js"]}');
  assert.throws(() => checkRuntime(inspectRuntime(root)), /production output/);
}));
test('runtime collector detects browser package markers', () => buildFixture((root, build) => {
  writeFileSync(resolve(build, 'static/main.js'), 'require("micromatch")');
  assert.throws(() => checkRuntime(inspectRuntime(root)), /production output/);
}));
test('runtime collector rejects malformed trace', () => buildFixture((root, build) => {
  writeFileSync(resolve(build, 'server/main.js.nft.json'), '{"version":1}');
  assert.throws(() => inspectRuntime(root), /Malformed runtime/);
}));
test('runtime collector rejects missing required manifest data', () => buildFixture((root, build) => {
  writeFileSync(resolve(build, 'required-server-files.json'), '{}');
  assert.throws(() => inspectRuntime(root), /manifest evidence/);
}));
test('CI preserves security evidence after Playwright clears its output directory', () => {
  const ci = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8');
  const security = ci.indexOf('run: node scripts/audit_npm.mjs');
  assert.ok(security > ci.indexOf('run: npm run build'));
  assert.ok(security > ci.indexOf('run: node scripts/ci-services.mjs e2e'));
  assert.ok(ci.indexOf('uses: actions/upload-artifact@v4') > security);
  assert.match(ci, /path: test-results\//);
});
