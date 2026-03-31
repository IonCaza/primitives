"use client";

import { useEffect, useRef } from "react";
import { PanelRightClose, Loader2, CheckCircle2, Bot, MessageSquare } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import {
  useChildAgentActivity,
  type ActivityGroup,
} from "@/components/chat-runtime";
import { useAgents } from "@/hooks/use-settings";
import { cn } from "@/lib/utils";

function slugToName(
  slug: string,
  agents: { slug: string; name: string }[],
): string {
  return agents.find((a) => a.slug === slug)?.name ?? slug.replace(/-/g, " ");
}

function AgentCard({
  slug,
  content,
  done,
  agentList,
}: {
  slug: string;
  content: string;
  done: boolean;
  agentList: { slug: string; name: string }[];
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && !done) {
      el.scrollTop = el.scrollHeight;
    }
  }, [content, done]);

  return (
    <div className="flex max-h-64 min-h-0 flex-col rounded-lg border bg-card text-card-foreground">
      <div className="flex items-center gap-2 border-b px-3 py-1.5 shrink-0">
        <Bot className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="truncate text-xs font-semibold">
          {slugToName(slug, agentList)}
        </span>
        <span className="ml-auto">
          {done ? (
            <CheckCircle2 className="h-3 w-3 text-emerald-500" />
          ) : (
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
          )}
        </span>
      </div>
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="p-2 text-xs leading-relaxed">
          {content ? (
            <div className="prose prose-xs dark:prose-invert max-w-none break-words [&_table]:text-[10px] [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            </div>
          ) : (
            <span className="italic text-muted-foreground">Thinking...</span>
          )}
        </div>
      </div>
    </div>
  );
}

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

function ActivityGroupSection({
  group,
  agentList,
}: {
  group: ActivityGroup;
  agentList: { slug: string; name: string }[];
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <PromptHeader text={group.triggerContent} />
      {group.agents.map((agent) => (
        <AgentCard
          key={agent.runId}
          slug={agent.slug}
          content={agent.content}
          done={agent.done}
          agentList={agentList}
        />
      ))}
    </div>
  );
}

interface AgentActivityPanelProps {
  onCollapse?: () => void;
}

export function AgentActivityPanel({ onCollapse }: AgentActivityPanelProps) {
  const {
    liveAgents,
    historicalActivities,
    livePrompt,
  } = useChildAgentActivity();
  const { data: agentList = [] } = useAgents();

  const hasLive = liveAgents.size > 0;
  const hasHistorical = historicalActivities.length > 0;

  const liveGroup: ActivityGroup | null = hasLive
    ? {
        triggerMessageId: "__live__",
        triggerContent: livePrompt || "Current request",
        agents: Array.from(liveAgents.entries()).map(([runId, a]) => ({
          runId,
          slug: a.slug,
          content: a.content,
          done: a.done,
        })),
      }
    : null;

  return (
    <div className="flex h-full min-h-0 flex-col bg-muted/30 overflow-hidden">
      <div className="flex h-10 shrink-0 items-center justify-between border-b px-3">
        <span className="text-xs font-semibold text-muted-foreground">
          Agent Activity
        </span>
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
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-2">
        {hasHistorical &&
          historicalActivities.map((group) => (
            <ActivityGroupSection
              key={group.triggerMessageId}
              group={group}
              agentList={agentList}
            />
          ))}
        {liveGroup && (
          <ActivityGroupSection group={liveGroup} agentList={agentList} />
        )}
        {!hasLive && !hasHistorical && (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-xs text-muted-foreground italic">
              No agent activity yet
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
