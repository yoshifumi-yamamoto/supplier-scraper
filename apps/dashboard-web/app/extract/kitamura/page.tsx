import Link from "next/link";

import { KitamuraExtractPanel } from "@/components/kitamura-extract-panel";

export default function KitamuraExtractPage() {
  return (
    <main className="dashboard">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">K</div>
          <div>
            <h1>Kitamura Extract</h1>
            <p>商品一覧URLから商品情報を抽出します。中古は最上位コンディションを選択します。</p>
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
        <KitamuraExtractPanel />
      </section>
    </main>
  );
}
