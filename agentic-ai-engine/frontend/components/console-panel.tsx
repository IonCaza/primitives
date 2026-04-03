"use client";

import { useEffect, useRef, useState } from "react";
import {
  PanelRightClose,
  Loader2,
  CheckCircle2,
  Wrench,
  Brain,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  MessageSquare,
  Terminal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  useChildAgentActivity,
  type ConsoleGroup,
  type LiveConsoleEntry,
} from "@/components/chat-runtime";
import type { ConsoleEntryRecord } from "@/lib/types";
import { cn } from "@/lib/utils";

function PromptHeader({ text }: { text: string }) {
  const truncated = text.length > 120 ? text.slice(0, 120) + "..." : text;
  return (
    <div className="flex items-start gap-2 rounded-md bg-muted/50 px-3 py-2">
      <MessageSquare className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
      <p className="text-xs text-muted-foreground leading-snug line-clamp-2">
        {truncated}
      </p>
    </div>
  );
}

function formatDuration(startedAt: string, finishedAt: string | null | undefined): string {
  if (!finishedAt) return "...";
  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function isErrorResult(result: string | null | undefined): boolean {
  if (!result) return false;
  const lower = result.toLowerCase();
  return lower.includes("error") || lower.includes("traceback") || lower.includes("exception");
}

function JsonBlock({ data, maxLines = 8 }: { data: unknown; maxLines?: number }) {
  const [expanded, setExpanded] = useState(false);
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  const lines = text.split("\n");
  const needsTruncation = lines.length > maxLines;
  const display = expanded || !needsTruncation ? text : lines.slice(0, maxLines).join("\n") + "\n...";

  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded bg-muted/60 px-2 py-1.5 text-[10px] leading-snug font-mono whitespace-pre-wrap break-all">
        {display}
      </pre>
      {needsTruncation && (
        <button
          type="button"
          className="mt-0.5 text-[10px] text-primary/70 hover:text-primary underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Collapse" : `Show all (${lines.length} lines)`}
        </button>
      )}
    </div>
  );
}

function ToolCallCard({
  toolName,
  toolArgs,
  toolResult,
  done,
  startedAt,
  finishedAt,
}: {
  toolName: string;
  toolArgs?: Record<string, unknown> | null;
  toolResult?: string | null;
  done: boolean;
  startedAt: string;
  finishedAt?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const hasError = isErrorResult(toolResult);

  return (
    <div
      className={cn(
        "rounded-lg border text-card-foreground",
        hasError ? "border-destructive/40 bg-destructive/5" : "bg-card",
      )}
    >
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
        )}
        <Wrench className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="truncate text-xs font-semibold font-mono">{toolName}</span>
        <span className="ml-auto flex items-center gap-1.5">
          {done && finishedAt && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 font-normal">
              {formatDuration(startedAt, finishedAt)}
            </Badge>
          )}
          {hasError ? (
            <AlertCircle className="h-3 w-3 text-destructive" />
          ) : done ? (
            <CheckCircle2 className="h-3 w-3 text-emerald-500" />
          ) : (
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
          )}
        </span>
      </button>

      {open && (
        <div className="border-t px-3 py-2 space-y-2">
          {toolArgs && Object.keys(toolArgs).length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground mb-0.5 uppercase tracking-wider">Arguments</p>
              <JsonBlock data={toolArgs} />
            </div>
          )}
          {toolResult !== undefined && toolResult !== null && (
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground mb-0.5 uppercase tracking-wider">Result</p>
              <JsonBlock data={toolResult} maxLines={12} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ThinkingBlock({
  content,
  done,
}: {
  content: string;
  done: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && !done) {
      el.scrollTop = el.scrollHeight;
    }
  }, [content, done]);

  const maxLen = 300;
  const needsTruncation = done && content.length > maxLen;
  const display = expanded || !needsTruncation ? content : content.slice(0, maxLen) + "...";

  return (
    <div className="rounded-lg border border-dashed border-muted-foreground/20 bg-muted/20">
      <div className="flex items-center gap-2 px-3 py-1.5">
        <Brain className="h-3 w-3 shrink-0 text-violet-400" />
        <span className="text-xs font-semibold text-violet-400">Thinking</span>
        {!done && <Loader2 className="ml-auto h-3 w-3 animate-spin text-muted-foreground" />}
      </div>
      <div
        ref={scrollRef}
        className={cn("px-3 pb-2 overflow-y-auto", !done && "max-h-48")}
      >
        <p className="text-[11px] leading-relaxed text-muted-foreground italic whitespace-pre-wrap break-words">
          {display}
        </p>
        {needsTruncation && (
          <button
            type="button"
            className="mt-0.5 text-[10px] text-primary/70 hover:text-primary underline"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Collapse" : "Show full thinking"}
          </button>
        )}
      </div>
    </div>
  );
}

function ConsoleGroupSection({ group }: { group: ConsoleGroup }) {
  return (
    <div className="flex flex-col gap-1.5">
      <PromptHeader text={group.triggerContent} />
      {group.entries.map((entry, idx) =>
        entry.entry_type === "tool_call" ? (
          <ToolCallCard
            key={entry.id ?? idx}
            toolName={entry.tool_name ?? "unknown"}
            toolArgs={entry.tool_args}
            toolResult={entry.tool_result}
            done
            startedAt={entry.started_at}
            finishedAt={entry.finished_at}
          />
        ) : (
          <ThinkingBlock
            key={entry.id ?? idx}
            content={entry.thinking_content ?? ""}
            done
          />
        ),
      )}
    </div>
  );
}

function LiveConsoleSection({
  entries,
  prompt,
}: {
  entries: Map<string, LiveConsoleEntry>;
  prompt: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <PromptHeader text={prompt || "Current request"} />
      {Array.from(entries.entries()).map(([key, entry]) =>
        entry.entryType === "tool_call" ? (
          <ToolCallCard
            key={key}
            toolName={entry.toolName ?? "unknown"}
            toolArgs={entry.toolArgs}
            toolResult={entry.toolResult}
            done={entry.done}
            startedAt={entry.startedAt}
            finishedAt={entry.finishedAt}
          />
        ) : (
          <ThinkingBlock
            key={key}
            content={entry.thinkingContent ?? ""}
            done={entry.done}
          />
        ),
      )}
    </div>
  );
}

interface ConsolePanelProps {
  onCollapse?: () => void;
}

export function ConsolePanel({ onCollapse }: ConsolePanelProps) {
  const { liveConsoleEntries, historicalConsole, livePrompt } = useChildAgentActivity();
  const scrollRef = useRef<HTMLDivElement>(null);

  const hasLive = liveConsoleEntries.size > 0;
  const hasHistorical = historicalConsole.length > 0;

  useEffect(() => {
    const el = scrollRef.current;
    if (el && hasLive) {
      el.scrollTop = el.scrollHeight;
    }
  }, [liveConsoleEntries, hasLive]);

  let entryCount = liveConsoleEntries.size;
  for (const g of historicalConsole) entryCount += g.entries.length;

  return (
    <div className="flex h-full min-h-0 flex-col bg-muted/30 overflow-hidden">
      <div className="flex h-10 shrink-0 items-center justify-between border-b px-3">
        <div className="flex items-center gap-2">
          <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold text-muted-foreground">
            Console
          </span>
          {entryCount > 0 && (
            <Badge variant="secondary" className="text-[9px] px-1 py-0 h-3.5 min-w-[18px] justify-center">
              {entryCount}
            </Badge>
          )}
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

      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-2">
        {hasHistorical &&
          historicalConsole.map((group, idx) => (
            <ConsoleGroupSection key={group.triggerMessageId + idx} group={group} />
          ))}
        {hasLive && (
          <LiveConsoleSection entries={liveConsoleEntries} prompt={livePrompt} />
        )}
        {!hasLive && !hasHistorical && (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-xs text-muted-foreground italic">
              No console output yet
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
