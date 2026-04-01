"use client";

import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useComposerRuntime, useAuiState } from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/thread";
import { ChatRuntime, useChildAgentActivity } from "@/components/chat-runtime";
import { AgentActivityPanel } from "@/components/agent-activity-panel";
import { PresentationSandbox } from "@/components/presentation-sandbox";
import { usePresentation, usePresentationTemplate } from "@/hooks/use-presentations";
import { useProject } from "@/hooks/use-projects";
import { queryKeys } from "@/lib/query-keys";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { Skeleton } from "@/components/ui/skeleton";
import { GripVertical, Maximize2, PanelTopClose, PanelTop } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface PresentationStudioProps {
  projectId: string;
  presentationId: string;
}

function InitialPromptSender({
  prompt,
  hasCode,
}: {
  prompt: string;
  hasCode: boolean;
}) {
  const composer = useComposerRuntime();
  const composerRef = useRef(composer);
  composerRef.current = composer;
  const sent = useRef(false);
  const threadReady = useAuiState(
    (s: { threadListItem: { remoteId?: string } }) =>
      !!s.threadListItem?.remoteId,
  );

  useEffect(() => {
    if (!prompt || hasCode || sent.current || !threadReady) return;
    const timer = setTimeout(() => {
      if (sent.current) return;
      sent.current = true;
      composerRef.current.setText(prompt);
      composerRef.current.send();
    }, 300);
    return () => clearTimeout(timer);
  }, [prompt, hasCode, threadReady]);

  return null;
}

function StudioInner({ projectId, presentationId }: PresentationStudioProps) {
  const { activityVisible, setActivityVisible } = useChildAgentActivity();

  const { data: presentation, isLoading: presLoading } = usePresentation(
    projectId, presentationId, { refetchInterval: 5000 },
  );
  const { data: template, isLoading: tmplLoading } = usePresentationTemplate(
    presentation?.template_version ?? 0,
  );

  const previewRef = useRef<HTMLDivElement>(null);
  const handleFullscreen = useCallback(() => {
    previewRef.current?.requestFullscreen?.();
  }, []);

  const isLoading = presLoading || tmplLoading;

  return (
    <>
      {presentation && (
        <InitialPromptSender
          prompt={presentation.prompt}
          hasCode={!!presentation.component_code}
        />
      )}
      <ResizablePanelGroup orientation="horizontal" className="h-full">
        <ResizablePanel id="studio-chat" defaultSize="40%" minSize="25%">
          <div className="h-full flex flex-col overflow-hidden border border-border rounded-lg">
            {activityVisible && (
              <div className="border-b border-border max-h-[40%] overflow-auto shrink-0">
                <AgentActivityPanel />
              </div>
            )}
            <div className="flex items-center justify-end px-2 py-1 border-b border-border bg-muted/30 shrink-0">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 text-muted-foreground"
                    onClick={() => setActivityVisible(!activityVisible)}
                  >
                    {activityVisible ? (
                      <PanelTopClose className="h-3.5 w-3.5" />
                    ) : (
                      <PanelTop className="h-3.5 w-3.5" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {activityVisible ? "Hide agent activity" : "Show agent activity"}
                </TooltipContent>
              </Tooltip>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <Thread />
            </div>
          </div>
        </ResizablePanel>

        <ResizableHandle className="w-2 flex items-center justify-center bg-transparent hover:bg-accent transition-colors">
          <GripVertical className="h-4 w-4 text-muted-foreground" />
        </ResizableHandle>

        <ResizablePanel id="studio-preview" defaultSize="60%" minSize="30%">
          <div ref={previewRef} className="h-full flex flex-col border border-border rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-muted/30 shrink-0">
              <span className="text-sm font-medium text-muted-foreground">
                Preview
                {presentation?.template_version && (
                  <span className="ml-2 text-xs opacity-60">
                    template v{presentation.template_version}
                  </span>
                )}
              </span>
              <Button variant="ghost" size="sm" onClick={handleFullscreen} title="Fullscreen">
                <Maximize2 className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              {isLoading ? (
                <div className="p-4 space-y-4">
                  <Skeleton className="h-8 w-64" />
                  <div className="grid grid-cols-3 gap-4">
                    <Skeleton className="h-24" />
                    <Skeleton className="h-24" />
                    <Skeleton className="h-24" />
                  </div>
                  <Skeleton className="h-48" />
                </div>
              ) : (
                <PresentationSandbox
                  componentCode={presentation?.component_code ?? ""}
                  templateHtml={template?.template_html ?? ""}
                  projectId={projectId}
                />
              )}
            </div>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </>
  );
}

export function PresentationStudio({ projectId, presentationId }: PresentationStudioProps) {
  const qc = useQueryClient();
  const { data: project } = useProject(projectId);
  const { data: presentation } = usePresentation(projectId, presentationId);

  const handlePresentationUpdate = useCallback(
    (_updatedId: string) => {
      qc.refetchQueries({
        queryKey: queryKeys.presentations.detail(projectId, presentationId),
      });
    },
    [qc, projectId, presentationId],
  );

  const projectName = project?.name ?? "";

  const storedPrompt = presentation?.prompt ?? "";
  const paletteMatch = storedPrompt.match(/\[color-palette:[^\]]*\]/);
  const paletteCtx = paletteMatch ? ` ${paletteMatch[0]}` : "";

  const messageTransform = useCallback(
    (text: string) => {
      const ctx =
        `[context: presentation_id="${presentationId}", project="${projectName}".${paletteCtx} ` +
        `Always use save_presentation with presentation_id="${presentationId}" ` +
        `and project_name="${projectName}" when saving.]`;
      return `${ctx}\n\n${text}`;
    },
    [presentationId, projectName, paletteCtx],
  );

  const chatSessionId = presentation?.chat_session_id ?? undefined;

  if (!chatSessionId) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Loading presentation…
      </div>
    );
  }

  return (
    <ChatRuntime
      key={chatSessionId}
      agentSlug="presentation-designer"
      onPresentationUpdate={handlePresentationUpdate}
      messageTransform={messageTransform}
      fixedSessionId={chatSessionId}
    >
      <StudioInner projectId={projectId} presentationId={presentationId} />
    </ChatRuntime>
  );
}
