import Link from "next/link";

import { MercariExtractPanel } from "@/components/mercari-extract-panel";

export default function MercariExtractPage() {
  return (
    <main className="dashboard">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">S</div>
          <div>
            <h1>Mercari Extract</h1>
            <p>検索結果URLから商品情報を抽出します。</p>
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
        <MercariExtractPanel />
      </section>
    </main>
  );
}
