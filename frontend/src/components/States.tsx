import { AlertCircle, Check, LoaderCircle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function LoadingState({ label = "Loading data" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <LoaderCircle className="spin" size={21} aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <AlertCircle size={21} aria-hidden="true" />
      <div className="state-copy">
        <strong>We couldn’t load this data</strong>
        <span>{message}</span>
      </div>
      <button
        className="button button--secondary"
        onClick={onRetry}
        type="button"
      >
        <RefreshCw size={15} aria-hidden="true" />
        Retry
      </button>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon ?? <Check size={20} />}</div>
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const tone =
    normalized === "succeeded" ||
    normalized === "success" ||
    normalized === "payment_created" ||
    normalized === "idempotency_replay"
      ? "positive"
      : normalized === "failed" ||
          normalized === "payload_conflict" ||
          normalized === "validation_error" ||
          normalized === "database_error"
        ? "negative"
        : normalized === "pending" || normalized === "handled_error"
          ? "warning"
          : "neutral";

  return (
    <span className={`badge badge--${tone}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function RefreshButton({
  onClick,
  isLoading,
}: {
  onClick: () => void;
  isLoading: boolean;
}) {
  return (
    <button
      className="button button--secondary"
      type="button"
      onClick={onClick}
      disabled={isLoading}
    >
      <RefreshCw
        className={isLoading ? "spin" : ""}
        size={16}
        aria-hidden="true"
      />
      Refresh
    </button>
  );
}
