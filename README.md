# Company OS

Private Company OS modular monolith. **Phase 2 foundation only.**

Next.js console, FastAPI API, heartbeat-only worker and PostgreSQL with enforced
workspace isolation. No business integrations, outbound sending, AI or production
deployment exists.

Prerequisites: Node.js 24, npm 11+, Python 3.12. From this repository:

```sh
npm ci
npm run setup
npm run dev
```

Open [localhost:3000](http://localhost:3000). Sign in as Synthetic User A or B.
Setup creates random local secrets in ignored `.env`; PostgreSQL data stays in
ignored `.local/pgdata`. No Docker or vendor account is required. Stop cleanly in
another terminal with `npm run stop`. Restart with `npm run dev`.

```sh
npm run check
npm run build
npx playwright install chromium
npm run test:e2e
```

Run checks and E2E while `npm run dev` is running. The Python suite creates and
removes its own randomly named test database, never the demo database.

See the [exact local/demo runbook](docs/local-development.md),
[Phase 2 handoff](docs/phases/phase-2-handoff.md),
[canonical documentation](docs/README.md) and [engineering instructions](AGENTS.md).
Work remains local and uncommitted for review. The first GitHub push and Phase 3
each require the founder's explicit authorization.
