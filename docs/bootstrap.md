# Bootstrap

## 1) runner 実行
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
PYTHONPATH=. python3 apps/runner/main.py --site yahoofleama
```

## 2) dashboard-api 起動
```bash
cd /Users/yamamotoyoshifumi/projects/ebay/supplier-scraper-main
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn apps.dashboard_api.main:app --reload --host 0.0.0.0 --port 8080
```

## 3) legacy取り込み（任意）
既存コードは `/Users/yamamotoyoshifumi/projects/ebay/supplier-scraper` を参照し、
サイト単位で `legacy/` へコピーして段階移植する。
