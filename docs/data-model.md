# Data model

This stage provides a PostgreSQL-backed simulated payment API, request-attempt
logging, and aggregate metrics. It does not process real payments or create
seed data. The PostgreSQL schema is created only through Alembic; application startup
does not create or mutate tables. The local Compose `migrate` service applies
Alembic upgrades after PostgreSQL becomes healthy and before the API starts.

## `payments`

Each row represents one simulated payment.

- `id` is the internal UUID primary key used by foreign keys.
- `public_id` is a separately generated, cryptographically random `pay_...`
  identifier intended for API responses. It is unique and is not derived from
  the internal key.
- `amount_minor` is an integer in the range 1–100,000,000 (smallest currency
  units); `currency` is a separate three-character code. The schema currently
  supports USD, EUR, and GBP. Storing integer minor units avoids floating-point
  rounding.
- `status` is one of `pending`, `succeeded`, or `failed`; new rows default to
  `pending`. This describes simulation state, not a real payment authorization.
- `created_at` and `updated_at` are timezone-aware timestamps. The database
  defaults both to the current time; SQLAlchemy ORM updates `updated_at` when a
  row is modified.

Database checks enforce amount, currency, and status invariants. The creation
time is indexed for chronological lookups.

## `idempotency_records`

Each row reserves a client idempotency key within an explicit `scope` (the
caller/workspace boundary). `POST /api/v1/payments` accepts an optional
`Idempotency-Scope` header, defaulting to `default`. Scope is currently a
caller-supplied namespace, not an authorization boundary; a future authenticated
API must derive it from the authenticated principal. Scopes are case-sensitive,
1–128 ASCII characters, start with an alphanumeric character, and otherwise
allow alphanumeric characters, `.`, `_`, `:`, and `-`.

- `(scope, idempotency_key)` has a database unique constraint.
- Keys are case-sensitive, 1–255 ASCII characters, start with an alphanumeric
  character, and otherwise allow alphanumeric characters, `.`, `_`, `~`, and
  `-`. Request validation and PostgreSQL check constraints enforce this format.
- `request_hash` stores a lowercase SHA-256 hex digest of the canonical request
  payload, not the payload itself.
- `payment_id` optionally references the original payment and uses `ON DELETE
  RESTRICT` so a payment cannot be removed while an idempotency record points
  to it.
- `response_status_code` and `response_body` are a nullable pair. When present,
  the JSONB body is limited by application behavior to the replayable public
  API response (never credentials or raw request data).
- `created_at` is timezone-aware and defaults to the database's current time.

Idempotency records do not expire and are not pruned automatically. This keeps
a key from becoming reusable and accidentally creating a second payment after
an undocumented retention window. Any future retention policy must preserve the
key for at least as long as replaying it could recreate the operation.

## `request_logs`

Each row records metadata for one API request. `request_id` is a unique UUID
that can correlate a response or sanitized error without using payment IDs as
request identifiers.

- `request_method`, `api_path`, `request_at`, `http_status_code`, and
  `processing_duration_ms` capture request metadata. Store only the normalized
  route path in `api_path` (without query parameters). Status and duration
  ranges are database-checked; `request_at` is timezone-aware and indexed.
- `idempotency_outcome` is one of `not_used`, `created`, `replayed`,
  `payload_mismatch`, or `in_progress`.
- `outcome` classifies the overall result as payment-created, idempotency
  replay, payload conflict, validation error, handled error, database error,
  or ordinary success.
- `payment_id` optionally references a payment with `ON DELETE RESTRICT`.
- `sanitized_error_code` is a bounded error code, not an exception message.

The table deliberately has no headers, authorization fields, or request-body
column. Middleware logs API and health attempts using the request ID, normalized
route template, method, status, duration, payment reference, outcome,
idempotency outcome, and an allowlisted error code. It never stores
idempotency keys, credentials, or arbitrary request data. Logging uses a
separate transaction after request handling; a log write failure is reported
but does not change the payment transaction or response. Request and payment
history is not deleted as part of normal operations. See [metrics.md](metrics.md)
for observability behavior and metric definitions.

## API contracts

`app.schemas.payment` defines `CreatePaymentRequest`, `PaymentResponse`,
paginated list responses, `MetricsSummaryResponse`, and `ApiErrorResponse`. A
create request accepts only a strict integer
`amount_minor` within the same database bounds and one supported currency;
unknown fields are rejected. This prevents card data or other uncontracted
fields from being silently accepted. Responses expose the public payment ID,
amount, currency, simulation status, and timezone-aware timestamps, but never
the internal database key.

`POST /api/v1/payments` requires an `Idempotency-Key` header. The payment and
its replayable response are committed atomically with the key record. The
canonical payload consists only of validated `amount_minor` and `currency`;
unknown fields are rejected and JSON object key ordering has no effect. A new
request returns 201; an identical replay returns the stored original response
with 200; reusing a key in the same scope with a different payload returns 409.
Replays do not re-read or mutate the payment, so their response remains the
original result even if the payment row later changes.

PostgreSQL's `(scope, idempotency_key)` unique constraint is the concurrency
authority. Creation uses `INSERT ... ON CONFLICT DO NOTHING RETURNING` inside
the same transaction as payment insertion and response persistence. Under
PostgreSQL's default READ COMMITTED isolation, a competing insert waits for the
winner; after it commits the loser reads and replays the stored result, while a
loser whose competitor rolls back can insert and create the payment. SQLSTATE
`40001` (serialization failure) and `40P01` (deadlock) retry the whole
transaction up to three attempts. If contention persists, the API returns
503; the caller should retry with the same key. Every failed transaction rolls
back both the key record and payment. If the commit succeeded but the response
was lost, a retry reads the durable original result from PostgreSQL.

The API only records a simulated `pending` payment. List endpoints use bounded
limit/offset pagination ordered by timestamp and primary key. `/health` and the
existing liveness/readiness routes provide health checks.

## Migrations

Revision `0001_stage2` creates the three tables, named constraints, foreign
keys, and indexes. Revision `0002_idempotency_key_formats` adds PostgreSQL
constraints for accepted key/scope formats. Revision
`0003_request_metrics` adds normalized request outcomes. Upgrade
applies the schema without inserting rows. Downgrade is destructive to
persisted records; do not run it against data that must be retained. Apply
changes with:

```powershell
.\backend\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```
