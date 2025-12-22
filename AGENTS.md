# Repository Guidelines

## Project Structure & Module Organization
- `app/` houses FastAPI routers (`app/api/endpoints`), schemas (`app/schemas`), and integrations or jobs under `app/services/**`, `app/coupang_*`, and `app/ownerclan_*`.
- `frontend/` is the Next 16 App Router UI (`src/app/*` routes, UI in `src/components`, utilities inside `src/lib`); styling starts in `src/app/globals.css`.
- `alembic/` tracks migrations, `docs/` stores API/design notes, and automation scripts live in `scripts/` with launcher helpers (`start_api.sh`, `start_frontend.sh`) at the repo root.

## Build, Test, and Development Commands
- Install backend deps with `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- Serve the API via `API_RELOAD=1 ./start_api.sh` on port 8888; `./stop_api.sh` frees the port and flushes `.api.pid`.
- Run the dashboard with `./start_frontend.sh` (port 3333) or `npm run build && npm run start` before releasing.
- Manage schema changes through `alembic revision --autogenerate -m "summary"` and `alembic upgrade head`.
- Exercise workflows through the curated helpers, e.g., `python scripts/run_processing.py`, `python scripts/coupang_status_report.py`, or the domain-specific `scripts/test_*.py`.

## Coding Style & Naming Conventions
- Backend modules stay snake_case, classes CamelCase, endpoints expose a module-level `router`, and every public API uses typed Pydantic models (see `app/schemas/product.py`).
- Services should isolate side effects per integration (Gemini, Coupang, OwnerClan, storage) and keep routers thin.
- Frontend code follows ESLint with TypeScript; components are PascalCase, hooks start with `use`, and shared helpers export named functions from `src/lib`.

## Testing Guidelines
- There is no monolithic `pytest`; run the focused runners such as `python scripts/test_ai_service.py`, `python scripts/test_sourcing.py`, and `python scripts/test_benchmark.py` plus any new `scripts/test_*.py` you add.
- Document inputs (env vars, DRY_RUN flags) and capture relevant `api.log` lines when sharing results.
- UI changes must pass `npm run lint`; add component or Playwright coverage under `frontend/` when shipping complex flows.

## Commit & Pull Request Guidelines
- Follow the observed log style `<type>: <short summary>` in imperative mood (`fix: ...`, `feat: ...`), and keep unrelated work in separate commits.
- Mention migrations, scripts, or env toggles touched in the commit body.
- Pull requests must explain motivation, list verification commands (e.g., `./start_api.sh`, `python scripts/run_processing.py`), and include screenshots for UI.

## Security & Configuration Tips
- Copy `.env.example` before running anything and supply Postgres, Supabase, Coupang, and AI provider credentials locally.
- Treat `api.log`, `frontend.log`, and script output as sensitive, using sandbox credentials or DRY_RUN options for marketplace-facing automation.
