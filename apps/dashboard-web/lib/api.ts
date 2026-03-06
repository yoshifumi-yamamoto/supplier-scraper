export type Overview = {
  today_runs: number;
  today_failures: number;
  sites: { site: string; latest_status: string; last_run: string | null }[];
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
    started_at: string | null;
    finished_at: string | null;
    error_summary: string;
  }[];
  top_errors: { message: string; count: number }[];
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
  status: string;
};

const API_BASE = process.env.NEXT_PUBLIC_DASHBOARD_API_BASE ?? "http://127.0.0.1:8080";

export async function fetchOverview(): Promise<Overview> {
  try {
    const res = await fetch(`${API_BASE}/api/overview`, { cache: "no-store" });
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
    const res = await fetch(`${API_BASE}/api/system/memory`, { cache: "no-store" });
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
    const res = await fetch(`${API_BASE}/api/mcp/summary`, { cache: "no-store" });
    if (!res.ok) return fallback;
    return res.json();
  } catch {
    return fallback;
  }
}

export async function fetchSystemSchedule(): Promise<SystemSchedule> {
  const fallback: SystemSchedule = { timezone: "Asia/Tokyo", items: [] };
  try {
    const res = await fetch(`${API_BASE}/api/system/schedule`, { cache: "no-store" });
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
    status: "unknown",
  };
  try {
    const res = await fetch(`${API_BASE}/api/validator/summary`, { cache: "no-store" });
    if (!res.ok) return fallback;
    return res.json();
  } catch {
    return fallback;
  }
}
