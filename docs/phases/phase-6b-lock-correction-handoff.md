# Phase 6B Ubuntu lock correction

This is the founder-authorized PR #5 publication/reproducibility correction,
following reviewed commit `d44a1804fc37c72cefa230c8f9e68120846acafb` on
`phase-6b-ai-gateway-evaluation`. The request transposed `cefa` in that SHA;
Git and the PR identify the commit above. Phase 7 and live providers remain closed.

## Cause and generation contract

The `dev` extra in `pyproject.toml` includes `pip-tools>=7.4,<8`, locked at
`7.6.1`. Its distribution metadata requires both `pip>=22.2` and `setuptools`.
The previous lock omitted those unsafe-classified requirements and ended with
pip-compile's unpinned/hash-mode warning. The existing Windows venv already had
`pip==26.2.1` and `setuptools==84.0.0`, masking a fresh-environment failure.

The old generated header recorded:

```text
pip-compile --extra=dev --generate-hashes --no-index --output-file=requirements.lock pyproject.toml
```

Using Python 3.12.14 and pip-tools 7.6.1, the correction ran the documented
`docs/local-development.md` generation method with explicit no-upgrade behavior:

```text
python -m piptools compile pyproject.toml --extra dev --all-build-deps --allow-unsafe --generate-hashes --no-upgrade --output-file requirements.lock
```

The generated header adds `--all-build-deps --allow-unsafe`; it retains the
runner-derived `--no-index` comment and omits the default `--no-upgrade` option.
No hashes were supplied by hand. Install commands and hash enforcement are unchanged.

## Exact dependency diff

All 53 existing locked package versions and their hash sets are unchanged.
No packages were removed. Six necessary packages were added, each with two
generated SHA-256 hashes (12 added hashes; no existing hashes removed or changed):

| Package | Version | Reason |
| --- | --- | --- |
| pip | 26.2.1 | Required by pip-tools; included by supported unsafe handling |
| setuptools | 84.0.0 | Required by pip-tools; fixes fresh hashed installation |
| hatchling | 1.32.3 | Existing pyproject build backend, required for no-build-isolation |
| editables | 0.6 | Existing backend's editable-build requirement |
| tomlkit | 0.15.1 | Hatchling dependency |
| trove-classifiers | 2026.6.1.19 | Hatchling dependency |

Other lock changes are generated dependency comments: hatchling is recorded for
packaging/pathspec/pluggy, and pyjwt's redundant self-reference is removed.
The existing OpenAI, Anthropic, HTTP clients, Pydantic, FastAPI, SQLAlchemy,
psycopg and Alembic pins and hashes are unchanged. Canonical dependency inputs
in `pyproject.toml` are unchanged.

## Fresh Python 3.12 proof

Created `.local/phase6b-lock-fresh-4539b0018e2b476fa03cf94f297f1aa8` from Python
3.12.14, with system site packages disabled. Its initial distribution inventory
contained only ensurepip's `pip==25.0.1`; setuptools was absent.
The disposable interpreter successfully ran, in this order:

```text
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check
```

The first command installed locked `setuptools==84.0.0` and `pip==26.2.1`.
The second installed Company OS 0.2.0. The third reported no broken requirements.
The disposable directory was verified inside `.local` and deleted afterward.
The normal `.venv` was not modified to manufacture this result. Local proof
metadata/logs are retained under ignored `.local/phase6b-lock-fresh.*`.

## Regression guard and changed paths

- `requirements.lock`: complete canonical hashed development/build graph.
- `scripts/boundaries.py`: reject pip-compile's unpinned-package warning in the
  existing canonical boundary/dependency check, called by `npm run check`.
- `tests/unit/test_core_boundaries.py`: one regression verifies the corrected
  lock is accepted and a lock containing the old warning is rejected.
- This handoff: exact scope, reproducibility evidence, checks and rollback.

## Validation

`npm.cmd run check` passed (exit 0): 424 Python tests passed, zero skipped,
one existing Starlette/AnyIO deprecation warning, in 629.92 seconds; two console
tests passed. Contract/OpenAPI generation, Ruff lint/format (197 files), mypy
(68 source files), canonical boundaries/dependency/migration/secret checks,
console ESLint and TypeScript all passed. Collection includes 88 tests across
the AI contract, gateway and review modules, plus shared contract/tenancy checks.
Fresh installation and `git diff --check` passed. The initial sandboxed focused
run reported 18 passes and one pytest temporary-directory permission error;
the canonical full check outside that sandbox passed all 424 tests.
Build/browser acceptance is deferred to the unchanged complete Ubuntu workflow,
as explicitly permitted for this dependency-only correction.

## Integrity, rollback and remaining gate

Raw SHA-256 comparison against the reviewed working tree confirms no runtime,
provider, authority, budget, accounting, RLS, schema or migration change.
Migration head remains `0026_phase6b_review_fixes`; there is no new migration.
No requirement behavior changes: this corrects dependency reproducibility only.
Rollback is a separate revert of this correction; it restores the known broken
fresh-environment lock and is therefore not suitable for publication. No database
rollback is needed. No production performance or provider claim is made.

After local acceptance, publish one separate corrective commit to the existing
PR #5 without amending the reviewed commit or force pushing. Both push and PR
Ubuntu `Phase 2 foundation` / `foundation-required` runs must be reported.
Stop on any new CI failure after installation; do not patch it automatically.
CI results and correction SHA belong in the delivery report after push.
Protected main stays unchanged; review ZIPs and credentials are not committed.
Do not merge; return for independent review.

OpenAI live calls: 0. Anthropic live calls: 0. Authorized live spend: $0.
Production AI routes: 0. No real provider credential was resolved or tested.
Phase 7 has NOT begun; no live-provider preflight is authorized here.
