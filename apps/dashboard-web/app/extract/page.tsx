import Link from "next/link";

const tools = [
  {
    name: "Mercari Extract",
    description: "検索結果URLから商品情報CSVを生成します。",
    href: "/extract/mercari",
    status: "available",
  },
  {
    name: "Kitamura Extract",
    description: "商品一覧URLから新品・中古の分岐を吸収してCSVを生成します。",
    href: "/extract/kitamura",
    status: "available",
  },
  {
    name: "Surugaya Extract",
    description: "検索一覧から詳細ページを辿り、`other` 詳細は先頭候補を選んでCSVを生成します。",
    href: "/extract/surugaya",
    status: "available",
  },
  {
    name: "Yahoo Fleamarket Extract",
    description: "今後追加予定です。",
    href: "#",
    status: "planned",
  },
  {
    name: "2ndStreet Extract",
    description: "今後追加予定です。",
    href: "#",
    status: "planned",
  },
];

export default function ExtractHubPage() {
  return (
    <main className="dashboard">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">E</div>
          <div>
            <h1>Market Pilot Extract</h1>
            <p>商品抽出ツールのハブです。サイトごとに実行UIを分けます。</p>
          </div>
        </div>
        <div className="top-tags">
          <Link className="tag" href="/">ダッシュボードへ戻る</Link>
        </div>
      </header>

      <section className="extract-hub-grid">
        {tools.map((tool) => (
          <article key={tool.name} className="extract-hub-card">
            <div className="panel-head">
              <h3>{tool.name}</h3>
              <span className={`pill ${tool.status === "available" ? "pill-ok" : "pill-warn"}`}>
                {tool.status === "available" ? "利用可能" : "準備中"}
              </span>
            </div>
            <p className="action-copy">{tool.description}</p>
            {tool.status === "available" ? (
              <Link className="extract-link-button" href={tool.href}>
                開く
              </Link>
            ) : (
              <span className="extract-link-button extract-link-disabled">近日追加</span>
            )}
          </article>
        ))}
      </section>
    </main>
  );
}
