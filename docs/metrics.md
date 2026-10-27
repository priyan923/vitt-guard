# Request observability and metrics

## Request records

Every request to `/api/v1/*`, `/health`, `/health/live`, and `/health/ready`
gets a server-generated UUID returned as `X-Request-ID`. A `request_logs` row
stores the uppercase HTTP method, registered route template (never path
parameters or query strings), database timestamp, HTTP status, elapsed
milliseconds, outcome, idempotency outcome, optional internal payment
reference, and optional sanitized error code.

`outcome` is one of:

- `payment_created`: a new payment was committed.
- `idempotency_replay`: a prior result was replayed.
- `payload_conflict`: a key was reused with a different canonical payload or
  another handled conflict returned 409.
- `validation_error`: request validation returned 422.
- `database_error`: a handled database failure occurred.
- `handled_error`: another handled error occurred.
- `success`: another successful request.

The separate `idempotency_outcome` column records `created`, `replayed`,
`payload_mismatch`, `in_progress`, or `not_used`; thus request attempt outcomes
can be analyzed without inferring them from payment rows.

Request validation errors are logged as 422 with `validation_error`. Handled
HTTP/service exceptions retain their response status and a bounded error code;
their exception messages are not persisted. Database failures retain their
sanitized classification (`database_unavailable` or `database_error`).
Unexpected errors return a generic response and are classified as
`handled_error` with the sanitized code `internal_error`.

Logging uses a separate short-lived SQLAlchemy session after the response has
been produced. If inserting a log row fails, the failure is reported using
only request ID and exception class; the existing payment transaction and HTTP
response are not changed. For a database failure in the payment operation,
the payment transaction rolls back and a request log is attempted afterward.
Logging is best-effort when PostgreSQL itself is unavailable.

No headers (including idempotency, authorization, or cookies), credentials,
raw request bodies, raw exception messages, or query strings are logged.
Payment IDs are associated through a database foreign key and exposed in the
request API only as public payment IDs.

## Summary metrics

`GET /api/v1/metrics/summary` returns persisted aggregates. With no query
parameters it reports lifetime counts as visible when its SQL queries run. The
metrics request itself is persisted after its response and so is not included
in that response's `total_requests`. It never returns a rate, since this
endpoint does not define a rate denominator.

| Metric | Data definition |
|---|---|
| `total_payments` | Count of `payments` rows in the selected window. |
| `payments_by_status` | `COUNT(*) GROUP BY payments.status` in that window, including zero-valued known statuses. |
| `total_requests` | Count of `request_logs` rows in the selected window. |
| `payment_attempts` | Count of request rows whose normalized route is `/api/v1/payments` or `/api/v1/payments/{payment_id}`. |
| `successful_requests` | Count of request rows with HTTP status 200–299. |
| `conflicts` | Count of request rows with HTTP status 409. |
| `idempotency_replays` | Count of request rows with `idempotency_outcome = 'replayed'`. |

Payment totals are aggregated from `payments`; request totals and categories
are aggregated from `request_logs` independently. They are not joined, so
payments with multiple attempts cannot multiply either count. Queries use SQL
`COUNT` and `GROUP BY`; no table rows are loaded into application memory.
`created_at` and `request_at` have database indexes for chronological reads.
Pagination for request history orders by timestamp descending, then UUID
descending for deterministic ties.

Optional `start` and `end` parameters must be timezone-aware timestamps. They
are normalized to UTC and applied as the half-open interval
`[start, end)`: `timestamp >= start AND timestamp < end`. Each table uses its
own timestamp (`payments.created_at` or `request_logs.request_at`). Either
bound may be omitted; if both are given, `end` must be later than `start`.
Empty databases and empty windows return zero counts, known payment statuses
with zero values, and no fabricated series.

## Schema migration

Revision `0003_request_metrics` adds the constrained `outcome`
column to `request_logs`. Run Alembic to `head` before starting the updated API.
