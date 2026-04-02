import { Badge } from "@/components/ui/badge";
import { Circle, CheckCircle, XCircle, Ban, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type JobStatusValue = "queued" | "running" | "completed" | "failed" | "cancelled";

const STATUS_CONFIG: Record<JobStatusValue, { icon: React.ElementType; variant: string; className: string }> = {
  queued: { icon: Circle, variant: "secondary", className: "text-zinc-500" },
  running: { icon: Loader2, variant: "default", className: "text-blue-500 animate-spin" },
  completed: { icon: CheckCircle, variant: "default", className: "text-green-500" },
  failed: { icon: XCircle, variant: "destructive", className: "text-red-500" },
  cancelled: { icon: Ban, variant: "secondary", className: "text-yellow-600" },
};

interface JobStatusBadgeProps {
  status: string;
  className?: string;
}

export function JobStatusBadge({ status, className }: JobStatusBadgeProps) {
  const config = STATUS_CONFIG[status as JobStatusValue] ?? STATUS_CONFIG.queued;
  const Icon = config.icon;

  return (
    <Badge variant={config.variant as "default" | "secondary" | "destructive"} className={cn("gap-1 capitalize", className)}>
      <Icon className={cn("h-3 w-3", config.className)} />
      {status}
    </Badge>
  );
}
