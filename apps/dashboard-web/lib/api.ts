export type Overview = {
  today_runs: number;
  today_failures: number;
  sites: { site: string; latest_status: string; last_run: string | null }[];
};

const API_BASE = process.env.NEXT_PUBLIC_DASHBOARD_API_BASE ?? "http://127.0.0.1:8080";

export async function fetchOverview(): Promise<Overview> {
  const res = await fetch(`${API_BASE}/api/overview`, { cache: "no-store" });
  if (!res.ok) throw new Error(`overview fetch failed: ${res.status}`);
  return res.json();
}
