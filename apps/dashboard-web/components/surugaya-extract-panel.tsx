"use client";

import { useEffect, useMemo, useState } from "react";
import { clientApiBase } from "@/lib/api";

const API_BASE = clientApiBase();

type HistoryItem = { filename: string; display_name?: string; download_url?: string | null; status?: string; extracted_count?: number; skip_count?: number; page?: number };

export function SurugayaExtractPanel() {
  const [searchUrl, setSearchUrl] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [maxPages, setMaxPages] = useState("");
  const [maxItems, setMaxItems] = useState("400");
  const [activeJob, setActiveJob] = useState<any>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [message, setMessage] = useState("");
  const [stopping, setStopping] = useState(false);
  const [selected, setSelected] = useState<HistoryItem | null>(null);

  async function refresh() {
    const [s, h] = await Promise.all([
      fetch(`${API_BASE}/api/extract/surugaya/status`, { cache: "no-store" }),
      fetch(`${API_BASE}/api/extract/surugaya/history`, { cache: "no-store" }),
    ]);
    const sj = await s.json();
    const hj = await h.json();
    setActiveJob(sj.active_job || null);
    setHistory(hj.items || []);
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);

  const isRunning = !!activeJob;
  const selectedHistory = selected || history[0] || null;

  async function onStart() {
    setMessage("");
    const res = await fetch(`${API_BASE}/api/extract/surugaya/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        search_url: searchUrl,
        display_name: displayName,
        max_pages: maxPages ? Number(maxPages) : 0,
        max_items: maxItems ? Number(maxItems) : 400,
        headless: true,
      }),
    });
    const body = await res.json();
    if (!res.ok) {
      setMessage(body.detail || "start failed");
      return;
    }
    setMessage("抽出を開始しました");
    await refresh();
  }

  async function onDelete() {
    if (!selectedHistory) return;
    if (!confirm(`削除しますか: ${selectedHistory.filename}`)) return;
    const res = await fetch(`${API_BASE}/api/extract/surugaya/history/${selectedHistory.filename}`, { method: "DELETE" });
    if (!res.ok) {
      const body = await res.json();
      setMessage(body.detail || "delete failed");
      return;
    }
    setSelected(null);
    await refresh();
  }

  async function onStop() {
    if (!activeJob) return;
    if (!confirm("途中までのCSVを残したまま抽出を中止します。実行しますか。")) return;
    setStopping(true);
    setMessage("");
    const res = await fetch(`${API_BASE}/api/extract/surugaya/stop`, { method: "POST" });
    const body = await res.json();
    if (!res.ok) {
      setMessage(body.detail || "stop failed");
      setStopping(false);
      return;
    }
    setMessage("抽出を中止しました。途中までのCSVを保持しています。");
    setStopping(false);
    await refresh();
  }

  return (
    <div className="extract-panel">
      <div className="extract-form-grid">
        <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="抽出ファイル名" />
        <input value={searchUrl} onChange={(e) => setSearchUrl(e.target.value)} placeholder="一覧URL" />
        <input value={maxPages} onChange={(e) => setMaxPages(e.target.value)} placeholder="最大ページ数（未設定で上限なし）" />
        <input value={maxItems} onChange={(e) => setMaxItems(e.target.value)} placeholder="最大件数" />
        <button onClick={onStart} disabled={isRunning || !displayName || !searchUrl}>スタート</button>
      </div>
      {message ? <p>{message}</p> : null}
      {activeJob ? <div className="ops-card"><p>抽出ジョブが実行中です。</p><h4>{activeJob.progress?.extracted_count ?? 0}件</h4><p>page {activeJob.progress?.page ?? 0} / skip {activeJob.progress?.skip_count ?? 0}</p><button onClick={onStop} disabled={stopping}>{stopping ? "中止中..." : "途中で中止"}</button></div> : null}
      <div className="panel-head"><h3>履歴</h3><span>{history.length}件</span></div>
      <div className="list">
        {history.map((row) => (
          <button key={row.filename} className="list-item" onClick={() => setSelected(row)}>
            <p>{row.display_name || row.filename}</p>
            <div><span>{row.status === "cancelled" ? "中止" : (row.status || '-')}</span><span>{row.extracted_count ?? 0}件</span></div>
          </button>
        ))}
      </div>
      {selectedHistory ? <div className="ops-grid"><div className="ops-card"><p>CSV</p><h4>{selectedHistory.filename}</h4></div><div className="ops-card"><p>抽出件数</p><h4>{selectedHistory.extracted_count ?? 0}</h4></div><div className="ops-card"><p>スキップ</p><h4>{selectedHistory.skip_count ?? 0}</h4></div><div className="ops-card"><p>ページ</p><h4>{selectedHistory.page ?? 0}</h4></div>{selectedHistory.download_url ? <a className="extract-link-button" href={`${API_BASE}${selectedHistory.download_url}`}>CSVダウンロード</a> : null}<button onClick={onDelete}>削除</button></div> : null}
    </div>
  );
}
