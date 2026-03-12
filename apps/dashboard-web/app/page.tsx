import { fetchMCPSummary, fetchOverview, fetchSystemMemory, fetchValidatorSummary } from "@/lib/api";
import Link from "next/link";

type SiteView = {
  site: string;
  status: string;
  lastRun: string | null;
  errorSummary: string;
  successRate: number;
  runSuccessRate: number | null;
  lastRunStatus: string;
};

function fmt(ts?: string | null) {
  if (!ts) return "-";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("ja-JP", { hour12: false });
}

function pct(v: number) {
  return `${Math.max(0, Math.min(100, Math.round(v)))}%`;
}

function siteStatus(status: string) {
  if (status === "success") return { label: "正常", tone: "ok" };
  if (status === "running") return { label: "稼働中", tone: "warn" };
  return { label: "エラー", tone: "ng" };
}

function runLabel(status: string) {
  if (status === "success") return "成功";
  if (status === "running") return "実行中";
  if (status === "failed" || status === "error") return "失敗";
  return "不明";
}

export default async function Page() {
  const overview = await fetchOverview();
  const systemMemory = await fetchSystemMemory();
  const mcp = await fetchMCPSummary();
  const validator = await fetchValidatorSummary();

  const latestMap = new Map(mcp.latest_by_site.map((v) => [v.site, v]));
  const overviewMap = new Map(overview.sites.map((v) => [v.site, v]));
  const knownSites = ["mercari", "yahoofleama", "secondstreet", "yafuoku", "rakuma", "hardoff", "yodobashi", "kitamura"];
  const siteNames = Array.from(new Set([...knownSites, ...overview.sites.map((s) => s.site), ...mcp.latest_by_site.map((s) => s.site)]));
  const sites: SiteView[] = siteNames.map((name) => {
    const ov = overviewMap.get(name);
    const latest = latestMap.get(name);
    return {
      site: name,
      status: latest?.status ?? ov?.latest_status ?? "unknown",
      lastRun: latest?.finished_at ?? latest?.started_at ?? ov?.last_run ?? null,
      errorSummary: latest?.error_summary ?? "",
      successRate: ov?.success_rate ?? (latest?.status === "success" ? 100 : latest?.status === "running" ? 70 : 0),
      runSuccessRate: ov?.run_success_rate ?? null,
      lastRunStatus: ov?.last_run_status ?? latest?.status ?? "unknown",
    };
  });

  const totalSites = sites.length;
  const okSites = sites.filter((s) => s.status === "success").length;
  const ngSites = sites.filter((s) => s.status !== "success").length;
  const health = totalSites === 0 ? 0 : Math.round((okSites / totalSites) * 100);

  return (
    <main className="dashboard">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">S</div>
          <div>
            <h1>BaySync Scraper Dashboard</h1>
            <p>在庫スクレイピングシステム監視</p>
          </div>
        </div>
        <div className="top-tags">
          <span className="tag tag-live">LIVE DATA</span>
          <span className="tag">{totalSites}サイト監視中</span>
          <span className={`tag ${ngSites === 0 ? "tag-ok" : "tag-ng"}`}>
            {ngSites === 0 ? "システム稼働中" : "要対応"}
          </span>
        </div>
      </header>

      <section className="kpi-grid">
        <article className="kpi-card kpi-danger">
          <p>サイト正常率</p>
          <h2>{pct(health)}</h2>
        </article>
        <article className="kpi-card">
          <p>監視アイテム総数</p>
          <h2>{mcp.kpis.sites_tracked || totalSites}</h2>
        </article>
        <article className="kpi-card">
          <p>正常稼働</p>
          <h2>{okSites}</h2>
        </article>
        <article className="kpi-card">
          <p>エラー発生</p>
          <h2>{ngSites}</h2>
        </article>
        <article className="kpi-card">
          <p>メモリ使用率</p>
          <h2>{pct(systemMemory.memory.percent)}</h2>
        </article>
        <article className="kpi-card">
          <p>Swap使用率</p>
          <h2>{pct(systemMemory.swap.percent)}</h2>
        </article>
      </section>

      <section className="site-grid">
        {sites.map((site) => {
          const st = siteStatus(site.status);
          return (
            <article key={site.site} className={`site-card tone-${st.tone}`}>
              <div className="site-head">
                <div>
                  <h3>{site.site}</h3>
                  <p>{site.status}</p>
                </div>
                <span className={`pill pill-${st.tone}`}>{st.label}</span>
              </div>

              <div className="progress-label">
                <span>成功率</span>
                <span>{pct(site.successRate)}</span>
              </div>
              <div className="progress-track">
                <div className="progress-bar" style={{ width: pct(site.successRate) }} />
              </div>

              <div className="site-meta">
                <div>
                  <span>最終実行</span>
                  <strong>{fmt(site.lastRun)}</strong>
                </div>
                <div>
                  <span>前回実行</span>
                  <strong>{runLabel(site.lastRunStatus)}</strong>
                </div>
              </div>

              <div className="site-meta">
                <div>
                  <span>直近Run成功率</span>
                  <strong>{site.runSuccessRate == null ? "-" : pct(site.runSuccessRate)}</strong>
                </div>
                <div>
                  <span>現在状態</span>
                  <strong>{st.label}</strong>
                </div>
              </div>

              <div className="code-line">
                {site.errorSummary ? site.errorSummary.slice(0, 90) : "最新エラーなし"}
              </div>
            </article>
          );
        })}
      </section>

      <section className="bottom-grid">
        <article className="panel action-panel">
          <div className="panel-head">
            <h3>抽出ツール</h3>
            <span>別ページで実行</span>
          </div>
          <p className="action-copy">
            Mercari の検索URLを入力して、商品情報抽出ジョブを開始します。
          </p>
          <Link className="extract-link-button" href="/extract/mercari">
            Mercari抽出ページへ
          </Link>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h3>エラーログ</h3>
            <span>{mcp.top_errors.length}件</span>
          </div>
          <div className="list">
            {mcp.top_errors.length === 0 ? (
              <div className="list-item">直近エラーはありません</div>
            ) : (
              mcp.top_errors.map((row) => (
                <div key={`${row.message}-${row.count}`} className="list-item">
                  <p>{row.message}</p>
                  <div>
                    <span>x{row.count}</span>
                    <span>{fmt(row.last_seen_at)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h3>運用ステータス</h3>
            <span>{fmt(validator.checked_at)}</span>
          </div>
          <div className="ops-grid">
            <div className="ops-card">
              <p>MCP Success (24h)</p>
              <h4>{mcp.kpis.success_24h}</h4>
            </div>
            <div className="ops-card">
              <p>MCP Failed (24h)</p>
              <h4>{mcp.kpis.failed_24h}</h4>
            </div>
            <div className="ops-card">
              <p>CPU</p>
              <h4>{pct(mcp.server.cpu_percent)}</h4>
            </div>
            <div className="ops-card">
              <p>Chrome</p>
              <h4>{mcp.server.chrome_processes}</h4>
            </div>
            <div className="ops-card">
              <p>Validator Retry</p>
              <h4>{validator.retried_count}</h4>
            </div>
            <div className="ops-card">
              <p>Today Failures</p>
              <h4>{overview.today_failures}</h4>
            </div>
          </div>
        </article>
      </section>
    </main>
  );
}
