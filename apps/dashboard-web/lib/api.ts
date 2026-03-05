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

const API_BASE = process.env.NEXT_PUBLIC_DASHBOARD_API_BASE ?? "http://127.0.0.1:8080";

export async function fetchOverview(): Promise<Overview> {
  const res = await fetch(`${API_BASE}/api/overview`, { cache: "no-store" });
  if (!res.ok) throw new Error(`overview fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchSystemMemory(): Promise<SystemMemory> {
  const res = await fetch(`${API_BASE}/api/system/memory`, { cache: "no-store" });
  if (!res.ok) throw new Error(`system memory fetch failed: ${res.status}`);
  return res.json();
}
