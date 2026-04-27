type StatusPillProps = {
  status: string;
};

export function StatusPill({ status }: StatusPillProps) {
  const normalized = status.toLowerCase();
  const tone =
    normalized.includes("healthy") || normalized.includes("indexed") || normalized.includes("success") || normalized.includes("enabled")
      ? "success"
      : normalized.includes("running") ||
          normalized.includes("pending") ||
          normalized.includes("queued") ||
          normalized.includes("warning") ||
          normalized.includes("degraded")
        ? "warning"
        : normalized.includes("failed") ||
            normalized.includes("unhealthy") ||
            normalized.includes("disabled") ||
            normalized.includes("unreachable")
          ? "danger"
          : "neutral";

  return <span className={`status-pill ${tone}`}>{status}</span>;
}

