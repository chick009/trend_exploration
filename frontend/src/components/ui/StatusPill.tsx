import { Badge } from "./Badge";

type Props = {
  status?: string | null;
};

function toneForStatus(status: string) {
  switch (status.toLowerCase()) {
    case "completed":
    case "ready":
      return "success" as const;
    case "running":
    case "queued":
    case "processing":
      return "info" as const;
    case "failed":
    case "error":
      return "danger" as const;
    case "warning":
      return "warning" as const;
    default:
      return "neutral" as const;
  }
}

export function StatusPill({ status }: Props) {
  const value = status?.trim() || "idle";
  return <Badge tone={toneForStatus(value)}>{value}</Badge>;
}
