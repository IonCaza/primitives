"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Circle,
  Clock,
  Loader2,
  PanelRightClose,
  Ban,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTaskBoard } from "@/components/chat-runtime";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

interface TaskItemData {
  id: string;
  subject: string;
  description: string | null;
  status: string;
  owner_agent_slug: string | null;
  blocked_by: string[];
  blocks: string[];
  created_at: string;
}

const STATUS_ORDER = [
  "in_progress",
  "pending",
  "blocked",
  "completed",
  "cancelled",
] as const;

const STATUS_META: Record<
  string,
  { label: string; icon: typeof Circle; className: string }
> = {
  pending: { label: "Pending", icon: Circle, className: "text-muted-foreground" },
  in_progress: { label: "In Progress", icon: Loader2, className: "text-blue-500 animate-spin" },
  completed: { label: "Completed", icon: CheckCircle2, className: "text-emerald-500" },
  blocked: { label: "Blocked", icon: AlertTriangle, className: "text-amber-500" },
  cancelled: { label: "Cancelled", icon: Ban, className: "text-muted-foreground/60" },
};

function TaskCard({ task }: { task: TaskItemData }) {
  const meta = STATUS_META[task.status] ?? STATUS_META.pending;
  const Icon = meta.icon;

  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border px-3 py-2",
        task.status === "completed" && "opacity-60",
        task.status === "cancelled" && "opacity-40",
      )}
    >
      <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", meta.className)} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[10px] font-mono text-muted-foreground">
            {task.id}
          </span>
          <span
            className={cn(
              "text-xs font-medium leading-snug",
              task.status === "completed" && "line-through",
            )}
          >
            {task.subject}
          </span>
        </div>
        {task.blocked_by.length > 0 && task.status !== "completed" && (
          <p className="mt-0.5 text-[10px] text-amber-600 dark:text-amber-400">
            blocked by {task.blocked_by.join(", ")}
          </p>
        )}
        {task.owner_agent_slug && (
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            {task.owner_agent_slug}
          </p>
        )}
      </div>
    </div>
  );
}

function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-emerald-500 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] tabular-nums text-muted-foreground">
        {done}/{total}
      </span>
    </div>
  );
}

interface TaskBoardPanelProps {
  onCollapse?: () => void;
}

export function TaskBoardPanel({ onCollapse }: TaskBoardPanelProps) {
  const { sessionId, updateCounter } = useTaskBoard();
  const [tasks, setTasks] = useState<TaskItemData[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setTasks([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .getSessionTasks(sessionId)
      .then((data) => {
        if (!cancelled) setTasks(data);
      })
      .catch(() => {
        if (!cancelled) setTasks([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, updateCounter]);

  const done = tasks.filter((t) => t.status === "completed").length;
  const total = tasks.length;

  const grouped = STATUS_ORDER.map((status) => ({
    status,
    tasks: tasks.filter((t) => t.status === status),
  })).filter((g) => g.tasks.length > 0);

  return (
    <div className="flex h-full min-h-0 flex-col bg-muted/30 overflow-hidden">
      <div className="flex h-10 shrink-0 items-center justify-between border-b px-3">
        <div className="flex items-center gap-2">
          <Clock className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold text-muted-foreground">
            Tasks
          </span>
        </div>
        {onCollapse && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={onCollapse}
            title="Collapse panel"
          >
            <PanelRightClose className="h-3 w-3" />
          </Button>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2">
        {loading && tasks.length === 0 ? (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-xs text-muted-foreground italic">
              No tasks yet
            </p>
          </div>
        ) : (
          <>
            <div className="px-1">
              <ProgressBar done={done} total={total} />
            </div>
            {grouped.map(({ status, tasks: groupTasks }) => (
              <div key={status} className="flex flex-col gap-1">
                <span className="px-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {STATUS_META[status]?.label ?? status} ({groupTasks.length})
                </span>
                {groupTasks.map((task) => (
                  <TaskCard key={task.id} task={task} />
                ))}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
