# Testing and CI

## Backend

Backend tests are in `backend/tests`. Unit/schema tests can run without a live
database. API, logging, readiness, rollback, persistence, and race tests use a
real PostgreSQL database. The suite includes same-key concurrent requests and
asserts that equivalent concurrent requests leave exactly one payment and one
idempotency record. SQLite is not used as evidence for PostgreSQL concurrency.

Every test marked `integration` requires `DATABASE_URL` to identify a dedicated
database whose name ends in `_test`. Before an integration test runs, the shared
fixture verifies that `payments`, `idempotency_records`, and `request_logs` have
no pre-existing rows. It fails without deleting anything if any are present.
On completion it removes only rows created by that test. Do not run the suite
against the developer database, a shared database, or any database containing
important data.

With a dedicated PostgreSQL test database already created, set the test URL in
PowerShell (use a URL-safe local password; do not print or commit it), migrate,
then run:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://TEST_USER:URL_SAFE_TEST_PASSWORD@localhost:5432/vitt_guard_test"
.\backend\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
Set-Location backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
Set-Location ..
```

The URL is an example shape; replace the user/password locally. Ensure that
database is dedicated and disposable before running migrations and tests.
Backend unit tests without a database are:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -m "not integration"
Set-Location ..
```

## Frontend and full quality checks

Vitest tests use controlled fixtures only inside test code. The production
client remains connected to the configured API. Run frontend checks from
`frontend`:

```powershell
npm.cmd test -- --pool=threads --maxWorkers=1 --fileParallelism=false
npm.cmd run lint
npm.cmd run format:check
npm.cmd run typecheck
npm.cmd run build
```

There is no coverage threshold configured and no coverage percentage is
reported unless coverage is explicitly measured.

## GitHub Actions

`.github/workflows/ci.yml` provisions an isolated PostgreSQL service named
`vitt_guard_test`. The backend job installs the development extras, runs Ruff,
applies `alembic upgrade head`, and runs pytest. The frontend job runs `npm ci`,
Vitest, ESLint, Prettier check, TypeScript, and the Vite production build. A
failed command fails its job.

The CI database service is not the local developer database. CI uses no
production payment or processor integration. For root-level PowerShell
commands, see [the README quality-check section](../README.md#testing-and-ci).
