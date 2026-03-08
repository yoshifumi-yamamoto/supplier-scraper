import { fetchMCPSummary, fetchOverview, fetchSystemMemory, fetchSystemSchedule, fetchValidatorSummary } from "@/lib/api";

function statusClass(status: string) {
  return status === "success" ? "badge badge-ok" : "badge badge-ng";
}

export default async function Page() {
  const overview = await fetchOverview();
  const systemMemory = await fetchSystemMemory();
  const mcp = await fetchMCPSummary();
  const schedule = await fetchSystemSchedule();
  const validator = await fetchValidatorSummary();

  return (
    <main className="container">
      <h1>Supplier Scraper Dashboard</h1>
      <p>統合ランナーの稼働状況を表示します。</p>

      <section className="grid">
        <div className="card">
          <div className="label">Today Runs</div>
          <div className="value">{overview.today_runs}</div>
        </div>
        <div className="card">
          <div className="label">Today Failures</div>
          <div className="value">{overview.today_failures}</div>
        </div>
        <div className="card">
          <div className="label">Tracked Sites</div>
          <div className="value">{overview.sites.length}</div>
        </div>
        <div className="card">
          <div className="label">Memory Used</div>
          <div className="value">{systemMemory.memory.percent}%</div>
        </div>
        <div className="card">
          <div className="label">Memory Available</div>
          <div className="value">{Math.round(systemMemory.memory.available_mb)}MB</div>
        </div>
        <div className="card">
          <div className="label">Swap Used</div>
          <div className="value">{systemMemory.swap.percent}%</div>
        </div>
      </section>

      <h2 className="section-title">Operations</h2>
      <section className="grid">
        <div className="card">
          <div className="label">MCP Success (24h)</div>
          <div className="value">{mcp.kpis.success_24h}</div>
        </div>
        <div className="card">
          <div className="label">MCP Failed (24h)</div>
          <div className="value">{mcp.kpis.failed_24h}</div>
        </div>
        <div className="card">
          <div className="label">MCP Running</div>
          <div className="value">{mcp.kpis.running_runs}</div>
        </div>
        <div className="card">
          <div className="label">Server CPU</div>
          <div className="value">{mcp.server.cpu_percent}%</div>
        </div>
        <div className="card">
          <div className="label">Chrome Processes</div>
          <div className="value">{mcp.server.chrome_processes}</div>
        </div>
        <div className="card">
          <div className="label">Runner Processes</div>
          <div className="value">{mcp.server.runner_processes}</div>
        </div>
        <div className="card">
          <div className="label">Validator Failed Recent</div>
          <div className="value">{validator.failed_recent}</div>
        </div>
        <div className="card">
          <div className="label">Validator Retried</div>
          <div className="value">{validator.retried_count}</div>
        </div>
        <div className="card">
          <div className="label">Validator Last Check</div>
          <div className="value">{validator.checked_at ? validator.checked_at.slice(11, 19) : "-"}</div>
        </div>
      </section>

      <h2 className="section-title">Top Errors</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Message</th>
            <th>Count</th>
            <th>Last Seen</th>
          </tr>
        </thead>
        <tbody>
          {mcp.top_errors.length === 0 ? (
            <tr>
              <td colSpan={3}>No recent errors</td>
            </tr>
          ) : (
            mcp.top_errors.map((row) => (
              <tr key={`${row.message}-${row.count}`}>
                <td>{row.message}</td>
                <td>{row.count}</td>
                <td>{row.last_seen_at ?? "-"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <h2 className="section-title">Validator Actions</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Site</th>
            <th>Run ID</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {validator.retried.length === 0 && validator.skipped.length === 0 ? (
            <tr>
              <td colSpan={4}>No recent validator actions</td>
            </tr>
          ) : (
            <>
              {validator.retried.map((row, idx) => (
                <tr key={`retried-${idx}-${row.failed_run_id ?? "-"}`}>
                  <td>retried</td>
                  <td>{row.site ?? "-"}</td>
                  <td>{row.failed_run_id ?? "-"}</td>
                  <td>transient error auto-retry</td>
                </tr>
              ))}
              {validator.skipped.map((row, idx) => (
                <tr key={`skipped-${idx}-${row.run_id ?? "-"}`}>
                  <td>skipped</td>
                  <td>{row.site ?? "-"}</td>
                  <td>{row.run_id ?? "-"}</td>
                  <td>{row.reason ?? "-"}</td>
                </tr>
              ))}
            </>
          )}
        </tbody>
      </table>

      <h2 className="section-title">Schedule</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Cron</th>
            <th>Command</th>
          </tr>
        </thead>
        <tbody>
          {schedule.items.length === 0 ? (
            <tr>
              <td colSpan={2}>No schedule found</td>
            </tr>
          ) : (
            schedule.items.map((row) => (
              <tr key={`${row.schedule}-${row.command}`}>
                <td>{row.schedule}</td>
                <td>{row.command}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <h2 className="section-title">Latest Site Status</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Site</th>
            <th>Status</th>
            <th>Last Run</th>
          </tr>
        </thead>
        <tbody>
          {overview.sites.map((site) => (
            <tr key={site.site}>
              <td>{site.site}</td>
              <td><span className={statusClass(site.latest_status)}>{site.latest_status}</span></td>
              <td>{site.last_run ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
