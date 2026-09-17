# Phase 2 dependency inventory and rationale

Resolved versions are immutable in `requirements.lock` (Python, with artifact
hashes) and `package-lock.json` (JavaScript, with integrity hashes). These locks
contain **every transitive package**, not only the direct dependencies below.
The permitted direct dependency names are checked in `scripts/boundaries.py`.
No provider SDK, AI framework, broker, extra database or orchestration platform
is installed as an application dependency.

## Backend

| Direct package | Locked version | Purpose | Declared license family |
|---|---|---|---|
| FastAPI | 0.141.1 | HTTP routes and OpenAPI | MIT |
| Uvicorn | 0.53.0 | ASGI process | BSD |
| Pydantic | 2.13.5 | Closed request/response schemas | MIT |
| pydantic-settings | 2.15.0 | Validated environment configuration | MIT |
| SQLAlchemy | 2.0.54 | Connections, transactions and parameterized SQL | MIT |
| Alembic | 1.20.0 | The single schema history | MIT |
| psycopg / psycopg-binary | 3.3.5 | PostgreSQL protocol driver | LGPL / bundled library notices |
| PyJWT / cryptography | 2.14.0 / 50.0.1 | JWT issuer/audience/signature/expiry checks | MIT / Apache-2.0 or BSD |
| HTTPX | 0.28.1 | API and process integration tests; no business provider | BSD |
| pytest | 9.1.1 | Unit, contract, PostgreSQL and security tests | MIT |
| Ruff | 0.16.8 | Formatting and import/lint checks | MIT |
| mypy | 1.20.2 | Backend type checking | MIT |
| pip-tools | 7.6.1 | Reproducible hashed dependency lock | BSD |
| Hatchling | 1.32.0 | Python package build/editable install | MIT |

Build tooling/transitives include pip, setuptools, wheel, build, editables,
packaging, pathspec, pluggy, pyproject-hooks, tomlkit and trove-classifiers.
Runtime transitives include Starlette, AnyIO, annotated-doc/types, pydantic-core,
typing-extensions/inspection, python-dotenv, greenlet, h11/httpcore, certifi/idna,
click, cffi/pycparser, Mako/MarkupSafe and tzdata. Test/type-check dependencies
include iniconfig, Pygments, mypy-extensions, librt and colorama.
Starlette's HTTPX/BlockingPortal deprecation warnings are recorded in the handoff;
they do not affect the tested request behavior. Dependency changes need review.

## Console and local tooling

| Direct package | Pinned version | Purpose |
|---|---|---|
| Next.js / eslint-config-next | 16.3.5 | Server-rendered BFF console and framework lint rules |
| React / react-dom | 19.3.0 | View rendering |
| jose | 6.1.3 | Server-only development JWT assertion |
| server-only | 0.0.1 | Prevent API/session helper imports into browser components |
| TypeScript | 5.9.3 | Static frontend contracts |
| @types/node | 24.10.13 | Node runtime types |
| @types/react / @types/react-dom | 19.2.14 / 19.2.3 | React types |
| ESLint | 9.39.3 | Frontend static checks; version compatible with current Next config |
| Vitest | 4.1.11 | CSRF/environment unit tests; patched after the initial audit |
| @playwright/test | 1.58.2 | Real-browser founder demo and security tests |
| openapi-typescript | 7.13.0 | Generate frontend types from backend OpenAPI |
| embedded-postgres | 18.4.0-beta.17 | Local-only PostgreSQL 18.4 binary lifecycle |

The JavaScript application/tooling packages use MIT/Apache/BSD-compatible declared
licenses; redistributed binaries include their upstream notices. Package locks
and installed metadata are the source of exact transitive versions/licenses.
No separate commercial service, provider account or paid license was purchased.
Package security scan: `npm audit --audit-level=moderate`; final result in handoff.

The lock is the reproducibility contract; semver ranges in `pyproject.toml` describe
supported resolution bounds and do not authorize unreviewed upgrades. Always
install with `--require-hashes -r requirements.lock` and `npm ci`.
