import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

export function usePresentations(projectId: string) {
  return useQuery({
    queryKey: queryKeys.presentations.list(projectId),
    queryFn: () => api.listPresentations(projectId),
    enabled: !!projectId,
  });
}

export function usePresentation(
  projectId: string,
  presentationId: string,
  opts?: { refetchInterval?: number },
) {
  return useQuery({
    queryKey: queryKeys.presentations.detail(projectId, presentationId),
    queryFn: () => api.getPresentation(projectId, presentationId),
    enabled: !!projectId && !!presentationId,
    ...(opts?.refetchInterval ? { refetchInterval: opts.refetchInterval } : {}),
  });
}

export function usePresentationVersions(projectId: string, presentationId: string) {
  return useQuery({
    queryKey: queryKeys.presentations.versions(projectId, presentationId),
    queryFn: () => api.listPresentationVersions(projectId, presentationId),
    enabled: !!projectId && !!presentationId,
  });
}

export function usePresentationTemplate(version: number) {
  return useQuery({
    queryKey: queryKeys.presentations.template(version),
    queryFn: () => api.getPresentationTemplate(version),
    enabled: version > 0,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

export function useLatestPresentationTemplate() {
  return useQuery({
    queryKey: queryKeys.presentations.templateLatest,
    queryFn: () => api.getLatestPresentationTemplate(),
  });
}

export function useCreatePresentation(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { title: string; description?: string; prompt?: string; chat_session_id?: string }) =>
      api.createPresentation(projectId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.presentations.list(projectId) });
    },
  });
}

export function useUpdatePresentation(projectId: string, presentationId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { title?: string; description?: string; component_code?: string; template_version?: number; status?: string }) =>
      api.updatePresentation(projectId, presentationId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.presentations.detail(projectId, presentationId) });
      qc.invalidateQueries({ queryKey: queryKeys.presentations.list(projectId) });
    },
  });
}

export function useDeletePresentation(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (presId: string) => api.deletePresentation(projectId, presId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.presentations.list(projectId) });
    },
  });
}
