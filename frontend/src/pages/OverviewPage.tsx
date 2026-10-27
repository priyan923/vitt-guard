import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  CreditCard,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { getMetrics } from "../api/client";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeading,
  RefreshButton,
} from "../components/States";

export function OverviewPage() {
  const metrics = useQuery({
    queryKey: ["metrics"],
    queryFn: async () => (await getMetrics()).data,
  });
  const data = metrics.data;

  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE OVERVIEW"
        title="Good to see you."
        description="A live look at your simulated payment environment."
        action={
          <RefreshButton
            onClick={() => void metrics.refetch()}
            isLoading={metrics.isFetching}
          />
        }
      />
      {metrics.isPending ? (
        <LoadingState label="Loading workspace metrics" />
      ) : metrics.isError ? (
        <ErrorState
          message={metrics.error.message}
          onRetry={() => void metrics.refetch()}
        />
      ) : data ? (
        <>
          <div className="metric-grid">
            <MetricCard
              label="Total payments"
              value={data.total_payments.toLocaleString()}
              detail={`${data.payments_by_status.pending} pending`}
              icon={<CreditCard size={18} />}
              tone="navy"
            />
            <MetricCard
              label="Request attempts"
              value={data.total_requests.toLocaleString()}
              detail={`${data.successful_requests} successful responses`}
              icon={<Activity size={18} />}
              tone="green"
            />
            <MetricCard
              label="Idempotency replays"
              value={data.idempotency_replays.toLocaleString()}
              detail="Original result returned"
              icon={<RotateCcw size={18} />}
              tone="blue"
            />
            <MetricCard
              label="Payload conflicts"
              value={data.conflicts.toLocaleString()}
              detail="HTTP 409 responses"
              icon={<ShieldCheck size={18} />}
              tone="amber"
            />
          </div>

          <section className="panel overview-status">
            <div className="panel__heading">
              <div>
                <h2>Payment status</h2>
                <p>Payment records grouped by their current status</p>
              </div>
              <span className="data-source">
                <i /> Live database
              </span>
            </div>
            {data.total_payments === 0 ? (
              <EmptyState
                title="No payments yet"
                description="When you create a simulated payment, its status will appear here."
                icon={<CreditCard size={20} />}
              />
            ) : (
              <div className="status-breakdown">
                {Object.entries(data.payments_by_status).map(
                  ([status, count]) => (
                    <div className="status-breakdown__row" key={status}>
                      <span className={`status-dot status-dot--${status}`} />
                      <span className="status-breakdown__label">{status}</span>
                      <div className="status-track">
                        <span
                          className={`status-track__fill status-track__fill--${status}`}
                          style={{
                            width: `${data.total_payments ? (count / data.total_payments) * 100 : 0}%`,
                          }}
                        />
                      </div>
                      <strong>{count.toLocaleString()}</strong>
                    </div>
                  ),
                )}
              </div>
            )}
          </section>

          <section className="panel trend-panel">
            <div className="panel__heading">
              <div>
                <h2>Activity over time</h2>
                <p>Payment and request volume</p>
              </div>
              <span className="period-label">Lifetime summary</span>
            </div>
            <EmptyState
              title="Time-series data isn’t available yet"
              description="The API currently provides aggregate totals, not daily or hourly data. This space will show a trend when a real time-series endpoint is available."
              icon={<Activity size={20} />}
            />
          </section>
          <p className="metrics-note">
            Metrics are aggregated from persisted records. Request attempts and
            payment records are counted separately.
          </p>
        </>
      ) : null}
    </>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
  tone: string;
}) {
  return (
    <section className="metric-card">
      <div className="metric-card__top">
        <span>{label}</span>
        <span className={`metric-card__icon metric-card__icon--${tone}`}>
          {icon}
        </span>
      </div>
      <strong className="metric-card__value">{value}</strong>
      <span className="metric-card__detail">
        {tone === "green" ? (
          <ArrowUpRight size={14} />
        ) : tone === "amber" ? (
          <ArrowDownRight size={14} />
        ) : null}
        {detail}
      </span>
    </section>
  );
}
