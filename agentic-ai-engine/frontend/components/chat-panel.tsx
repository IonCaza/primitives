"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Bot, ChevronDown, ClipboardList, GripVertical, PanelRightOpen, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Thread } from "@/components/assistant-ui/thread";
import { ThreadList } from "@/components/assistant-ui/thread-list";
import { ChatRuntime, useChildAgentActivity, useTaskBoard } from "@/components/chat-runtime";
import { AgentActivityPanel } from "@/components/agent-activity-panel";
import { TaskBoardPanel } from "@/components/task-board-panel";
import { useAgents } from "@/hooks/use-settings";
import { useComposerRuntime } from "@assistant-ui/react";
import { useChatTrigger } from "@/hooks/use-chat-trigger";
import { cn } from "@/lib/utils";

const AgentNameContext = createContext<string>("AI Assistant");
export const useAgentName = () => useContext(AgentNameContext);

interface ChatPanelProps {
  open: boolean;
  onClose: () => void;
}

const MIN_ACTIVITY_PCT = 20;
const MAX_ACTIVITY_PCT = 70;
const DEFAULT_ACTIVITY_PCT = 50;

type PanelTab = "activity" | "tasks";

function ChatPanelInner() {
  const { activityVisible, setActivityVisible } = useChildAgentActivity();
  const { updateCounter } = useTaskBoard();
  const [activityPct, setActivityPct] = useState(DEFAULT_ACTIVITY_PCT);
  const [panelTab, setPanelTab] = useState<PanelTab>("activity");
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  useEffect(() => {
    if (updateCounter > 0 && !activityVisible) {
      setActivityVisible(true);
      setPanelTab("tasks");
    }
  }, [updateCounter, activityVisible, setActivityVisible]);

  const toggleActivity = useCallback(() => {
    setActivityVisible(!activityVisible);
  }, [activityVisible, setActivityVisible]);

  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      dragging.current = true;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [],
  );

  const onHandlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const pct = ((rect.width - x) / rect.width) * 100;
      setActivityPct(Math.min(MAX_ACTIVITY_PCT, Math.max(MIN_ACTIVITY_PCT, pct)));
    },
    [],
  );

  const onHandlePointerUp = useCallback(() => {
    dragging.current = false;
  }, []);

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      <div className="w-52 shrink-0 overflow-y-auto border-r p-2">
        <ThreadList />
      </div>

      <div ref={containerRef} className="relative flex flex-1 min-w-0 min-h-0">
        {/* Main chat thread */}
        <div
          className="min-w-0 min-h-0 overflow-hidden"
          style={{ width: activityVisible ? `${100 - activityPct}%` : "100%" }}
        >
          <Thread />
          {!activityVisible && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-2 z-10 h-7 w-7 text-muted-foreground hover:text-foreground"
              onClick={toggleActivity}
              title="Show agent activity"
            >
              <PanelRightOpen className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>

        {/* Drag handle */}
        {activityVisible && (
          <div
            className={cn(
              "flex w-2 shrink-0 cursor-col-resize items-center justify-center",
              "border-x bg-border/40 transition-colors hover:bg-accent/60 active:bg-accent",
              "select-none touch-none",
            )}
            onPointerDown={onHandlePointerDown}
            onPointerMove={onHandlePointerMove}
            onPointerUp={onHandlePointerUp}
            onPointerCancel={onHandlePointerUp}
          >
            <GripVertical className="h-4 w-4 text-muted-foreground/50" />
          </div>
        )}

        {/* Side panel (activity or tasks) */}
        {activityVisible && (
          <div
            className="flex min-w-0 min-h-0 flex-col overflow-hidden"
            style={{ width: `${activityPct}%` }}
          >
            <div className="flex h-8 shrink-0 items-center border-b px-1">
              <Button
                variant={panelTab === "activity" ? "secondary" : "ghost"}
                size="sm"
                className="h-6 gap-1 px-2 text-[11px]"
                onClick={() => setPanelTab("activity")}
              >
                <Users className="h-3 w-3" />
                Agents
              </Button>
              <Button
                variant={panelTab === "tasks" ? "secondary" : "ghost"}
                size="sm"
                className="h-6 gap-1 px-2 text-[11px]"
                onClick={() => setPanelTab("tasks")}
              >
                <ClipboardList className="h-3 w-3" />
                Tasks
              </Button>
            </div>
            <div className="min-h-0 flex-1">
              {panelTab === "activity" ? (
                <AgentActivityPanel onCollapse={toggleActivity} />
              ) : (
                <TaskBoardPanel onCollapse={toggleActivity} />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ChatAutoSender({ message }: { message: string | null }) {
  const composer = useComposerRuntime();
  const sent = useRef(false);

  useEffect(() => {
    if (!message || sent.current) return;
    sent.current = true;
    requestAnimationFrame(() => {
      composer.setText(message);
      composer.send();
    });
  }, [message, composer]);

  useEffect(() => {
    sent.current = false;
  }, [message]);

  return null;
}

const DEFAULT_AGENT_KEY = "ai-engine:defaultAgent";

function readDefaultAgent(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(DEFAULT_AGENT_KEY);
}

function persistDefaultAgent(slug: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(DEFAULT_AGENT_KEY, slug);
}

export function ChatPanel({ open, onClose }: ChatPanelProps) {
  const { data: agents = [] } = useAgents();
  const enabledAgents = agents.filter((a) => a.enabled);
  const [agentSlug, setAgentSlug] = useState(() => readDefaultAgent() ?? "assistant");
  const { pending, consume } = useChatTrigger();
  const [autoMessage, setAutoMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!enabledAgents.length) return;
    const match = enabledAgents.find((a) => a.slug === agentSlug);
    if (!match) {
      const stored = readDefaultAgent();
      const fallback = enabledAgents.find((a) => a.slug === stored) ?? enabledAgents[0];
      setAgentSlug(fallback.slug);
    }
  }, [enabledAgents, agentSlug]);

  const handleAgentChange = useCallback((slug: string) => {
    setAgentSlug(slug);
    persistDefaultAgent(slug);
  }, []);

  useEffect(() => {
    if (!open || !pending) return;
    const req = consume();
    if (!req) return;
    setAgentSlug(req.agentSlug);
    setAutoMessage(req.message);
  }, [open, pending, consume]);

  const agentName =
    enabledAgents.find((a) => a.slug === agentSlug)?.name ?? "AI Assistant";

  if (!open) return <div className="h-full bg-background" />;

  return (
    <ChatRuntime agentSlug={agentSlug}>
      <AgentNameContext.Provider value={agentName}>
        <ChatAutoSender message={autoMessage} />
        <div className="flex h-full flex-col bg-background">
          <div className="flex h-10 shrink-0 items-center justify-between border-b px-4">
            <div className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-primary" />
              {enabledAgents.length > 1 ? (
                <Select value={agentSlug} onValueChange={handleAgentChange}>
                  <SelectTrigger className="h-7 w-auto border-0 bg-transparent py-0 px-1.5 text-sm font-semibold shadow-none focus:ring-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {enabledAgents.map((a) => (
                      <SelectItem key={a.slug} value={a.slug}>
                        {a.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <span className="text-sm font-semibold">
                  {enabledAgents[0]?.name || "AI Assistant"}
                </span>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={onClose}
              title="Minimize"
            >
              <ChevronDown className="h-3.5 w-3.5" />
            </Button>
          </div>

          <ChatPanelInner />
        </div>
      </AgentNameContext.Provider>
    </ChatRuntime>
  );
}
