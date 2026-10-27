import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Activity } from "lucide-react";
import { Link } from "react-router-dom";
import { getRequests } from "../api/client";
import { ShortId } from "../components/Formatting";
import { formatTimestamp } from "../utils/format";
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

export function RequestsPage() {
  const [offset, setOffset] = useState(0);
  const requests = useQuery({
    queryKey: ["requests", PAGE_SIZE, offset],
    queryFn: async () => (await getRequests(PAGE_SIZE, offset)).data,
  });

  return (
    <>
      <PageHeading
        eyebrow="OBSERVABILITY"
        title="Request inspector"
        description="Inspect persisted API attempts, outcomes, and payment associations."
        action={
          <RefreshButton
            onClick={() => void requests.refetch()}
            isLoading={requests.isFetching}
          />
        }
      />
      <section className="panel table-panel">
        <div className="panel__heading table-panel__heading">
          <div>
            <h2>Recent requests</h2>
            <p>Newest requests first</p>
          </div>
          {requests.data && (
            <span className="count-pill">{requests.data.total} requests</span>
          )}
        </div>
        {requests.isPending ? (
          <LoadingState label="Loading request logs" />
        ) : requests.isError ? (
          <ErrorState
            message={requests.error.message}
            onRetry={() => void requests.refetch()}
          />
        ) : requests.data.items.length === 0 ? (
          <EmptyState
            title="No request attempts yet"
            description="Requests handled by the API will be recorded here."
            icon={<Activity size={20} />}
          />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Request</th>
                    <th scope="col">Route</th>
                    <th scope="col">Status</th>
                    <th scope="col">Duration</th>
                    <th scope="col">Outcome</th>
                    <th scope="col">Payment</th>
                    <th scope="col">
                      <span className="sr-only">Open request</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {requests.data.items.map((entry) => (
                    <tr key={entry.request_id}>
                      <td>
                        <Link
                          className="table-primary-link"
                          to={`/requests/${entry.request_id}`}
                        >
                          <ShortId value={entry.request_id} />
                        </Link>
                        <span className="table-subline">
                          {entry.request_method} ·{" "}
                          {formatTimestamp(entry.request_at)}
                        </span>
                      </td>
                      <td>
                        <span className="route-cell">{entry.api_path}</span>
                      </td>
                      <td>
                        <span
                          className={`http-code ${entry.http_status_code >= 400 ? "http-code--error" : ""}`}
                        >
                          {entry.http_status_code}
                        </span>
                      </td>
                      <td className="muted-cell">
                        {entry.processing_duration_ms} ms
                      </td>
                      <td>
                        <StatusBadge status={entry.outcome} />
                      </td>
                      <td>
                        {entry.payment_id ? (
                          <Link
                            className="text-link text-link--small"
                            to={`/payments/${entry.payment_id}`}
                          >
                            <ShortId value={entry.payment_id} />
                          </Link>
                        ) : (
                          <span className="muted-cell">—</span>
                        )}
                      </td>
                      <td>
                        <Link
                          className="row-open-link"
                          to={`/requests/${entry.request_id}`}
                          aria-label={`View request ${entry.request_id}`}
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
              total={requests.data.total}
              limit={requests.data.limit}
              offset={requests.data.offset}
              onChange={setOffset}
            />
          </>
        )}
      </section>
      <p className="metrics-note">
        Request logs omit sensitive headers, credentials, query strings, and raw
        bodies.
      </p>
    </>
  );
}
