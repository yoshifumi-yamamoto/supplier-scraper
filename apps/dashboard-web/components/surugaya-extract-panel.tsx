"use client";

import { useEffect, useMemo, useState } from "react";
import { clientApiBase } from "@/lib/api";

const API_BASE = clientApiBase();

type ExtractJob = {
  accepted?: boolean;
  pid: number;
  display_name?: string;
  output_name?: string;
  output_path: string;
  log_path: string;
  search_url?: string;
  max_pages?: number;
  max_items?: number;
  started_at?: string;
  status?: string;
  filename?: string;
  download_url?: string | null;
  progress?: {
    status?: string;
    page?: number;
    extracted_count?: number;
    skip_count?: number;
    message?: string;
  } | null;
};

type StatusResponse = {
  active_job: ExtractJob | null;
};

type HistoryResponse = {
  items: ExtractJob[];
};

function fmt(ts?: string) {
  if (!ts) return "-";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("ja-JP", { hour12: false });
}

function progressMetrics(job?: ExtractJob | null) {
  const extracted = job?.progress?.extracted_count ?? 0;
  const skipped = job?.progress?.skip_count ?? 0;
  const attempts = extracted + skipped;
  const successRate = attempts > 0 ? Math.round((extracted / attempts) * 100) : 0;
  const maxItems = job?.max_items ?? 0;
  const remaining = maxItems > 0 ? Math.max(maxItems - extracted, 0) : null;
  return { extracted, skipped, attempts, successRate, remaining };
}

export function SurugayaExtractPanel() {
  const [searchUrl, setSearchUrl] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [maxPages, setMaxPages] = useState("");
  const [maxItems, setMaxItems] = useState("400");
  const [loading, setLoading] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ExtractJob | null>(null);
  const [activeJob, setActiveJob] = useState<ExtractJob | null>(null);
  const [history, setHistory] = useState<ExtractJob[]>([]);
  const [selectedFile, setSelectedFile] = useState("");

  async function refresh() {
    const [statusRes, historyRes] = await Promise.all([
      fetch(`${API_BASE}/api/extract/surugaya/status`, { cache: "no-store" }),
      fetch(`${API_BASE}/api/extract/surugaya/history`, { cache: "no-store" }),
    ]);
    const statusData: StatusResponse = await statusRes.json();
    const historyData: HistoryResponse = await historyRes.json();
    setActiveJob(statusData.active_job);
    setHistory(historyData.items ?? []);
    const nextSelected =
      selectedFile && historyData.items?.some((row) => row.filename === selectedFile)
        ? selectedFile
        : (historyData.items?.[0]?.filename ?? "");
    setSelectedFile(nextSelected);
  }

  useEffect(() => {
    refresh().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!activeJob) return;
    const timer = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [activeJob]);

  const selectedHistory = useMemo(
    () => history.find((row) => row.filename === selectedFile) ?? null,
    [history, selectedFile],
  );
  const activeMetrics = progressMetrics(activeJob);
  const historyMetrics = progressMetrics(selectedHistory);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/extract/surugaya/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          search_url: searchUrl,
          display_name: displayName,
          max_pages: Number(maxPages) || 0,
          max_items: Number(maxItems) || 400,
          headless: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const detail = typeof data.detail === "string" ? data.detail : data.detail?.message;
        throw new Error(detail ?? "failed to start extract");
      }
      setResult(data);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to start extract");
    } finally {
      setLoading(false);
    }
  }

  async function onDelete() {
    if (!selectedHistory?.filename) return;
    const targetName = selectedHistory.display_name ?? selectedHistory.filename;
    if (!window.confirm(`抽出履歴 ${targetName} を削除します。CSVとログも削除されます。`)) return;
    setDeleting(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/extract/surugaya/history/${selectedHistory.filename}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "failed to delete history");
      }
      setResult(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to delete history");
    } finally {
      setDeleting(false);
    }
  }

  async function onStop() {
    if (!activeJob) return;
    if (!window.confirm("途中までのCSVを残したまま抽出を中止します。実行しますか。")) return;
    setStopping(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/extract/surugaya/stop`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail ?? "failed to stop extract");
      }
      setResult(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to stop extract");
    } finally {
      setStopping(false);
    }
  }

  const disabled = loading || Boolean(activeJob);

  return (
    <article className="panel extract-panel">
      <div className="panel-head">
        <h3>Surugaya 抽出</h3>
        <span>検索URLからCSVを生成</span>
      </div>

      <form className="extract-form" onSubmit={onSubmit}>
        <label className="extract-field">
          <span>検索URL</span>
          <input
            type="url"
            required
            placeholder="https://www.suruga-ya.jp/search?..."
            value={searchUrl}
            onChange={(e) => setSearchUrl(e.target.value)}
          />
        </label>

        <label className="extract-field">
          <span>抽出名</span>
          <input
            type="text"
            required
            placeholder="AUTOart 1/18 ダイキャスト"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </label>

        <div className="extract-row">
          <label className="extract-field">
            <span>最大ページ数</span>
            <input
              type="number"
              min="0"
              max="100"
              placeholder="未設定で上限なし"
              value={maxPages}
              onChange={(e) => setMaxPages(e.target.value)}
            />
          </label>

          <label className="extract-field">
            <span>最大件数</span>
            <input
              type="number"
              min="1"
              max="10000"
              value={maxItems}
              onChange={(e) => setMaxItems(e.target.value)}
            />
          </label>
        </div>

        <button className="extract-button" type="submit" disabled={disabled}>
          {loading ? "起動中..." : activeJob ? "抽出実行中" : "スタート"}
        </button>
      </form>

      {activeJob ? (
        <div className="extract-result">
          <p>抽出ジョブが実行中です。</p>
          <p>開始: {fmt(activeJob.started_at)}</p>
          <p>PID: {activeJob.pid}</p>
          <p>CSV: {activeJob.output_path}</p>
          <p>抽出件数: {activeMetrics.extracted}</p>
          <p>スキップ件数: {activeMetrics.skipped}</p>
          <p>成功率: {activeMetrics.successRate}%</p>
          <p>残り件数目安: {activeMetrics.remaining ?? "-"}</p>
          <p>処理ページ: {activeJob.progress?.page ?? 0}</p>
          {activeJob.progress?.message ? <p>進捗: {activeJob.progress.message}</p> : null}
          <div className="extract-actions">
            <button className="extract-delete-button" type="button" onClick={onStop} disabled={stopping}>
              {stopping ? "中止中..." : "途中で中止"}
            </button>
          </div>
        </div>
      ) : null}

      {error ? <p className="extract-error">{error}</p> : null}
      {result ? (
        <div className="extract-result">
          <p>抽出ジョブを開始しました。</p>
          <p>PID: {result.pid}</p>
          <p>CSV: {result.output_path}</p>
          <p>LOG: {result.log_path}</p>
        </div>
      ) : null}

      <div className="extract-history">
        <div className="panel-head">
          <h3>抽出履歴</h3>
          <span>{history.length}件</span>
        </div>

        <label className="extract-field">
          <span>履歴ファイル</span>
          <select
            value={selectedFile}
            onChange={(e) => setSelectedFile(e.target.value)}
            disabled={history.length === 0}
          >
            <option value="">選択してください</option>
            {history.map((row) => (
              <option key={row.filename ?? row.output_path} value={row.filename ?? ""}>
                {row.display_name ?? row.filename} /{" "}
                {row.status === "completed"
                  ? "完了"
                  : row.status === "running"
                    ? "実行中"
                    : row.status === "cancelled"
                      ? "中止"
                      : "失敗"}
              </option>
            ))}
          </select>
        </label>

        {selectedHistory ? (
          <div className="extract-result">
            <p>開始: {fmt(selectedHistory.started_at)}</p>
            <p>状態: {selectedHistory.status ?? "-"}</p>
            <p>抽出件数: {historyMetrics.extracted}</p>
            <p>スキップ件数: {historyMetrics.skipped}</p>
            <p>成功率: {historyMetrics.successRate}%</p>
            <p>残り件数目安: {historyMetrics.remaining ?? "-"}</p>
            <p>最終ページ: {selectedHistory.progress?.page ?? 0}</p>
            <p>CSV: {selectedHistory.output_path}</p>
            <p>LOG: {selectedHistory.log_path}</p>
            <div className="extract-actions">
              {selectedHistory.download_url ? (
                <a
                  className="extract-link-button"
                  href={`${API_BASE}${selectedHistory.download_url}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  CSVをダウンロード
                </a>
              ) : null}
              <button
                className="extract-delete-button"
                type="button"
                onClick={onDelete}
                disabled={deleting || selectedHistory.status === "running"}
              >
                {deleting ? "削除中..." : "履歴を削除"}
              </button>
            </div>
          </div>
        ) : (
          <p className="action-copy">履歴からCSVを選ぶと、後からダウンロードできます。</p>
        )}
      </div>
    </article>
  );
}
