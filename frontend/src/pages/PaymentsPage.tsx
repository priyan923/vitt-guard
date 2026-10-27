import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, CreditCard } from "lucide-react";
import { Link } from "react-router-dom";
import { getPayments } from "../api/client";
import { ShortId } from "../components/Formatting";
import { formatMoney, formatTimestamp } from "../utils/format";
import { Pagination } from "../components/Pagination";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeading,
  RefreshButton,
  StatusBadge,
} from "../components/States";

const PAGE_SIZE = 10;

export function PaymentsPage() {
  const [offset, setOffset] = useState(0);
  const payments = useQuery({
    queryKey: ["payments", PAGE_SIZE, offset],
    queryFn: async () => (await getPayments(PAGE_SIZE, offset)).data,
  });

  return (
    <>
      <PageHeading
        eyebrow="PAYMENT ACTIVITY"
        title="Payments"
        description="Browse simulated payment records stored in your workspace."
        action={
          <RefreshButton
            onClick={() => void payments.refetch()}
            isLoading={payments.isFetching}
          />
        }
      />
      <section className="panel table-panel">
        <div className="panel__heading table-panel__heading">
          <div>
            <h2>All payments</h2>
            <p>Newest payment records first</p>
          </div>
          {payments.data && (
            <span className="count-pill">{payments.data.total} records</span>
          )}
        </div>
        {payments.isPending ? (
          <LoadingState label="Loading payments" />
        ) : payments.isError ? (
          <ErrorState
            message={payments.error.message}
            onRetry={() => void payments.refetch()}
          />
        ) : payments.data.items.length === 0 ? (
          <EmptyState
            title="No payments found"
            description="Create a simulated payment in API Explorer to see a record here."
            icon={<CreditCard size={20} />}
          />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Payment</th>
                    <th scope="col">Amount</th>
                    <th scope="col">Status</th>
                    <th scope="col">Created</th>
                    <th scope="col">
                      <span className="sr-only">Open payment</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {payments.data.items.map((payment) => (
                    <tr key={payment.payment_id}>
                      <td>
                        <Link
                          className="table-primary-link"
                          to={`/payments/${payment.payment_id}`}
                        >
                          <ShortId value={payment.payment_id} />
                        </Link>
                      </td>
                      <td className="amount-cell">
                        {formatMoney(payment.amount_minor, payment.currency)}
                      </td>
                      <td>
                        <StatusBadge status={payment.status} />
                      </td>
                      <td className="muted-cell">
                        {formatTimestamp(payment.created_at)}
                      </td>
                      <td>
                        <Link
                          className="row-open-link"
                          to={`/payments/${payment.payment_id}`}
                          aria-label={`View payment ${payment.payment_id}`}
                        >
                          <ArrowUpRight size={16} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              total={payments.data.total}
              limit={payments.data.limit}
              offset={payments.data.offset}
              onChange={setOffset}
            />
          </>
        )}
      </section>
      <p className="metrics-note">
        Pagination is applied by the API. Search and filters are not available
        on this endpoint.
      </p>
    </>
  );
}
