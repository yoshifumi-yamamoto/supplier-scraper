import { SurugayaExtractPanel } from "@/components/surugaya-extract-panel";

export default function SurugayaExtractPage() {
  return (
    <main className="dashboard">
      <div className="panel">
        <div className="panel-head">
          <h3>Surugaya Extract</h3>
          <span>一覧 -&gt; 詳細 -&gt; 次ページ</span>
        </div>
        <p className="action-copy">
          検索一覧から商品詳細を辿って CSV を生成します。`/product/other/` は先頭の詳細候補を選びます。
        </p>
        <SurugayaExtractPanel />
      </div>
    </main>
  );
}
