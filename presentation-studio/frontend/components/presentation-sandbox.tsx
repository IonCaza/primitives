"use client";

import { useRef, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api-client";

interface PresentationSandboxProps {
  componentCode: string;
  templateHtml: string;
  projectId: string;
}

export function PresentationSandbox({
  componentCode,
  templateHtml,
  projectId,
}: PresentationSandboxProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [frameKey, setFrameKey] = useState(0);

  const srcdoc = useMemo(() => {
    if (!templateHtml) return "";
    const code = componentCode || "function App() { return React.createElement('div', { className: 'p-8 min-h-screen flex items-center justify-center text-gray-500' }, 'Waiting for presentation content...'); }";
    const marker = "/* __COMPONENT_CODE__ */";
    const idx = templateHtml.indexOf(marker);
    if (idx === -1) return templateHtml;
    return templateHtml.slice(0, idx) + code + templateHtml.slice(idx + marker.length);
  }, [templateHtml, componentCode]);

  useEffect(() => {
    setFrameKey((k) => k + 1);
  }, [srcdoc]);

  useEffect(() => {
    const handler = async (event: MessageEvent) => {
      if (event.data?.type !== "presentation_query") return;
      if (event.source !== iframeRef.current?.contentWindow) return;

      const { v = 1, id, tool, params } = event.data;

      if (v === 1) {
        try {
          const response = await api.executePresentationQuery(projectId, tool, params);
          iframeRef.current?.contentWindow?.postMessage({ id, result: response.result }, "*");
        } catch (error) {
          const message = error instanceof Error ? error.message : "Unknown error";
          iframeRef.current?.contentWindow?.postMessage({ id, error: message }, "*");
        }
      }
    };

    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [projectId]);

  return (
    <iframe
      key={frameKey}
      ref={iframeRef}
      srcDoc={srcdoc}
      sandbox="allow-scripts"
      className="w-full h-full border-0 bg-gray-950 rounded-lg"
      title="Presentation Preview"
    />
  );
}
