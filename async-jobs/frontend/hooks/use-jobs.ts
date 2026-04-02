import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { request } from "@/lib/api-client";

export interface Job {
  id: string;
  job_type: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  params: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface JobEvent {
  id: string;
  phase: string;
  level: string;
  message: string;
  detail: Record<string, unknown> | null;
  timestamp: string;
}

export const jobKeys = {
  all: ["jobs"] as const,
  list: (filters?: { job_type?: string; status?: string }) => [...jobKeys.all, "list", filters] as const,
  detail: (id: string) => [...jobKeys.all, "detail", id] as const,
  events: (id: string) => [...jobKeys.all, "events", id] as const,
};


export function useJobs(filters?: { job_type?: string; status?: string }) {
  return useQuery({
    queryKey: jobKeys.list(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      if (filters?.job_type) params.set("job_type", filters.job_type);
      if (filters?.status) params.set("status", filters.status);
      const qs = params.toString();
      return request<Job[]>(`/jobs${qs ? `?${qs}` : ""}`);
    },
    placeholderData: keepPreviousData,
    refetchInterval: (query) => {
      const jobs = query.state.data;
      return jobs?.some((j) => j.status === "queued" || j.status === "running")
        ? 3000
        : false;
    },
  });
}


export function useJob(jobId: string) {
  return useQuery({
    queryKey: jobKeys.detail(jobId),
    queryFn: () => request<Job>(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const job = query.state.data;
      return job && (job.status === "queued" || job.status === "running")
        ? 3000
        : false;
    },
  });
}


export function useJobEvents(jobId: string) {
  return useQuery({
    queryKey: jobKeys.events(jobId),
    queryFn: () => request<JobEvent[]>(`/jobs/${jobId}/events`),
    enabled: !!jobId,
  });
}


export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { job_type: string; params?: Record<string, unknown> }) =>
      request<Job>("/jobs", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: jobKeys.all });
    },
  });
}


export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      request<Job>(`/jobs/${jobId}/cancel`, { method: "POST" }),
    onSuccess: (_data, jobId) => {
      qc.invalidateQueries({ queryKey: jobKeys.detail(jobId) });
      qc.invalidateQueries({ queryKey: jobKeys.all });
    },
  });
}
