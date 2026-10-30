import { Link } from "react-router-dom";

import type { Reliability, RunStatus, TestOutcome } from "../api";

export function SummaryValue({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: TestOutcome;
}) {
  return (
    <div className="summary-value">
      <span className="summary-label">{label}</span>
      <strong className={tone ? `outcome-${tone}` : ""}>{value}</strong>
    </div>
  );
}

export function StatusBadge({ status }: { status: RunStatus | TestOutcome }) {
  return (
    <span className={`status-badge status-${status}`}>
      <span className="status-dot" />
      {status}
    </span>
  );
}

export function ReliabilityBadge({ reliability }: { reliability: Reliability }) {
  const labels: Record<Reliability, string> = {
    stable: "Stable",
    potentially_flaky: "Potentially flaky",
    persistently_failing: "Persistent failure",
    insufficient_data: "Insufficient data",
  };
  const label = labels[reliability];
  return <span className={`reliability-badge reliability-${reliability}`}>{label}</span>;
}

export function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  const page = Math.floor(offset / limit);
  const pages = Math.ceil(total / limit);
  if (pages <= 1) {
    return null;
  }
  return (
    <nav aria-label="Pagination" className="pagination">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <div>
        <button disabled={page === 0} onClick={() => onChange((page - 1) * limit)} type="button">
          <Icon name="chevron-left" />
          Previous
        </button>
        <span className="pagination-page">
          {page + 1} / {pages}
        </span>
        <button
          disabled={page + 1 >= pages}
          onClick={() => onChange((page + 1) * limit)}
          type="button"
        >
          Next
          <Icon name="chevron" />
        </button>
      </div>
    </nav>
  );
}

export function LoadingState({ label, compact = false }: { label: string; compact?: boolean }) {
  return (
    <div aria-busy="true" aria-live="polite" className={`loading-state${compact ? " compact" : ""}`}>
      <span className="loading-pulse" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error-state" role="alert">
      <div>
        <strong>Something went wrong</strong>
        <p>{message}</p>
      </div>
      <button className="secondary-button" onClick={onRetry} type="button">
        Try again
      </button>
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <div aria-hidden="true" className="empty-mark">
        <PulseMark />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

export function NotFound() {
  return (
    <div className="page-container">
      <EmptyState
        title="Page not found"
        description="This TestPulse page does not exist. Return to your project list to continue."
      />
      <Link className="text-link" to="/">
        Go to projects
      </Link>
    </div>
  );
}


export function PulseMark() {
  return (
    <svg aria-hidden="true" className="pulse-mark" fill="none" viewBox="0 0 32 32">
      <path
        d="M3 17h6l3.2-8 5.1 15 3.2-9H29"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.2"
      />
    </svg>
  );
}

export function Icon({
  name,
}: {
  name: "grid" | "branch" | "pulse" | "stability" | "arrow" | "chevron" | "chevron-left" | "external";
}) {
  const common = {
    "aria-hidden": true as const,
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.8,
    viewBox: "0 0 20 20",
  };

  switch (name) {
    case "grid":
      return (
        <svg {...common}>
          <rect height="6" rx="1" width="6" x="3" y="3" />
          <rect height="6" rx="1" width="6" x="11" y="3" />
          <rect height="6" rx="1" width="6" x="3" y="11" />
          <rect height="6" rx="1" width="6" x="11" y="11" />
        </svg>
      );
    case "branch":
      return (
        <svg {...common}>
          <circle cx="6" cy="4" r="2" />
          <circle cx="6" cy="16" r="2" />
          <circle cx="15" cy="7" r="2" />
          <path d="M6 6v8M8 5c4 0 7 0 7 0v.5M8 15h2a5 5 0 0 0 5-5V9" />
        </svg>
      );
    case "pulse":
      return (
        <svg {...common}>
          <path d="M2 10h4l2.2-5 3.6 10 2.4-6H18" />
        </svg>
      );
    case "stability":
      return (
        <svg {...common}>
          <path d="M10 2.5 17 6v4.5c0 3.7-2.7 5.9-7 7-4.3-1.1-7-3.3-7-7V6l7-3.5Z" />
          <path d="m7 10 2 2 4-4" />
        </svg>
      );
    case "arrow":
      return (
        <svg {...common}>
          <path d="M4 10h11M10 5l5 5-5 5" />
        </svg>
      );
    case "chevron":
      return (
        <svg {...common}>
          <path d="m7 4 6 6-6 6" />
        </svg>
      );
    case "chevron-left":
      return (
        <svg {...common}>
          <path d="m13 4-6 6 6 6" />
        </svg>
      );
    case "external":
      return (
        <svg {...common}>
          <path d="M11 4h5v5M16 4 9 11" />
          <path d="M14 11v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4" />
        </svg>
      );
    default:
      return null;
  }
}
