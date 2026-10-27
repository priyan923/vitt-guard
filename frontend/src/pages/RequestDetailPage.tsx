import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clock3, FileSearch } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getRequest } from "../api/client";
import { ShortId } from "../components/Formatting";
import { formatTimestamp } from "../utils/format";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeading,
  StatusBadge,
} from "../components/States";

export function RequestDetailPage() {
  const { requestId = "" } = useParams();
  const request = useQuery({
    queryKey: ["request", requestId],
    queryFn: async () => (await getRequest(requestId)).data,
    enabled: Boolean(requestId),
  });

  return (
    <>
      <Link className="back-link" to="/requests">
        <ArrowLeft size={16} /> Request inspector
      </Link>
      {request.isPending ? (
        <LoadingState label="Loading request" />
      ) : request.isError ? (
        request.error instanceof ApiError && request.error.status === 404 ? (
          <section className="panel">
            <EmptyState
              title="Request not found"
              description="This request ID is not available in the current workspace."
              icon={<FileSearch size={20} />}
            />
          </section>
        ) : (
          <ErrorState
            message={request.error.message}
            onRetry={() => void request.refetch()}
          />
        )
      ) : (
        <>
          <PageHeading
            eyebrow="REQUEST DETAILS"
            title="Request attempt"
            description={`${request.data.request_method} ${request.data.api_path}`}
            action={<StatusBadge status={request.data.outcome} />}
          />
          <section className="panel detail-panel">
            <div className="request-code-line">
              <span
                className={`http-code ${request.data.http_status_code >= 400 ? "http-code--error" : ""}`}
              >
                {request.data.http_status_code}
              </span>
              <span>{request.data.request_method}</span>
              <code>{request.data.api_path}</code>
            </div>
            <div className="detail-grid">
              <Field label="Request ID">
                <ShortId value={request.data.request_id} prefix={24} />
              </Field>
              <Field label="Timestamp">
                <Clock3 size={14} />
                {formatTimestamp(request.data.request_at)}
              </Field>
              <Field label="Duration">
                {request.data.processing_duration_ms} ms
              </Field>
              <Field label="Idempotency outcome">
                <StatusBadge status={request.data.idempotency_outcome} />
              </Field>
              <Field label="Outcome">
                <StatusBadge status={request.data.outcome} />
              </Field>
              <Field label="Payment">
                {request.data.payment_id ? (
                  <Link
                    className="text-link text-link--small"
                    to={`/payments/${request.data.payment_id}`}
                  >
                    <ShortId value={request.data.payment_id} prefix={20} />
                  </Link>
                ) : (
                  "—"
                )}
              </Field>
              <Field label="Sanitized error">
                {request.data.sanitized_error_code ?? "—"}
              </Field>
            </div>
          </section>
          <p className="metrics-note">
            Request headers and raw request/response bodies are intentionally
            not stored in request logs.
          </p>
        </>
      )}
    </>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="detail-field">
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  );
}
