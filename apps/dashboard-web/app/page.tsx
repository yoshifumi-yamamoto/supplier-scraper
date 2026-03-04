import { fetchOverview } from "@/lib/api";

function statusClass(status: string) {
  return status === "success" ? "badge badge-ok" : "badge badge-ng";
}

export default async function Page() {
  const overview = await fetchOverview();

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
      </section>

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
