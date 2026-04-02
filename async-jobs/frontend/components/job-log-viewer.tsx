"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Terminal, Circle, ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface LogEntry {
  ts: number;
  phase: string;
  level: string;
  message: string;
}

/**
 * Phase-to-color mapping. Override or extend this with your domain phases.
 * The viewer gracefully falls back to bg-zinc-600 for unknown phases.
 */
const PHASE_COLORS: Record<string, string> = {
  init: "bg-slate-500",
  fetch: "bg-blue-500",
  process: "bg-violet-500",
  validate: "bg-cyan-500",
  transform: "bg-amber-500",
  persist: "bg-teal-500",
  finalize: "bg-emerald-500",
  complete: "bg-green-500",
  error: "bg-red-500",
  cancelled: "bg-yellow-600",
};

const LEVEL_CLASSES: Record<string, string> = {
  info: "text-zinc-300",
  warning: "text-amber-400",
  error: "text-red-400",
};

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface JobLogViewerProps {
  jobId: string;
  logUrl?: string;
  compact?: boolean;
  title?: string;
  onDone?: () => void;
  phaseColors?: Record<string, string>;
}

export function JobLogViewer({
  jobId,
  logUrl,
  compact = false,
  title = "Job Logs",
  onDone,
  phaseColors,
}: JobLogViewerProps) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [live, setLive] = useState(true);
  const [expanded, setExpanded] = useState(!compact);
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  const colors = { ...PHASE_COLORS, ...phaseColors };

  const connect = useCallback(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    const tokenSuffix = token ? `?token=${encodeURIComponent(token)}` : "";
    const url = logUrl
      ? `${logUrl}${tokenSuffix}`
      : `/api/jobs/${jobId}/logs${tokenSuffix}`;

    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("log", (ev) => {
      try {
        const entry: LogEntry = JSON.parse(ev.data);
        setEntries((prev) => [...prev, entry]);
      } catch { /* ignore parse errors */ }
    });

    es.addEventListener("done", () => {
      setLive(false);
      es.close();
      onDone?.();
    });

    es.onerror = () => {
      setLive(false);
      es.close();
    };

    return es;
  }, [jobId, logUrl, onDone]);

  useEffect(() => {
    const es = connect();
    return () => {
      es.close();
    };
  }, [connect]);

  useEffect(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [entries]);

  if (compact && !expanded) {
    const lastEntry = entries[entries.length - 1];
    return (
      <button
        onClick={() => setExpanded(true)}
        className="flex items-center gap-2 rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800 transition-colors w-full"
      >
        <Terminal className="h-3 w-3 shrink-0" />
        {live && <Circle className="h-2 w-2 fill-green-500 text-green-500 animate-pulse shrink-0" />}
        <span className="truncate">{lastEntry?.message || "Waiting for logs..."}</span>
        <ChevronDown className="h-3 w-3 ml-auto shrink-0" />
      </button>
    );
  }

  const maxH = compact ? "max-h-40" : "max-h-72";

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-950 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-900 border-b border-zinc-800">
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <Terminal className="h-3.5 w-3.5" />
          <span className="font-medium">{title}</span>
          {live && (
            <span className="flex items-center gap-1 text-green-400">
              <Circle className="h-1.5 w-1.5 fill-current animate-pulse" />
              Live
            </span>
          )}
          {!live && entries.length > 0 && (
            <span className="text-zinc-500">Finished</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {compact && (
            <Button variant="ghost" size="sm" className="h-5 w-5 p-0 text-zinc-500 hover:text-zinc-300" onClick={() => setExpanded(false)}>
              <ChevronUp className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>
      <div ref={containerRef} className={cn("overflow-y-auto px-3 py-2 font-mono text-xs leading-relaxed", maxH)}>
        {entries.length === 0 && (
          <div className="text-zinc-600 py-4 text-center">Waiting for logs...</div>
        )}
        {entries.map((entry, i) => (
          <div key={i} className="flex items-start gap-2 py-0.5">
            <span className="text-zinc-600 shrink-0 w-[5.5rem]">{formatTime(entry.ts)}</span>
            <span className={cn("shrink-0 mt-0.5 rounded px-1.5 py-0 text-[10px] font-semibold text-white uppercase tracking-wider", colors[entry.phase] || "bg-zinc-600")}>
              {entry.phase}
            </span>
            <span className={cn("break-all", LEVEL_CLASSES[entry.level] || "text-zinc-300")}>
              {entry.message}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}


interface ViewLogsButtonProps {
  jobId: string;
  logUrl?: string;
}

export function ViewLogsButton({ jobId, logUrl }: ViewLogsButtonProps) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <Button variant="ghost" size="sm" className="h-6 px-2 text-xs gap-1" onClick={() => setOpen(true)}>
        <Terminal className="h-3 w-3" /> Logs
      </Button>
    );
  }

  return <JobLogViewer jobId={jobId} logUrl={logUrl} />;
}
