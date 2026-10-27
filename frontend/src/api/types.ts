export type PaymentStatus = "pending" | "succeeded" | "failed";
export type PaymentCurrency = "USD" | "EUR" | "GBP";

export interface Payment {
  payment_id: string;
  amount_minor: number;
  currency: PaymentCurrency;
  status: PaymentStatus;
  created_at: string;
  updated_at: string;
}

export interface PaymentList {
  items: Payment[];
  total: number;
  limit: number;
  offset: number;
}

export interface RequestLog {
  request_id: string;
  request_method: string;
  api_path: string;
  request_at: string;
  http_status_code: number;
  processing_duration_ms: number;
  idempotency_outcome: string;
  outcome: string;
  payment_id: string | null;
  sanitized_error_code: string | null;
}

export interface RequestLogList {
  items: RequestLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface MetricsSummary {
  period_start: string | null;
  period_end: string | null;
  total_payments: number;
  payments_by_status: Record<PaymentStatus, number>;
  total_requests: number;
  payment_attempts: number;
  successful_requests: number;
  conflicts: number;
  idempotency_replays: number;
}

export interface CreatePaymentPayload {
  amount_minor: number;
  currency: PaymentCurrency;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
  request_id: string;
}

export interface ApiResult<T> {
  data: T;
  status: number;
  requestId: string | null;
}
