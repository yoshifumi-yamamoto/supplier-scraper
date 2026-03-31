import Link from "next/link";

import { SurugayaExtractPanel } from "@/components/surugaya-extract-panel";

export default function SurugayaExtractPage() {
  return (
    <main className="dashboard">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">S</div>
          <div>
            <h1>Surugaya Extract</h1>
            <p>検索一覧から商品詳細を辿ってCSVを生成します。`/product/other/` は先頭候補を選びます。</p>
          </div>
        </div>
        <div className="top-tags">
          <Link className="tag" href="/extract">
            抽出トップへ戻る
          </Link>
          <Link className="tag" href="/">
            ダッシュボードへ戻る
          </Link>
        </div>
      </header>

      <section className="extract-page-grid">
        <SurugayaExtractPanel />
      </section>
    </main>
  );
}
