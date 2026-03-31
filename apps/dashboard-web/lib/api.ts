export type Overview = {
  today_runs: number;
  today_failures: number;
  sites: { site: string; latest_status: string; last_run: string | null; last_run_status?: string | null; success_rate?: number | null; run_success_rate?: number | null }[];
};

export type SystemMemory = {
  memory: {
    total_mb: number;
    used_mb: number;
    available_mb: number;
    percent: number;
  };
  swap: {
    total_mb: number;
    used_mb: number;
    free_mb: number;
    percent: number;
  };
};

export type MCPSummary = {
  kpis: {
    success_24h: number;
    failed_24h: number;
    running_runs: number;
    sites_tracked: number;
  };
  latest_by_site: {
    site: string;
    status: string;
    display_status?: string;
    display_status_reason?: string | null;
    process_alive?: boolean;
    started_at: string | null;
    finished_at: string | null;
    error_summary: string;
    error_type?: string;
    elapsed_minutes?: number | null;
    next_run_at?: string | null;
    interval_minutes?: number | null;
    step_summary?: {
      total_items?: number | null;
      processed_items?: number | null;
      remaining_items?: number | null;
      success_items?: number | null;
      failed_items?: number | null;
      running_items?: number | null;
      progress_percent?: number | null;
      last_step_at?: string | null;
      avg_step_sec?: number | null;
      eta_at?: string | null;
    } | null;
  }[];
  top_errors: { message: string; error_type?: string; count: number; last_seen_at?: string | null }[];
  server: {
    cpu_percent: number;
    memory_percent: number;
    chrome_processes: number;
    runner_processes: number;
  };
};

export type SystemSchedule = {
  timezone: string;
  items: { schedule: string; command: string }[];
};

export type ValidatorSummary = {
  checked_at: string | null;
  failed_recent: number;
  retried_count: number;
  skipped_count: number;
  retried: { site?: string; failed_run_id?: string; error_type?: string }[];
  skipped: { site?: string; run_id?: string; reason?: string; error_type?: string }[];
  ai_notification: {
    status?: string;
    severity?: string;
    title?: string;
    reasons?: string[];
    error?: string;
  } | null;
  status: string;
};

const SERVER_API_BASE = process.env.DASHBOARD_API_BASE ?? "http://127.0.0.1:8080";
const CLIENT_API_BASE = process.env.NEXT_PUBLIC_DASHBOARD_API_BASE ?? "";

export async function fetchOverview(): Promise<Overview> {
  try {
    const res = await fetch(`${SERVER_API_BASE}/api/overview`, { next: { revalidate: 10 } });
    if (!res.ok) {
      return { today_runs: 0, today_failures: 0, sites: [] };
    }
    return res.json();
  } catch {
    return { today_runs: 0, today_failures: 0, sites: [] };
  }
}

export async function fetchSystemMemory(): Promise<SystemMemory> {
  try {
    const res = await fetch(`${SERVER_API_BASE}/api/system/memory`, { next: { revalidate: 5 } });
    if (!res.ok) {
      return {
        memory: { total_mb: 0, used_mb: 0, available_mb: 0, percent: 0 },
        swap: { total_mb: 0, used_mb: 0, free_mb: 0, percent: 0 },
      };
    }
    return res.json();
  } catch {
    return {
      memory: { total_mb: 0, used_mb: 0, available_mb: 0, percent: 0 },
      swap: { total_mb: 0, used_mb: 0, free_mb: 0, percent: 0 },
    };
  }
}

export async function fetchMCPSummary(): Promise<MCPSummary> {
  const fallback: MCPSummary = {
    kpis: { success_24h: 0, failed_24h: 0, running_runs: 0, sites_tracked: 0 },
    latest_by_site: [],
    top_errors: [],
    server: { cpu_percent: 0, memory_percent: 0, chrome_processes: 0, runner_processes: 0 },
  };
  try {
    const res = await fetch(`${SERVER_API_BASE}/api/mcp/summary`, { cache: "no-store" });
    if (!res.ok) return fallback;
    return res.json();
  } catch {
    return fallback;
  }
}

export async function fetchSystemSchedule(): Promise<SystemSchedule> {
  const fallback: SystemSchedule = { timezone: "Asia/Tokyo", items: [] };
  try {
    const res = await fetch(`${SERVER_API_BASE}/api/system/schedule`, { next: { revalidate: 60 } });
    if (!res.ok) return fallback;
    return res.json();
  } catch {
    return fallback;
  }
}

export async function fetchValidatorSummary(): Promise<ValidatorSummary> {
  const fallback: ValidatorSummary = {
    checked_at: null,
    failed_recent: 0,
    retried_count: 0,
    skipped_count: 0,
    retried: [],
    skipped: [],
    ai_notification: null,
    status: "unknown",
  };
  try {
    const res = await fetch(`${SERVER_API_BASE}/api/validator/summary`, { next: { revalidate: 30 } });
    if (!res.ok) return fallback;
    return res.json();
  } catch {
    return fallback;
  }
}

export function clientApiBase(): string {
  return CLIENT_API_BASE;
}
