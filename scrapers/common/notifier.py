import os
from datetime import datetime, timezone

import requests


def _is_enabled() -> bool:
    return os.getenv("CHATWORK_NOTIFY_ENABLED", "false").lower() == "true"


def notify_chatwork(message: str) -> None:
    if not _is_enabled():
        return

    token = os.getenv("CHATWORK_API_TOKEN")
    room_id = os.getenv("CHATWORK_ROOM_ID")
    if not token or not room_id:
        return

    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    headers = {"X-ChatWorkToken": token}
    body = f"[info][title]Supplier Scraper Alert[/title]{message}[/info]"
    try:
        requests.post(url, headers=headers, data={"body": body}, timeout=15)
    except Exception:
        # Notification failure must not break the scraper runner.
        return


def build_failure_message(site: str, run_id: str, error: str) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    return (
        f"UTC: {ts}\n"
        f"site: {site}\n"
        f"run_id: {run_id}\n"
        f"status: failed\n"
        f"error: {error}"
    )

