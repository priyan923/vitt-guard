import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Code2,
  KeyRound,
  RotateCcw,
  Send,
} from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  API_BASE_URL,
  ApiError,
  createPayment,
  getAuthenticatedUsername,
  getRequest,
} from "../api/client";
import type {
  ApiResult,
  CreatePaymentPayload,
  Payment,
  PaymentCurrency,
} from "../api/types";
import { CopyButton, ShortId } from "../components/Formatting";
import { PageHeading, StatusBadge } from "../components/States";
import { buildCurlCommand } from "../utils/curl";

interface PaymentAttempt {
  payload: CreatePaymentPayload;
  idempotencyKey: string;
  scope: string;
}

interface ExplorerResult {
  attempt: PaymentAttempt;
  response: ApiResult<Payment> | null;
  error: ApiError | null;
}

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

function responseRequestId(result: ExplorerResult | null): string | null {
  if (!result) return null;
  if (result.response?.requestId) return result.response.requestId;
  if (result.error?.requestId) return result.error.requestId;

  const body = result.error?.body;
  if (body && typeof body === "object" && "request_id" in body) {
    const requestId = body.request_id;
    return typeof requestId === "string" ? requestId : null;
  }
  return null;
}

export function ApiExplorerPage() {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("2499");
  const [currency, setCurrency] = useState<PaymentCurrency>("USD");
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);
  const [scope, setScope] = useState("default");
  const [result, setResult] = useState<ExplorerResult | null>(null);

  const mutation = useMutation<ApiResult<Payment>, ApiError, PaymentAttempt>({
    mutationFn: ({ payload, idempotencyKey: key, scope: keyScope }) =>
      createPayment(payload, key, keyScope),
    onSuccess: async (response, attempt) => {
      setResult({ attempt, response, error: null });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["payments"] }),
        queryClient.invalidateQueries({ queryKey: ["metrics"] }),
        queryClient.invalidateQueries({ queryKey: ["requests"] }),
      ]);
    },
    onError: async (error, attempt) => {
      setResult({ attempt, response: null, error });
      if (error.status > 0) {
        await queryClient.invalidateQueries({ queryKey: ["requests"] });
      }
    },
  });

  const requestId = responseRequestId(result);
  const requestLog = useQuery({
    queryKey: ["request", requestId],
    queryFn: async () => (await getRequest(requestId!)).data,
    enabled: Boolean(requestId),
  });

  const payload: CreatePaymentPayload = {
    amount_minor: Number(amount),
    currency,
  };
  const curl = buildCurlCommand(
    payload,
    idempotencyKey,
    scope,
    API_BASE_URL,
    getAuthenticatedUsername(),
  );
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    send({
      payload: { ...payload },
      idempotencyKey,
      scope,
    });
  }

  function send(attempt: PaymentAttempt) {
    setResult({ attempt, response: null, error: null });
    mutation.mutate(attempt);
  }

  function showNewKey() {
    setIdempotencyKey(newIdempotencyKey());
  }

  const resultBody = result?.response?.data ?? result?.error?.body;
  const isValidationError = result?.error?.status === 422;
  const isConflict = result?.error?.status === 409;
  const isUnknownOutcome =
    result?.error?.failureKind === "timeout" ||
    result?.error?.failureKind === "network";
  const isReplay = result?.response?.status === 200;
  const isCreated = result?.response?.status === 201;

  return (
    <>
      <PageHeading
        eyebrow="DEVELOPER TOOLS"
        title="API Explorer"
        description="Exercise payment creation, idempotency, and request inspection against the live API."
      />
      <div className="simulation-banner">
        <span className="simulation-banner__icon">
          <KeyRound size={17} />
        </span>
        <div>
          <strong>Simulation mode — no real money moves</strong>
          <p>
            Requests create persisted development records only. This endpoint
            does not process financial transactions.
          </p>
        </div>
      </div>

      <div className="explorer-grid">
        <section className="panel explorer-form-panel">
          <div className="panel__heading">
            <div>
              <h2>New payment or idempotency test</h2>
              <p>POST /api/v1/payments</p>
            </div>
            <span className="method-pill">POST</span>
          </div>
          <form className="explorer-form" onSubmit={submit}>
            <label className="field-label" htmlFor="amount-minor">
              Amount in minor units
            </label>
            <div className="input-with-suffix">
              <input
                id="amount-minor"
                type="number"
                min="1"
                max="100000000"
                step="1"
                required
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
              <span>minor units</span>
            </div>
            <span className="field-hint">
              Enter a whole number from 1 to 100,000,000.
            </span>

            <label className="field-label" htmlFor="currency">
              Currency
            </label>
            <select
              id="currency"
              value={currency}
              onChange={(event) =>
                setCurrency(event.target.value as PaymentCurrency)
              }
            >
              <option value="USD">USD — US Dollar</option>
              <option value="EUR">EUR — Euro</option>
              <option value="GBP">GBP — British Pound</option>
            </select>

            <div className="field-label-row">
              <label className="field-label" htmlFor="idempotency-key">
                Idempotency key
              </label>
              <button
                className="inline-action"
                type="button"
                onClick={showNewKey}
              >
                <RotateCcw size={14} /> Generate fresh key
              </button>
            </div>
            <input
              id="idempotency-key"
              type="text"
              pattern="[A-Za-z0-9][A-Za-z0-9._~-]{0,254}"
              maxLength={255}
              required
              value={idempotencyKey}
              onChange={(event) => setIdempotencyKey(event.target.value)}
            />
            <span className="field-hint">
              Keep the same key and payload to retry. Change the payload with
              this key to receive a conflict.
            </span>

            <label className="field-label" htmlFor="idempotency-scope">
              Idempotency scope
            </label>
            <input
              id="idempotency-scope"
              type="text"
              pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
              maxLength={128}
              required
              value={scope}
              onChange={(event) => setScope(event.target.value)}
            />
            <span className="field-hint">
              Namespace only; this is not an authentication boundary.
            </span>

            <button
              className="button button--primary submit-button"
              type="submit"
              disabled={mutation.isPending}
            >
              <Send size={16} />
              {mutation.isPending ? "Sending request…" : "Send request"}
            </button>
          </form>
          {result && (
            <div className="explorer-retry">
              <div>
                <strong>Previous attempt</strong>
                <span>
                  {result.attempt.payload.amount_minor}{" "}
                  {result.attempt.payload.currency} · key{" "}
                  <code>{result.attempt.idempotencyKey}</code> · scope{" "}
                  <code>{result.attempt.scope}</code>
                </span>
              </div>
              <button
                className="button button--secondary"
                type="button"
                disabled={mutation.isPending}
                onClick={() => send({ ...result.attempt })}
              >
                <RotateCcw size={15} />
                Retry exact request
              </button>
            </div>
          )}
        </section>

        <div className="explorer-side">
          <section className="panel curl-panel">
            <div className="panel__heading">
              <div>
                <h2>PowerShell cURL example</h2>
                <p>Uses current form values and configured API base URL</p>
              </div>
              <CopyButton value={curl} label="Copy cURL command" />
            </div>
            <pre className="code-block">
              <code>{curl}</code>
            </pre>
            <p className="metrics-note">
              Uses curl.exe. URL credentials, query parameters, and fragments
              are omitted. If authenticated, cURL prompts for the password;
              none is included in the copied command.
            </p>
          </section>

          <section className="panel response-panel" aria-live="polite">
            <div className="panel__heading">
              <div>
                <h2>Response</h2>
                <p>Actual API response</p>
              </div>
              {result && (
                <span
                  className={`response-status ${
                    result.error
                      ? "response-status--error"
                      : result.response?.status === 200
                        ? "response-status--replay"
                        : ""
                  }`}
                >
                  {mutation.isPending
                    ? "Pending"
                    : (result.response?.status ??
                      (result.error?.status || "No HTTP response"))}
                </span>
              )}
            </div>
            {!result ? (
              <div className="response-placeholder">
                <Code2 size={19} />
                <span>Send a request to inspect the response.</span>
              </div>
            ) : mutation.isPending ? (
              <div className="response-placeholder" role="status">
                <span className="spinner-small" />
                Sending request to the API…
              </div>
            ) : (
              <>
                {isCreated && (
                  <div className="explorer-outcome explorer-outcome--success">
                    <CheckCircle2 size={17} />
                    <span>New payment created (HTTP 201).</span>
                  </div>
                )}
                {isReplay && (
                  <div className="explorer-outcome explorer-outcome--success">
                    <CheckCircle2 size={17} />
                    <span>
                      Replay confirmed by the API (HTTP 200); the original
                      payment result was returned.
                    </span>
                  </div>
                )}
                {isConflict && (
                  <div className="explorer-outcome explorer-outcome--error">
                    <AlertCircle size={17} />
                    <span>
                      Conflict: this key was already used with a different
                      payload.
                    </span>
                  </div>
                )}
                {isValidationError && (
                  <div className="explorer-outcome explorer-outcome--error">
                    <AlertCircle size={17} />
                    <span>
                      Validation rejected by the API (HTTP 422). This request
                      was not accepted as a payment operation.
                    </span>
                  </div>
                )}
                {isUnknownOutcome && (
                  <div className="explorer-outcome explorer-outcome--warning">
                    <AlertCircle size={17} />
                    <span>
                      {result.error?.failureKind === "timeout"
                        ? "The request timed out."
                        : "The network connection failed."}{" "}
                      The operation result is unknown. No new key was generated;
                      use “Retry exact request” to safely check using the same
                      key and payload.
                    </span>
                  </div>
                )}
                {result.error &&
                  !isUnknownOutcome &&
                  !isConflict &&
                  !isValidationError && (
                    <div className="explorer-outcome explorer-outcome--error">
                      <AlertCircle size={17} />
                      <span>
                        {result.error.failureKind === "unexpected"
                          ? "The API response could not be interpreted."
                          : `The API returned HTTP ${result.error.status}.`}
                      </span>
                    </div>
                  )}
                {requestId && (
                  <div className="request-id-line">
                    <span>Request ID</span>
                    <code>{requestId}</code>
                    <Link
                      className="text-link text-link--small"
                      to={`/requests/${encodeURIComponent(requestId)}`}
                    >
                      Inspect request
                    </Link>
                  </div>
                )}
                {requestId && requestLog.data && (
                  <div className="explorer-log">
                    <div>
                      <span>Request outcome</span>
                      <StatusBadge status={requestLog.data.outcome} />
                    </div>
                    <div>
                      <span>Idempotency outcome</span>
                      <StatusBadge
                        status={requestLog.data.idempotency_outcome}
                      />
                    </div>
                    {requestLog.data.payment_id && (
                      <div>
                        <span>
                          {isConflict
                            ? "Original payment"
                            : "Associated payment"}
                        </span>
                        <Link
                          className="text-link text-link--small"
                          to={`/payments/${encodeURIComponent(requestLog.data.payment_id)}`}
                        >
                          <ShortId
                            value={requestLog.data.payment_id}
                            prefix={22}
                          />
                        </Link>
                      </div>
                    )}
                  </div>
                )}
                {requestId && requestLog.isError && (
                  <p className="metrics-note">
                    The payment response is available, but its request log could
                    not be loaded. Use “Inspect request” to retry the lookup.
                  </p>
                )}
                {result.error && (
                  <p className="response-error">{result.error.message}</p>
                )}
                <pre className="code-block code-block--response">
                  <code>
                    {JSON.stringify(resultBody, null, 2) ??
                      "No response body was returned."}
                  </code>
                </pre>
              </>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
