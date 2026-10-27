import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clock3, CreditCard, Info, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getPayment } from "../api/client";
import { ShortId } from "../components/Formatting";
import { formatMoney, formatTimestamp } from "../utils/format";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeading,
  StatusBadge,
} from "../components/States";

export function PaymentDetailPage() {
  const { paymentId = "" } = useParams();
  const payment = useQuery({
    queryKey: ["payment", paymentId],
    queryFn: async () => (await getPayment(paymentId)).data,
    enabled: Boolean(paymentId),
  });

  return (
    <>
      <Link className="back-link" to="/payments">
        <ArrowLeft size={16} /> All payments
      </Link>
      {payment.isPending ? (
        <LoadingState label="Loading payment" />
      ) : payment.isError ? (
        payment.error instanceof ApiError && payment.error.status === 404 ? (
          <section className="panel">
            <EmptyState
              title="Payment not found"
              description="This payment ID does not exist in the current workspace."
              icon={<CreditCard size={20} />}
            />
          </section>
        ) : (
          <ErrorState
            message={payment.error.message}
            onRetry={() => void payment.refetch()}
          />
        )
      ) : (
        <>
          <PageHeading
            eyebrow="PAYMENT DETAILS"
            title="Payment"
            description="A persisted simulated payment record. No funds were moved."
            action={<StatusBadge status={payment.data.status} />}
          />
          <section className="panel detail-panel">
            <div className="detail-amount">
              <span>Payment amount</span>
              <strong>
                {formatMoney(payment.data.amount_minor, payment.data.currency)}
              </strong>
              <span className="currency-caption">
                {payment.data.amount_minor.toLocaleString()} minor units ·{" "}
                {payment.data.currency}
              </span>
            </div>
            <div className="detail-grid">
              <DetailField label="Payment ID">
                <ShortId value={payment.data.payment_id} prefix={20} />
              </DetailField>
              <DetailField label="Status">
                <StatusBadge status={payment.data.status} />
              </DetailField>
              <DetailField label="Created">
                <Clock3 size={14} />
                {formatTimestamp(payment.data.created_at)}
              </DetailField>
              <DetailField label="Last updated">
                <Clock3 size={14} />
                {formatTimestamp(payment.data.updated_at)}
              </DetailField>
              <DetailField label="Currency">
                {payment.data.currency}
              </DetailField>
              <DetailField label="Record type">
                <span className="simulation-label">
                  <ShieldCheck size={14} /> Simulation
                </span>
              </DetailField>
            </div>
          </section>
          <section className="panel related-panel">
            <div className="panel__heading">
              <div>
                <h2>Related request history</h2>
                <p>Request attempts associated with this payment</p>
              </div>
            </div>
            <EmptyState
              title="Payment-specific history isn’t available"
              description="The request API does not currently support filtering by payment. Browse the Request inspector for all recorded attempts."
              icon={<Info size={20} />}
            />
            <Link className="text-link" to="/requests">
              Open Request inspector{" "}
              <ArrowLeft className="arrow-right" size={15} />
            </Link>
          </section>
        </>
      )}
    </>
  );
}

function DetailField({
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
