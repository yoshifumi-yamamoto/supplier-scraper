import { fetchMCPSummary, fetchOverview, fetchSystemMemory, fetchSystemSchedule, fetchValidatorSummary } from "@/lib/api";
import Link from "next/link";

type SiteView = {
  site: string;
  status: string;
  rawStatus: string;
  statusReason: string | null;
  processAlive: boolean;
  lastRun: string | null;
  startedAt: string | null;
  errorSummary: string;
  runSuccessRate: number | null;
  lastRunStatus: string;
  elapsedMinutes: number | null;
  nextRunAt: string | null;
  intervalMinutes: number | null;
  stepSummary: {
    totalItems: number | null;
    processedItems: number | null;
    remainingItems: number | null;
    successItems: number | null;
    failedItems: number | null;
    runningItems: number | null;
    progressPercent: number | null;
    lastStepAt: string | null;
    etaAt: string | null;
  } | null;
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

function mins(v?: number | null) {
  if (v == null) return "-";
  if (v < 60) return `${v}分`;
  const h = Math.floor(v / 60);
  const m = v % 60;
  return m ? `${h}時間${m}分` : `${h}時間`;
}

function siteStatus(status: string) {
  if (status === "success") return { label: "正常", tone: "ok" };
  if (status === "running") return { label: "稼働中", tone: "warn" };
  if (status === "stalled") return { label: "停止疑い", tone: "ng" };
  return { label: "エラー", tone: "ng" };
}

function runLabel(status: string) {
  if (status === "success") return "成功";
  if (status === "running") return "実行中";
  if (status === "failed" || status === "error") return "失敗";
  return "不明";
}

function aiSeverityLabel(severity?: string) {
  if (severity === "high") return "高";
  if (severity === "medium") return "中";
  if (severity === "low") return "低";
  return "-";
}

export default async function Page() {
  const overview = await fetchOverview();
  const systemMemory = await fetchSystemMemory();
  const mcp = await fetchMCPSummary();
  const schedule = await fetchSystemSchedule();
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
      status: latest?.display_status ?? latest?.status ?? ov?.latest_status ?? "unknown",
      rawStatus: latest?.status ?? ov?.latest_status ?? "unknown",
      statusReason: latest?.display_status_reason ?? null,
      processAlive: latest?.process_alive ?? false,
      lastRun: latest?.finished_at ?? latest?.started_at ?? ov?.last_run ?? null,
      startedAt: latest?.started_at ?? null,
      errorSummary: latest?.error_summary ?? "",
      runSuccessRate: ov?.run_success_rate ?? null,
      lastRunStatus: ov?.last_run_status ?? latest?.status ?? "unknown",
      elapsedMinutes: latest?.elapsed_minutes ?? null,
      nextRunAt: latest?.next_run_at ?? null,
      intervalMinutes: latest?.interval_minutes ?? null,
      stepSummary: latest?.step_summary
        ? {
            totalItems: latest.step_summary.total_items ?? null,
            processedItems: latest.step_summary.processed_items ?? null,
            remainingItems: latest.step_summary.remaining_items ?? null,
            successItems: latest.step_summary.success_items ?? null,
            failedItems: latest.step_summary.failed_items ?? null,
            runningItems: latest.step_summary.running_items ?? null,
            progressPercent: latest.step_summary.progress_percent ?? null,
            lastStepAt: latest.step_summary.last_step_at ?? null,
            etaAt: latest.step_summary.eta_at ?? null,
          }
        : null,
    };
  });

  const totalSites = sites.length;
  const okSites = sites.filter((s) => s.status === "success").length;
  const ngSites = sites.filter((s) => s.status !== "success").length;
  const runningSites = sites.filter((s) => s.status === "running").length;
  const health = totalSites === 0 ? 0 : Math.round((okSites / totalSites) * 100);
  const runningWithProgress = sites.filter((s) => s.status === "running" && s.stepSummary?.totalItems != null);
  const totalProcessingItems = runningWithProgress.reduce((sum, s) => sum + (s.stepSummary?.totalItems ?? 0), 0);
  const totalProcessedItems = runningWithProgress.reduce((sum, s) => sum + (s.stepSummary?.processedItems ?? 0), 0);

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
          <p>失敗サイト</p>
          <h2>{ngSites}</h2>
        </article>
        <article className="kpi-card">
          <p>監視サイト数</p>
          <h2>{mcp.kpis.sites_tracked || totalSites}</h2>
        </article>
        <article className="kpi-card">
          <p>実行中サイト</p>
          <h2>{runningSites}</h2>
        </article>
        <article className="kpi-card">
          <p>稼働中の処理件数</p>
          <h2>{totalProcessedItems}/{totalProcessingItems || "-"}</h2>
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
                  <p>{site.rawStatus}</p>
                </div>
                <span className={`pill pill-${st.tone}`}>{st.label}</span>
              </div>

              {site.stepSummary?.progressPercent != null ? (
                <>
                  <div className="progress-label">
                    <span>進捗</span>
                    <span>{site.stepSummary.processedItems}/{site.stepSummary.totalItems} ({pct(site.stepSummary.progressPercent)})</span>
                  </div>
                  <div className="progress-track">
                    <div className="progress-bar" style={{ width: pct(site.stepSummary.progressPercent) }} />
                  </div>
                </>
              ) : null}

              <div className="site-meta">
                <div>
                  <span>開始時刻</span>
                  <strong>{fmt(site.startedAt)}</strong>
                </div>
                <div>
                  <span>経過時間</span>
                  <strong>{mins(site.elapsedMinutes)}</strong>
                </div>
              </div>

              <div className="site-meta">
                <div>
                  <span>次回予定</span>
                  <strong>{site.status === "running" ? "実行中" : fmt(site.nextRunAt)}</strong>
                </div>
                <div>
                  <span>実行間隔</span>
                  <strong>{site.intervalMinutes ? `${site.intervalMinutes}分` : "-"}</strong>
                </div>
              </div>

              <div className="site-meta">
                <div>
                  <span>最終更新</span>
                  <strong>{fmt(site.stepSummary?.lastStepAt ?? site.lastRun)}</strong>
                </div>
                <div>
                  <span>前回結果</span>
                  <strong>{runLabel(site.lastRunStatus)}</strong>
                </div>
              </div>

              <div className="site-meta">
                <div>
                  <span>成功 / 失敗 / 実行中</span>
                  <strong>
                    {site.stepSummary
                      ? `${site.stepSummary.successItems ?? 0} / ${site.stepSummary.failedItems ?? 0} / ${site.stepSummary.runningItems ?? 0}`
                      : "-"}
                  </strong>
                </div>
                <div>
                  <span>残件 / 完了見込み</span>
                  <strong>
                    {site.stepSummary
                      ? `${site.stepSummary.remainingItems ?? "-"} / ${fmt(site.stepSummary.etaAt)}`
                      : "-"}
                  </strong>
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
                {site.errorSummary
                  ? site.errorSummary.slice(0, 90)
                  : site.statusReason === "process_missing_and_no_recent_step_activity"
                    ? "実プロセス不在かつ直近ステップ更新なし"
                    : site.statusReason === "process_missing_but_all_items_processed"
                      ? "実プロセス不在だが全件処理済み"
                      : "最新エラーなし"}
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
            抽出ツールのトップです。Mercari、Kitamura、Surugaya などサイト別の抽出画面へ移動できます。
          </p>
          <Link className="extract-link-button" href="/extract">
            抽出トップへ
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
            <div className="ops-card">
              <p>AI判定</p>
              <h4>{validator.ai_notification?.status === "sent" ? aiSeverityLabel(validator.ai_notification?.severity) : "-"}</h4>
            </div>
            <div className="ops-card">
              <p>Schedule</p>
              <h4>{schedule.items.length}</h4>
            </div>
          </div>
          <div className="code-line" style={{ marginTop: 16 }}>
            {validator.ai_notification?.title
              ? `AI: ${validator.ai_notification.title}`
              : validator.ai_notification?.error
                ? `AI error: ${validator.ai_notification.error}`
                : "AI判定の最新通知なし"}
          </div>
        </article>
      </section>
    </main>
  );
}
