// EXC-003 / ADR-026. Deliberately closed policy; drift requires independent review.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, readdirSync, mkdirSync, statSync } from 'node:fs';
import { resolve, relative, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isDeepStrictEqual } from 'node:util';

export const GHSA = 'GHSA-vfj7-8cjw-p6xm';
export const CVE = 'CVE-2026-93687';
export const EXPIRY = '2026-11-05T00:00:00Z';
export const CHAIN = [
  ['eslint-config-next', '16.3.8'], ['@next/eslint-plugin-next', '16.3.8'],
  ['fast-glob', '3.3.1'], ['micromatch', '4.0.8'], ['braces', '3.0.3'],
];
export const ESLINT_CONFIG = `import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';
export default defineConfig([...nextVitals,...nextTs,globalIgnores(['.next/**','next-env.d.ts'])]);
`;
const TITLE = 'braces vulnerable to stack-exhaustion denial of service through deeply nested patterns';
const DESCRIPTION = 'braces through 3.0.3 contains a stack overflow vulnerability in the recursive AST walkers that lack depth guards. Attackers can supply deeply nested brace patterns under the character limit to exhaust the call stack and terminate the Node.js process with an uncaught RangeError.';
const VECTOR = 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H';
const names = CHAIN.map(([name]) => name);
const counts = total => ({ info: 0, low: 0, moderate: 0, high: total, critical: 0, total });
const requirePolicy = (condition, message) => { if (!condition) throw new Error(message); };
const same = (actual, expected, message) => requirePolicy(isDeepStrictEqual(actual, expected), message);
const json = path => JSON.parse(readFileSync(path, 'utf8'));
const sha256 = data => createHash('sha256').update(data).digest('hex');

export function parseAudit(text) {
  requirePolicy(typeof text === 'string' && text.length > 0, 'Missing audit evidence');
  const audit = JSON.parse(text);
  requirePolicy(audit?.auditReportVersion === 2 && !audit.error, 'Invalid audit report');
  requirePolicy(audit.vulnerabilities && typeof audit.vulnerabilities === 'object' && !Array.isArray(audit.vulnerabilities), 'Missing vulnerability map');
  const entries = Object.entries(audit.vulnerabilities);
  const actual = { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: entries.length };
  for (const [name, entry] of entries) {
    requirePolicy(entry?.name === name && Object.hasOwn(actual, entry.severity) && entry.severity !== 'total', 'Malformed vulnerability entry');
    requirePolicy(Array.isArray(entry.via) && entry.via.length > 0 && Array.isArray(entry.nodes) && entry.nodes.length > 0, 'Missing vulnerability evidence');
    actual[entry.severity]++;
  }
  same(audit.metadata?.vulnerabilities, actual, 'Audit totals do not match all enumerated findings');
  return audit;
}

export function checkChain(lock, installed, consolePackage) {
  requirePolicy(lock?.lockfileVersion === 3 && lock.packages, 'Missing lock evidence');
  requirePolicy(installed?.packages, 'Missing installed tree evidence');
  requirePolicy(consolePackage?.name === '@company-os/console', 'Workspace identity drift');
  same(consolePackage.devDependencies?.['eslint-config-next'], '16.3.8', 'Workspace dependency drift');
  requirePolicy(!consolePackage.dependencies?.['eslint-config-next'], 'Production dependency introduced');
  const edges = [
    ['apps/console', 'devDependencies', 'eslint-config-next', '16.3.8'],
    ['node_modules/eslint-config-next', 'dependencies', '@next/eslint-plugin-next', '16.3.8'],
    ['node_modules/@next/eslint-plugin-next', 'dependencies', 'fast-glob', '3.3.1'],
    ['node_modules/fast-glob', 'dependencies', 'micromatch', '^4.0.4'],
    ['node_modules/micromatch', 'dependencies', 'braces', '^3.0.3'],
  ];
  for (const [label, packages] of [['lock', lock.packages], ['installed', installed.packages]]) {
    for (const [name, version] of CHAIN) {
      const paths = Object.keys(packages).filter(p => p.endsWith(`node_modules/${name}`));
      same(paths, [`node_modules/${name}`], `${label}: duplicated/missing dependency path: ${name}`);
      const entry = packages[paths[0]];
      requirePolicy(entry.version === version && entry.dev === true && !entry.link, `${label}: version/dev classification drift: ${name}`);
    }
    const incoming = [];
    for (const [path, entry] of Object.entries(packages)) {
      for (const kind of ['dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies']) {
        for (const name of names) if (Object.hasOwn(entry[kind] ?? {}, name)) incoming.push([path, kind, name, entry[kind][name]]);
      }
    }
    // npm's hidden installed lock omits workspace metadata; collector adds actual manifest.
    same(incoming.sort(), [...edges].sort(), `${label}: dependency path drift`);
  }
}

export function checkStatic(config, configFiles) {
  // Exact source is intentional: rejects computed keys, spreads, aliases, imports of
  // local config, environment-derived globs and inline settings without executing it.
  same(config.replaceAll('\r\n', '\n'), ESLINT_CONFIG, 'ESLint configuration changed; rootDir/glob exception requires review');
  same(configFiles, ['apps/console/eslint.config.mjs'], 'Additional ESLint configuration requires review');
}

export function checkRuntime(runtime) {
  requirePolicy(runtime?.buildId && runtime.traceCount > 0 && runtime.serverJsCount > 0 && runtime.browserJsCount > 0, 'Missing production build evidence');
  same(runtime.hits, [], 'Vulnerable chain found in production output');
}

export function checkUpstream(upstream) {
  const advisory = upstream?.advisory;
  requirePolicy(advisory?.ghsa_id === GHSA && advisory.cve_id === CVE, 'GHSA/CVE mismatch');
  requirePolicy(advisory.type === 'reviewed' && advisory.withdrawn_at === null && advisory.severity === 'high', 'Advisory state/severity drift');
  same(advisory.summary, TITLE, 'Advisory scope changed');
  same(advisory.description, DESCRIPTION, 'Advisory scope changed');
  same(advisory.cvss, { vector_string: VECTOR, score: 7.5 }, 'Advisory CVSS changed');
  same(advisory.cvss_severities, { cvss_v3: { vector_string: VECTOR, score: 7.5 }, cvss_v4: { vector_string: 'CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:H/SC:N/SI:N/SA:N', score: 8.7 } }, 'Advisory CVSS scope changed');
  same(advisory.cwes, [{ cwe_id: 'CWE-674', name: 'Uncontrolled Recursion' }], 'Advisory weakness changed');
  same(advisory.vulnerabilities, [{ package: { ecosystem: 'npm', name: 'braces' }, vulnerable_version_range: '<= 3.0.3', first_patched_version: null, vulnerable_functions: [] }], 'Supported patch available or advisory scope changed; remediate/review');
  requirePolicy(upstream.braces?.name === 'braces' && upstream.braces['dist-tags']?.latest === '3.0.3', 'Upstream braces release changed; remediate/review');
  const versions = Object.keys(upstream.braces.versions ?? {});
  requirePolicy(versions.includes('3.0.3') && versions.every(v => /^\d+\.\d+\.\d+(?:-.+)?$/.test(v)), 'Missing/invalid upstream release evidence');
  for (const v of versions.filter(v => !v.includes('-'))) {
    const [major, minor, patch] = v.split('.').map(Number);
    requirePolicy(major < 3 || (major === 3 && minor === 0 && patch <= 3), 'New stable braces release; remediate/review');
  }
}

export function evaluate(evidence, now = new Date()) {
  const audit = parseAudit(evidence.fullAudit);
  const prod = parseAudit(evidence.productionAudit);
  const pc = prod.metadata.vulnerabilities;
  requirePolicy(pc.moderate === 0 && pc.high === 0 && pc.critical === 0, 'Production audit failed');
  const total = audit.metadata.vulnerabilities.total;
  if (total === 0) return { status: 'PASS', exception: null, vulnerabilities: 0 };
  requirePolicy(Number.isFinite(now.getTime()) && now >= new Date('2026-10-05T00:00:00Z') && now < new Date(EXPIRY), 'EXC-003 expired or invalid clock');
  same(Object.keys(audit.vulnerabilities).sort(), [...names].sort(), 'Unexpected advisory/package entries');
  same(audit.metadata.vulnerabilities, counts(5), 'Unexpected severity/count');
  for (let i = 0; i < CHAIN.length; i++) {
    const name = names[i];
    const entry = audit.vulnerabilities[name];
    same(entry.nodes, [`node_modules/${name}`], 'Audit dependency path drift');
    same(entry.effects, i === 0 ? [] : [names[i - 1]], 'Unexpected propagated advisory effect');
    same(entry.isDirect, i === 0, 'Direct dependency classification drift');
    same(entry.range, ['>=14.3.0-canary.0', '>=14.3.0-canary.0', '*', '>=0.2.0', '*'][i], 'Audit vulnerability scope drift');
    if (i < 4) same(entry.via, [names[i + 1]], 'Additional/changed advisory in propagation chain');
    else same(entry.via, [{ source: 1240992, name: 'braces', dependency: 'braces', title: TITLE, url: `https://github.com/advisories/${GHSA}`, severity: 'high', cwe: ['CWE-674'], cvss: { score: 7.5, vectorString: VECTOR }, range: '<=3.0.3' }], 'Unauthorized advisory or changed scope');
    // The only accepted offered fix is the known prohibited downgrade. Any new
    // suggestion (including true, unknown or a supported update) requires review.
    same(entry.fixAvailable, { name: 'eslint-config-next', version: '14.2.35', isSemVerMajor: true }, 'Remediation changed; supported fix must be applied/reviewed');
  }
  checkChain(evidence.lock, evidence.installed, evidence.consolePackage);
  checkStatic(evidence.eslintConfig, evidence.configFiles);
  checkRuntime(evidence.runtime);
  checkUpstream(evidence.upstream);
  return { status: 'PASS_WITH_EXCEPTION', exception: 'EXC-003', advisory: GHSA, cve: CVE, vulnerabilities: 5, expires: EXPIRY };
}

function walk(directory) {
  return readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name)).flatMap(entry => {
    if (['node_modules', '.git', '.next', '.local', '.venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'].includes(entry.name)) return [];
    const path = resolve(directory, entry.name);
    requirePolicy(!entry.isSymbolicLink(), 'Unexpected symlink in inspected source/build');
    return entry.isDirectory() ? walk(path) : [path];
  });
}

export function inspectRuntime(root) {
  const build = resolve(root, 'apps/console/.next');
  const buildId = readFileSync(resolve(build, 'BUILD_ID'), 'utf8').trim();
  const manifest = json(resolve(build, 'required-server-files.json'));
  requirePolicy(manifest?.version === 1 && manifest.config?.distDir === '.next' && Array.isArray(manifest.files) && manifest.files.length > 0, 'Missing required production manifest evidence');
  for (const file of manifest.files) {
    requirePolicy(typeof file === 'string' && file.replaceAll('\\', '/').startsWith('.next/'), 'Invalid required build file');
    const path = resolve(root, 'apps/console', file);
    requirePolicy(path.startsWith(build + (process.platform === 'win32' ? '\\' : '/')) && statSync(path).isFile(), 'Missing required build file');
  }
  const all = walk(build);
  const traces = all.filter(p => p.endsWith('.nft.json'));
  const serverJs = walk(resolve(build, 'server')).filter(p => p.endsWith('.js'));
  const browserJs = walk(resolve(build, 'static')).filter(p => p.endsWith('.js'));
  const hits = [];
  const inspected = [];
  const marker = /\b(?:braces|micromatch|fast-glob|eslint-config-next)\b|@next[\\/]eslint-plugin-next/;
  for (const path of [...traces, ...serverJs, ...browserJs].sort()) {
    const content = readFileSync(path, 'utf8');
    inspected.push({ path: relative(build, path).replaceAll('\\', '/'), sha256: sha256(content) });
    if (path.endsWith('.nft.json')) {
      const trace = JSON.parse(content);
      requirePolicy(trace.version === 1 && Array.isArray(trace.files) && trace.files.every(p => typeof p === 'string'), 'Malformed runtime trace');
      for (const file of trace.files) if (marker.test(file)) hits.push({ file: relative(build, path).replaceAll('\\', '/'), kind: 'trace' });
    } else if (marker.test(content)) hits.push({ file: relative(build, path).replaceAll('\\', '/'), kind: 'javascript-marker' });
  }
  return { buildId, traceCount: traces.length, serverJsCount: serverJs.length, browserJsCount: browserJs.length, hits, inspected };
}

function installedTree(root, lock, consolePackage) {
  const installed = json(resolve(root, 'node_modules/.package-lock.json'));
  installed.packages['apps/console'] = consolePackage;
  for (const [name] of CHAIN) {
    const path = `node_modules/${name}`;
    const actual = json(resolve(root, path, 'package.json'));
    const entry = installed.packages[path];
    requirePolicy(actual.name === name && actual.version === entry?.version, 'Installed package identity drift');
    same(actual.dependencies, lock.packages[path]?.dependencies, 'Installed dependency metadata drift');
    installed.packages[path] = { ...entry, dependencies: actual.dependencies };
  }
  return installed;
}

function auditCommand(args, output) {
  // Only fixed argument arrays below; no shell/user input interpolation.
  const windows = process.platform === 'win32';
  const command = windows ? process.execPath : 'npm';
  const argv = windows ? [resolve(dirname(process.execPath), 'node_modules/npm/bin/npm-cli.js'), ...args] : args;
  console.log(`$ npm ${args.join(' ')}`);
  const result = spawnSync(command, argv, { encoding: 'utf8', windowsHide: true, timeout: 120000, maxBuffer: 16 * 1024 * 1024 });
  requirePolicy(!result.error && result.signal === null && [0, 1].includes(result.status), 'npm audit failed to complete');
  if (args.includes('--json')) {
    const audit = parseAudit(result.stdout);
    // Preserve every advisory and all counts; omit any ambient npm diagnostics.
    const safe = { auditReportVersion: audit.auditReportVersion, vulnerabilities: audit.vulnerabilities, metadata: audit.metadata };
    writeFileSync(output, JSON.stringify(safe, null, 2) + '\n');
    console.log(JSON.stringify(safe, null, 2));
    const c = safe.metadata.vulnerabilities;
    requirePolicy(result.status === (c.moderate + c.high + c.critical > 0 ? 1 : 0), 'Unexpected npm audit exit code');
    return JSON.stringify(safe);
  }
  console.log(result.stdout.trim());
  requirePolicy(result.status === 0, 'Production npm audit failed');
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: 'application/json' }, redirect: 'error', signal: AbortSignal.timeout(30000) });
  requirePolicy(response.ok, `Public advisory evidence unavailable: HTTP ${response.status}`);
  return response.json();
}

export async function main() {
  requirePolicy(process.argv.length === 2, 'Unsupported audit policy arguments');
  const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
  process.chdir(root);
  const output = resolve(root, 'test-results/npm-security');
  mkdirSync(output, { recursive: true });
  writeFileSync(resolve(output, 'policy-evidence.json'), JSON.stringify({ report: { status: 'FAIL', reason: 'Gate incomplete; no exception applied' } }) + '\n');
  const fullAudit = auditCommand(['audit', '--audit-level=moderate', '--json'], resolve(output, 'full-audit.json'));
  auditCommand(['audit', '--omit=dev', '--audit-level=moderate']);
  const productionAudit = auditCommand(['audit', '--omit=dev', '--audit-level=moderate', '--json'], resolve(output, 'production-audit.json'));
  const evidence = { fullAudit, productionAudit };
  if (parseAudit(fullAudit).metadata.vulnerabilities.total !== 0) {
    evidence.lock = json('package-lock.json');
    evidence.consolePackage = json('apps/console/package.json');
    evidence.installed = installedTree(root, evidence.lock, evidence.consolePackage);
    evidence.eslintConfig = readFileSync('apps/console/eslint.config.mjs', 'utf8');
    evidence.configFiles = walk(root).filter(p => /^(?:eslint\.config\.[cm]?[jt]s|\.eslintrc(?:\..+)?)$/.test(p.split(/[\\/]/).at(-1))).map(p => relative(root, p).replaceAll('\\', '/')).sort();
    for (const path of walk(root).filter(p => p.endsWith('package.json'))) requirePolicy(!Object.hasOwn(json(path), 'eslintConfig'), 'Package ESLint configuration requires review');
    evidence.runtime = inspectRuntime(root);
    const [advisory, registry] = await Promise.all([fetchJson(`https://api.github.com/advisories/${GHSA}`), fetchJson('https://registry.npmjs.org/braces')]);
    const { ghsa_id, cve_id, type, withdrawn_at, severity, summary, description, cvss, cvss_severities, cwes, vulnerabilities } = advisory;
    evidence.upstream = { advisory: { ghsa_id, cve_id, type, withdrawn_at, severity, summary, description, cvss, cvss_severities, cwes, vulnerabilities }, braces: { name: registry.name, 'dist-tags': registry['dist-tags'], versions: Object.fromEntries(Object.keys(registry.versions ?? {}).map(v => [v, {}])) } };
  }
  const report = evaluate(evidence);
  // Evidence can be replayed offline by tests/reviewers; CLI never accepts cached input.
  writeFileSync(resolve(output, 'policy-evidence.json'), JSON.stringify({ checkedAt: new Date().toISOString(), report, evidence }, null, 2) + '\n');
  console.log(JSON.stringify(report));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(`NPM SECURITY POLICY: FAIL: ${error.message}`); process.exitCode = 1; });
}
