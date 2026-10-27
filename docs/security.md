# Security and deployment boundary

## Intended use

Vitt Guard is a simulated-payment demonstration. It stores
development records only and does not collect card data, authorize payments,
call a processor, or move money. Treat all stored data and API access as local
development data.

The supported initial trust boundary is one developer workstation:

- Docker Compose publishes PostgreSQL and the API only on `127.0.0.1`.
- The documented host-run Uvicorn command uses its loopback default.
- Local Compose defaults to authentication disabled. Any process or user able
  to reach the loopback API can then create simulated records and read local
  data.
- CORS requires explicit origins and defaults to no cross-origin browser
  access. The local `.env.example` opts in only to localhost Vite origins.
  CORS is a browser policy, not authentication or a network access control.
- Do not change the local port bindings to public interfaces or expose the
  unauthenticated local configuration through a proxy.

## Implemented controls

- Payment requests accept only strict integer minor-unit amounts from 1 through
  100,000,000, supported currencies (`USD`, `EUR`, `GBP`), and no additional
  body fields. Idempotency keys and scopes use bounded formats.
- Request bodies are limited by `MAX_REQUEST_BODY_BYTES` (default 16 KiB,
  allowed configuration 1 KiB–1 MiB). Payment and request list limits are
  1–100; offsets are bounded to 0–1,000,000.
- Request validation and unexpected errors return stable, sanitized error
  responses. Request logs contain normalized paths and outcome codes, not raw
  bodies, headers, query values, credentials, or exception text.
- PostgreSQL connection pools are bounded to five base connections and five
  overflow connections. Pool acquisition and connection, lock, and statement
  waits have finite timeouts. Database sessions close and roll back on
  exceptions; the engine is disposed during application shutdown.
- `/health/live` reports process liveness without a database check.
  `/health/ready` runs a real database query and returns an error when the
  dependency is unavailable.
- CORS allows only HTTP(S) origins listed in `CORS_ALLOWED_ORIGINS`; wildcards,
  credentials, paths, and URL credentials are rejected. `Authorization` is
  explicitly permitted for the optional HTTP Basic flow; cookies are not used.
- `AUTH_ENABLED=true` protects every `/api/v1/*` route with HTTP Basic
  authentication. Credentials are compared in constant time and configured
  from backend environment variables. Production mode refuses to start unless
  authentication is enabled, the password is at least 32 characters, and an
  explicit CORS allowlist is configured. Health and auth bootstrap routes are
  intentionally public.
- The frontend stores a signed-in username/password-derived Authorization
  value in JavaScript memory only; it is cleared on sign-out or page reload and
  never stored in local/session storage. The UI bundle contains no secret.
- Production responses add HSTS; the hosting ingress must enforce HTTPS and
  redirect HTTP before requests reach the app. No session cookies are used, so
  `Secure`, `HttpOnly`, and `SameSite` cookie settings do not apply.
- Frontend `VITE_*` settings are public browser configuration. They must never
  contain database credentials, API secrets, or other private values.
- Idempotency is transactionally persisted in PostgreSQL with a unique
  constraint; retries use the same key and cannot silently create a second
  operation.

The authentication gate is suitable only as a minimal single-operator access
barrier for a low-risk portfolio demo. It does not provide user provisioning,
password reset, roles, per-user data isolation, or account-level audit trails.
There is no application-level rate limiter. Before any public deployment,
configure a topology-appropriate edge rate limit for login attempts and
write-capable API routes, and use managed TLS, secret storage, backups, logs,
and alerting. Keep the application private until these controls are in place.

## Local configuration

For direct cross-origin development only, set an explicit comma-separated
origin list in the root `.env`, for example:

```dotenv
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
MAX_REQUEST_BODY_BYTES=16384
```

The Vite same-origin proxy does not require a CORS exception. Do not add a
wildcard origin. Keep `.env` out of source control and use local-only database
credentials; do not put secrets in frontend environment variables. Set
`APP_ENV=production`, `AUTH_ENABLED=true`, `AUTH_USERNAME`, `AUTH_PASSWORD`,
and `CORS_ALLOWED_ORIGINS` only in the hosting provider's secret/configuration
store for a hosted instance.
