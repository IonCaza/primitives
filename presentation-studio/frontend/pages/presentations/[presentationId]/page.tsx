"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PresentationStudio } from "@/components/presentation-studio";
import { usePresentation } from "@/hooks/use-presentations";
import { Skeleton } from "@/components/ui/skeleton";

export default function PresentationStudioPage({
  params,
}: {
  params: Promise<{ projectId: string; presentationId: string }>;
}) {
  const { projectId, presentationId } = use(params);
  const { data: presentation } = usePresentation(projectId, presentationId);

  return (
    <div className="flex flex-col h-[calc(100vh-13rem)] min-h-[400px]">
      <div className="flex items-center gap-3 pb-4 shrink-0">
        <Link
          href={`/projects/${projectId}/presentations`}
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        {presentation ? (
          <h2 className="text-xl font-semibold tracking-tight truncate">
            {presentation.title}
          </h2>
        ) : (
          <Skeleton className="h-7 w-48" />
        )}
      </div>

      <div className="flex-1 min-h-0">
        <PresentationStudio projectId={projectId} presentationId={presentationId} />
      </div>
    </div>
  );
}
