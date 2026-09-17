# Phase 2 environment

Local process orchestration: `scripts/local.mjs`. CI: `.github/workflows/ci.yml`.
Both use PostgreSQL 18.4. API and worker use separate non-owner, NOBYPASSRLS roles.
Only setup/migration/test tooling receives the owner URL; the console receives no
database environment variables. All local listeners bind to loopback.

There is no production deployment manifest, paid service or provider provisioning.
The managed deployment design remains the reference in `docs/17-deployment.md`
and requires its separate release gate. Do not use the local demo as a public
deployment; its development identity adapter intentionally impersonates synthetic
users on the local machine.
