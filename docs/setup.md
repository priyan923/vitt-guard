# Development setup

## What this stage provides

This stage establishes the frontend/backend monorepo, local PostgreSQL
configuration, API process and database health checks, migration tooling, and
code-quality commands. It adds a PostgreSQL-backed simulated payment API and
request-attempt logging, but does not perform real payment processing or add
demo records.

## Configuration and startup validation

The backend reads `DATABASE_URL` from the process environment or the root
`.env` file. It fails during startup if the value is missing, malformed, not a
`postgresql+psycopg` URL, or lacks a host, database, or credentials. The URL is
not embedded in application code. Compose passes a URL with the internal `db`
service hostname to the API container; a backend process running on Windows
uses the host-mapped `localhost` URL from `.env`.

The `.env.example` file contains placeholders only. Copy it to `.env` and
replace every `REPLACE_ME` value with local-only values before starting Compose.
Never add `.env` or production secrets to Git.

## Database and migrations

The `db` Compose service stores PostgreSQL data in a named Docker volume and
reports healthy only when `pg_isready` can connect to the configured database.
The one-shot `migrate` service waits for database health and upgrades Alembic
to head. The API waits for successful migration, and the frontend waits for API
readiness. The API's readiness endpoint performs a real `SELECT 1`; it returns
HTTP 503 when the database is unavailable. `/health` and `/health/live` check
liveness without requiring the database.

Alembic is configured to use the validated database URL and SQLAlchemy
metadata. Revision `0001_stage2` adds payment, idempotency, and request-log
tables without inserting application data. Compose applies migrations through the local `migrate` service; host-run API
development must apply them explicitly with
`python -m alembic -c backend\alembic.ini upgrade head` from the repository
root. Application startup does not create tables. See
[data-model.md](data-model.md) for table constraints and downgrade behavior.

The API exposes simulated payment creation and listing at
`/api/v1/payments`, payment retrieval at `/api/v1/payments/{payment_id}`,
request history at `/api/v1/requests`, and database-backed metrics at
`/api/v1/metrics/summary`. Interactive OpenAPI documentation is available at
`/docs` when the API is running. Payment creation requires an
`Idempotency-Key`; it never performs a real transaction.
The optional `Idempotency-Scope` header separates caller/workspace namespaces
(defaults to `default`); it is not an authorization mechanism. Idempotency keys
are retained indefinitely and are replayed from PostgreSQL after process
restarts. Apply the current Alembic head before running the API.
Request outcome classification, logging failure behavior, and SQL metric
definitions are documented in [metrics.md](metrics.md).

Compose publishes the database, API, and frontend on loopback only. Local
authentication defaults off; optional backend HTTP Basic auth can be enabled
using `AUTH_ENABLED`, `AUTH_USERNAME`, and `AUTH_PASSWORD`. Production mode
requires authentication, a password of at least 32 characters, and an explicit
CORS allowlist. The app has no rate limiting or multi-user authorization. Do
not expose the local configuration through a public interface or proxy. CORS
is a browser policy, not an authorization control. See [security.md](security.md).

## Windows notes

- The documented frontend commands call `npm.cmd` directly. This avoids relying
  on PowerShell's `npm.ps1` wrapper or changing the machine's execution policy.
- Use `.\backend\.venv\Scripts\python.exe` to run the backend's Python tools
  without activating the virtual environment.
- Docker Desktop must be installed and running for the full Compose stack.
- Keep passwords URL-safe until the configuration is extended to handle URL
  escaping for special characters.

## Tests

`pytest -m "not integration"` runs tests that do not require a running database,
including request-contract and schema-invariant checks.
`pytest -m integration` exercises the API and database-backed request logging
against PostgreSQL and therefore requires a migrated, dedicated test database.
The tests clean their configured test database; do not point them at a database
containing important data.
Frontend lint, Prettier, TypeScript, and production-build checks are separate
commands in the root README.
