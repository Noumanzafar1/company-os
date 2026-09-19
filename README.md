# Company OS

Private Company OS modular monolith. **Phase 6B offline AI gateway; independent review required.**

Next.js console, FastAPI API, durable worker and PostgreSQL with enforced
workspace isolation. All fixtures and runtime effects are synthetic. Phase 6B adds
bounded AI tasks, immutable context and routes, contained fake providers, cost
accounting, evaluations and human route promotion. Official OpenAI and Anthropic
adapter code is present but live calls and production routes remain disabled.
The canonical specification retains its Phase 1 design status.

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
[Phase 6B handoff and AI demo](docs/phases/phase-6b-handoff.md),
[Phase 4 handoff and runtime demo](docs/phases/phase-4-handoff.md),
[Phase 3 handoff and business-state demo](docs/phases/phase-3-handoff.md),
[Phase 2 handoff](docs/phases/phase-2-handoff.md),
[canonical documentation](docs/README.md) and [engineering instructions](AGENTS.md).
Phase 6A is closed at the baseline recorded in the Phase 6B brief. Phase 6B work
remains local and uncommitted. No commit, push, PR, merge, deployment or Phase 7 is
authorized. Real provider calls require separate founder authorization with an
explicit provider list and aggregate dollar cap.
