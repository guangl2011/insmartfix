# InsmartFix

Monorepo for **InsmartFix**, the Insmart AI field app for contractors: web portal, backend API, and iOS and Android apps.

- Product design: [`docs/design/INSMARTFIX_PRODUCT_DESIGN.md`](docs/design/INSMARTFIX_PRODUCT_DESIGN.md)
- Color language: [`docs/design/COLOR_LANGUAGE.md`](docs/design/COLOR_LANGUAGE.md)

## How this repo is built
- **Process:** [`docs/process/DEVELOPMENT_PROCESS.md`](docs/process/DEVELOPMENT_PROCESS.md): spec → **G1 Spec Review (human)** → plan → scaffold → build → system test → **G2 Test Review (human)** → launch. Everything between the two gates is automated by the agent team in [`.claude/agents/`](.claude/agents).
- **Spec:** [`docs/specs/INSMARTFIX_V1_SPEC.md`](docs/specs/INSMARTFIX_V1_SPEC.md)
- **Test plan & environments:** [`docs/testing/TEST_PLAN.md`](docs/testing/TEST_PLAN.md)
- **Launch plan:** [`docs/launch/LAUNCH_PLAN.md`](docs/launch/LAUNCH_PLAN.md)

## Layout
```
apps/
  api/          FastAPI · Python 3.12 · uv · Pydantic v2 · SQLAlchemy 2 · Alembic · pytest/ruff/mypy
  web/          Next.js 15 App Router · TypeScript · vitest + RTL · Playwright (Pixel 7, iPhone 14, desktop)
  mobile/       Expo SDK 58 · expo-router · jest + RNTL · eas.json · Maestro flows in e2e/
packages/
  contracts/    openapi.json exported from the API → generated TS types + typed fetch client
  core/         pure TS shared logic (SLA, ordering, validation, draft/offline queue) — M3
  tokens/       COLOR_LANGUAGE v1.3 → tokens.css (web) + RN theme object (mobile), light + dark
  ui-web/       web component kit — M4
infra/          docker-compose.yml (postgres, minio, api, web, toxiproxy), .env.example, k6/
.github/        ci.yml (per PR) · nightly.yml (full E2E, Android, iOS, k6, ZAP) · deploy.yml · dependabot
Makefile        make help
```

## Quick start

Prerequisites: Node 22 + pnpm 10 (`corepack enable`), Python 3.12 + [uv](https://docs.astral.sh/uv/), Docker with Compose v2.
For mobile: Xcode (iOS simulator) and/or Android Studio (emulator); [Maestro](https://maestro.mobile.dev) for mobile E2E.

```bash
make install          # pnpm install --frozen-lockfile && uv sync --frozen
```

### local-mock — UI with no backend (TEST_PLAN §3)
```bash
pnpm dev:mock                                   # web on http://localhost:3000, DATA_SOURCE=mock
pnpm --filter @insmartfix/mobile dev            # Expo dev server; EXPO_PUBLIC_DATA_SOURCE defaults to mock
```
The MSW contract mock behind `DATA_SOURCE=mock` is filled in with the screens (M4 web, M5 mobile).

### local-stack — the full loop in Docker (TEST_PLAN §3)
```bash
make up               # copies infra/.env.example → infra/.env, builds, starts, waits until healthy
make seed             # TEST_PLAN §5 fixtures (stub until M1)
open http://localhost:3000                      # web (DATA_SOURCE=live → api)
curl http://localhost:8000/v1/readyz            # api (checks Postgres)
E2E_BASE_URL=http://localhost:3000 E2E_EXPECT_LIVE=1 make e2e-web
make down             # stop and delete volumes
```
Equivalent without make: `cp infra/.env.example infra/.env && docker compose -f infra/docker-compose.yml up -d --build --wait`.

| Service | Host port | Notes |
|---|---|---|
| web | 3000 | Next.js; talks to the API server-side only |
| api | 8000 | FastAPI, `/v1/healthz`, `/v1/readyz` |
| postgres | 55432 | Postgres 16 |
| minio | 9000 / 9001 | S3-compatible storage (console on 9001) |
| toxiproxy | 8474 (admin), 18000 → api, 15432 → postgres | resilience tests |

Mobile against the local stack: `EXPO_PUBLIC_DATA_SOURCE=live EXPO_PUBLIC_API_BASE_URL=http://<your-LAN-IP>:8000 pnpm --filter @insmartfix/mobile dev`.

### Tests and checks
| Command | What |
|---|---|
| `make lint` | ruff + mypy (API), eslint (incl. the NFR-4 status-color rule) + tsc + prettier |
| `make test` | all unit/integration tests with TEST_PLAN §4 coverage thresholds |
| `make test-api` / `test-web` / `test-mobile` | one area |
| `make contracts` | re-export `openapi.json` and regenerate TS types (CI fails on drift) |
| `make e2e-web` | Playwright; set `PW_IPHONE_ENGINE=chromium` if WebKit isn't installed locally |
| `make e2e-android` / `make e2e-ios` | Maestro flows on a running emulator / booted simulator |

Configuration is environment-only: `DATABASE_URL`, `S3_*`, `JWT_SECRET`, `DATA_SOURCE`, `API_BASE_URL`, `FAKE_CLOCK` (see `infra/.env.example`; dev-only placeholder values).
Staging/production secrets live only in the GitHub `staging` / `production` environments.
