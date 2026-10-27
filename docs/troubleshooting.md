# Troubleshooting

## Compose cannot start because a value is missing

Ensure the repository root contains `.env`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Replace all `REPLACE_ME` fields with local-only values. Keep `.env` ignored and
never paste its contents into logs, screenshots, issues, or source control.
Passwords used in database URLs must be URL-safe for this setup.

## Docker Desktop or port errors

Confirm Docker Desktop is running:

```powershell
docker info
docker compose ps
```

Default local ports are 5432 (PostgreSQL), 8000 (API), and 5173 (frontend).
If one is already in use, change the corresponding `*_PORT` value in `.env`,
then recreate services with `docker compose up --build -d`. The services bind
to loopback only.

## Startup or healthcheck is stuck

Inspect each service and recent logs without printing environment files:

```powershell
docker compose ps
docker compose logs --tail 100 db migrate api frontend
```

The expected order is database healthy, migration exits successfully, API
healthy, then frontend healthy. `/health/live` checks the API process;
`/health/ready` additionally checks PostgreSQL. A readiness failure is an
honest dependency failure, not proof that the database is healthy.

If migration fails, review the Alembic error and the `migrate` service exit
status. Do not work around it by creating tables manually. Fix the configuration
or migration problem, then retry:

```powershell
docker compose up --build -d
```

## Frontend loads but API calls fail

The Compose frontend uses Vite's same-origin proxy to the internal `api`
service. Verify the API is healthy and see recent logs:

```powershell
docker compose ps
docker compose logs --tail 100 api frontend
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

For host-run Vite, the default proxy target is `http://127.0.0.1:8000`; set
`VITE_API_PROXY_TARGET` to a different public host address only when required.
Do not put secrets into `VITE_*` variables. If using direct cross-origin calls,
add the exact browser origin to `CORS_ALLOWED_ORIGINS`; CORS is not
authentication.

## PostgreSQL tests refuse to run

Integration tests require a dedicated PostgreSQL URL whose database name ends
with `_test`. The suite refuses to run if application tables contain rows at
baseline. Confirm the URL target without echoing credentials, and do not point
it at the local development DB. The fixture does not clear pre-existing rows.
See [testing.md](testing.md).

## Resetting local data

`docker compose stop` and `docker compose down` preserve the named database
volume. To intentionally discard the local database, verify the current
Compose project and then run:

```powershell
docker compose down --volumes
docker compose up --build -d
```

This permanently deletes local persisted records. Do not use it to recover a
database that contains data you need.
