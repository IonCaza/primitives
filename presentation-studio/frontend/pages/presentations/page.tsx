"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Plus,
  Sparkles,
  Trash2,
  Calendar,
  MoreVertical,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { usePresentations, useDeletePresentation } from "@/hooks/use-presentations";
import { cn } from "@/lib/utils";
import type { PresentationListItem } from "@/lib/types";

function statusColor(s: string) {
  switch (s) {
    case "draft":
      return "bg-amber-500/15 text-amber-700 dark:text-amber-400";
    case "published":
      return "bg-green-500/15 text-green-700 dark:text-green-400";
    default:
      return "bg-muted text-muted-foreground";
  }
}

export default function PresentationsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const router = useRouter();
  const { data: presentations, isLoading } = usePresentations(projectId);
  const deleteMutation = useDeletePresentation(projectId);
  const [deleteTarget, setDeleteTarget] = useState<PresentationListItem | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            AI-generated dashboards and visualizations from your project data.
          </p>
        </div>
        <Button size="sm" onClick={() => router.push(`/projects/${projectId}/presentations/new`)}>
          <Plus className="mr-2 h-4 w-4" />
          New Presentation
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-xl" />
          ))}
        </div>
      ) : !presentations?.length ? (
        <Card className="border-dashed border-2">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <LayoutDashboard className="h-12 w-12 text-muted-foreground/40 mb-3" />
            <h3 className="text-lg font-medium">No presentations yet</h3>
            <p className="text-sm text-muted-foreground mt-1 max-w-md">
              Create your first AI-generated dashboard with charts, metrics, and
              insights from your project data.
            </p>
            <Button
              className="mt-4"
              onClick={() => router.push(`/projects/${projectId}/presentations/new`)}
            >
              <Sparkles className="mr-2 h-4 w-4" />
              Create Presentation
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {presentations.map((pres) => (
            <Link
              key={pres.id}
              href={`/projects/${projectId}/presentations/${pres.id}`}
              className="group"
            >
              <Card className="h-full transition-all hover:border-primary/50 hover:shadow-md hover:shadow-primary/5">
                <CardContent className="p-5 flex flex-col h-full">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold truncate group-hover:text-primary transition-colors">
                        {pres.title}
                      </h3>
                      {pres.description && (
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                          {pres.description}
                        </p>
                      )}
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild onClick={(e) => e.preventDefault()}>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0 opacity-0 group-hover:opacity-100 transition-opacity">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={(e) => {
                            e.preventDefault();
                            setDeleteTarget(pres);
                          }}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>

                  <div className="mt-auto pt-4 flex items-center gap-2 text-xs text-muted-foreground">
                    <Badge
                      variant="secondary"
                      className={cn("text-[10px] capitalize", statusColor(pres.status))}
                    >
                      {pres.status}
                    </Badge>
                    <span className="flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      {new Date(pres.created_at).toLocaleDateString()}
                    </span>
                    <span className="ml-auto opacity-60">v{pres.template_version}</span>
                  </div>

                  {pres.prompt && (
                    <p className="mt-2 text-xs text-muted-foreground/60 italic line-clamp-1">
                      &ldquo;{pres.prompt}&rdquo;
                    </p>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete Presentation"
        description={
          <>
            Are you sure you want to delete{" "}
            <strong>{deleteTarget?.title}</strong>? This action cannot be undone.
          </>
        }
        confirmLabel="Delete"
        onConfirm={() =>
          deleteTarget && deleteMutation.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) })
        }
      />
    </div>
  );
}
