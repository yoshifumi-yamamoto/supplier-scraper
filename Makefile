.PHONY: run-yahoofleama api

run-yahoofleama:
	PYTHONPATH=. python3 apps/runner/main.py --site yahoofleama

api:
	uvicorn apps.dashboard_api.main:app --reload --host 0.0.0.0 --port 8080
