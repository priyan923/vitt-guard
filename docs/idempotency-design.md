# Idempotency design

`POST /api/v1/payments` stores simulated operations only. Idempotency keeps a
client retry from creating a second payment when the first response is lost or
the client deliberately retries.

## Request identity and canonical payload

The identity is `(scope, idempotency_key)`. `Idempotency-Scope` defaults to
`default` and is a namespace, not an authenticated tenant boundary. Keys and
scopes are case-sensitive. Keys allow 1–255 ASCII characters, begin with an
alphanumeric character, and then allow alphanumeric characters, `.`, `_`,
`~`, and `-`. Scopes allow 1–128 ASCII characters, begin alphanumeric, and
then allow alphanumeric characters, `.`, `_`, `:`, and `-`.

The canonical payload contains exactly the validated `amount_minor` integer
and supported `currency` code. Unknown fields are rejected. Canonical JSON
uses stable key ordering, so object property order does not affect the SHA-256
digest. The hash, not a raw request body, is stored.

## Outcomes

| Situation | HTTP result | Persistence behavior |
|---|---:|---|
| Valid, unseen scoped key | `201 Created` | Commit one payment and its idempotency record and original response together. |
| Same scope, key, and canonical payload | `200 OK` | Return the stored original response; do not insert or mutate a payment. |
| Same scope and key, changed canonical payload | `409 Conflict` | Keep the original payment and response unchanged. |
| Same key in a different scope | `201 Created` when new there | Scope is part of the unique identity. |
| Invalid request | `422 Unprocessable Entity` | Validation runs before payment persistence; no payment/key operation is created. |
| Retryable serialization/deadlock contention persists | `503 Service Unavailable` | The attempt transaction is rolled back; retry with the same key and exact payload. |

Idempotency records do not expire automatically. An undocumented expiry could
allow a delayed retry to create a duplicate, so retention requires a deliberate
policy and proof that replay cannot recreate the operation.

## Transaction and concurrency flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DB as PostgreSQL

    Client->>API: POST + scope/key + validated payload
    API->>API: Canonicalize amount and currency; hash
    API->>DB: Begin transaction; INSERT key ON CONFLICT DO NOTHING
    alt This transaction reserved the unique key
        API->>DB: Insert payment and store replay response
        API->>DB: Commit all operation records atomically
        API-->>Client: 201 + payment response
    else Key already committed by an equivalent request
        API->>DB: Read key/hash and stored response
        API-->>Client: 200 + original response
    else Key exists with a different canonical hash
        API-->>Client: 409 + sanitized conflict
    end
```

The `(scope, idempotency_key)` database unique constraint is the final
concurrency safeguard. PostgreSQL arbitrates concurrent insertions; the
application does not rely on a process-local lock or a check-then-insert race.
The payment, key record, hash, and response are written in the same transaction.
If any operation fails before commit, the transaction rolls back so neither
the payment nor its replay record is left committed alone.

Under PostgreSQL READ COMMITTED behavior, a competing insert waits for the
winner. Once the winner commits, the competitor reads the stored record and
replays or conflicts based on the hash. If the competing transaction rolls
back, another caller may reserve the key and create the operation. SQLSTATE
`40001` and `40P01` are retried for the whole transaction up to three attempts;
continued contention returns a retryable service error after rollback.

If the transaction commits but the HTTP response is lost, the exact retry
returns the durable result from PostgreSQL, including after process restart.
If the first request fails before commit, retrying the same key and payload
may create the operation because no committed result exists.

Request-attempt logging is separate and best-effort. A logging outage cannot
roll back or mutate the payment transaction. Logs never contain raw payloads,
keys, credentials, or unrestricted exception text. See
[metrics.md](metrics.md) for log outcomes and
[data-model.md](data-model.md) for constraints.
