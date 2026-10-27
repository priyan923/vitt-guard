import type {
  ApiErrorBody,
  ApiResult,
  CreatePaymentPayload,
  MetricsSummary,
  Payment,
  PaymentList,
  RequestLog,
  RequestLogList,
} from "./types";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(
  /\/$/,
  "",
);

let authorizationHeader: string | null = null;
let authenticatedUsername: string | null = null;

export function setApiCredentials(username: string, password: string): void {
  const credentials = new TextEncoder().encode(`${username}:${password}`);
  const binary = Array.from(credentials, (value) =>
    String.fromCharCode(value),
  ).join("");
  authorizationHeader = `Basic ${btoa(binary)}`;
  authenticatedUsername = username;
}

export function clearApiCredentials(): void {
  authorizationHeader = null;
  authenticatedUsername = null;
}

export function getAuthenticatedUsername(): string | null {
  return authenticatedUsername;
}

export interface AuthStatus {
  authentication_required: boolean;
}

export type ApiFailureKind = "http" | "network" | "timeout" | "unexpected";

export class ApiError extends Error {
  readonly status: number;
  readonly requestId: string | null;
  readonly body: unknown;
  readonly failureKind: ApiFailureKind;

  constructor(
    message: string,
    status: number,
    requestId: string | null,
    body: unknown,
    failureKind: ApiFailureKind = "http",
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
    this.body = body;
    this.failureKind = failureKind;
  }
}

const REQUEST_TIMEOUT_MS = 15_000;

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    REQUEST_TIMEOUT_MS,
  );
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(authorizationHeader
          ? { Authorization: authorizationHeader }
          : {}),
        ...init?.headers,
      },
    });

    const requestId = response.headers.get("X-Request-ID");
    const responseText = await response.text();
    let body: unknown = null;
    if (responseText) {
      try {
        body = JSON.parse(responseText);
      } catch {
        throw new ApiError(
          "The API returned an unreadable response body.",
          response.status,
          requestId,
          null,
          "unexpected",
        );
      }
    }
    if (!response.ok) {
      const errorBody = body as Partial<ApiErrorBody> | null;
      const message =
        errorBody?.error?.message ??
        `The API returned an unexpected response (${response.status}).`;
      throw new ApiError(message, response.status, requestId, body);
    }

    export function getAuthStatus(): Promise<ApiResult<AuthStatus>> {
      return request("/auth/status");
    }

    export async function verifyCredentials(
      username: string,
      password: string,
    ): Promise<ApiResult<{ status: "authenticated" }>> {
      setApiCredentials(username, password);
      try {
        return await request("/auth/verify");
      } catch (error) {
        clearApiCredentials();
        throw error;
      }
    }

    return { data: body as T, status: response.status, requestId };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const timedOut = controller.signal.aborted;
    throw new ApiError(
      timedOut
        ? "The request timed out. Its result is unknown; retry the exact request with the same key."
        : "The API could not be reached. Its result is unknown; retry the exact request with the same key.",
      0,
      null,
      null,
      timedOut ? "timeout" : "network",
    );
  } finally {
    window.clearTimeout(timeout);
  }
}

export function getMetrics(): Promise<ApiResult<MetricsSummary>> {
  return request("/api/v1/metrics/summary");
}

export function getPayments(
  limit: number,
  offset: number,
): Promise<ApiResult<PaymentList>> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return request(`/api/v1/payments?${query}`);
}

export function getPayment(paymentId: string): Promise<ApiResult<Payment>> {
  return request(`/api/v1/payments/${encodeURIComponent(paymentId)}`);
}

export function getRequests(
  limit: number,
  offset: number,
): Promise<ApiResult<RequestLogList>> {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return request(`/api/v1/requests?${query}`);
}

export function getRequest(requestId: string): Promise<ApiResult<RequestLog>> {
  return request(`/api/v1/requests/${encodeURIComponent(requestId)}`);
}

export function createPayment(
  payload: CreatePaymentPayload,
  idempotencyKey: string,
  scope = "default",
): Promise<ApiResult<Payment>> {
  return request("/api/v1/payments", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
      "Idempotency-Scope": scope,
    },
    body: JSON.stringify(payload),
  });
}
