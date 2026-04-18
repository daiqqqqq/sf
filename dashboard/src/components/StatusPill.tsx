type StatusPillProps = {
  status: string;
};

export function StatusPill({ status }: StatusPillProps) {
  const normalized = status.toLowerCase();
  const tone =
    normalized.includes("healthy") || normalized.includes("indexed") || normalized.includes("success")
      ? "success"
      : normalized.includes("running") || normalized.includes("pending") || normalized.includes("queued")
        ? "warning"
        : normalized.includes("failed") || normalized.includes("unhealthy")
          ? "danger"
          : "neutral";

  return <span className={`status-pill ${tone}`}>{status}</span>;
}

