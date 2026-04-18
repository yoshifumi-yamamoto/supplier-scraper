import os
import json
import hashlib
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from scrapers.common.error_classifier import classify_error, is_transient_error
from scrapers.common.logging_utils import json_log
from scrapers.common.notifier import notify_chatwork

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
RUNS_TABLE = os.getenv("RUNS_TABLE", "scrape_runs")

LOOKBACK_MINUTES = int(os.getenv("VALIDATOR_LOOKBACK_MINUTES", "720"))
ALLOWLIST = {
    s.strip()
    for s in os.getenv(
        "VALIDATOR_SITE_ALLOWLIST",
        "mercari,yafuoku,yahoofleama,secondstreet,surugaya,hardoff,rakuma,kitamura,yodobashi",
    ).split(",")
    if s.strip()
}
AUTO_RETRY = os.getenv("VALIDATOR_AUTO_RETRY", "true").lower() == "true"
RETRY_MAX_PAGES = int(os.getenv("VALIDATOR_RETRY_MAX_PAGES", "1"))
AUTO_RETRY_ERROR_TYPES = {
    s.strip()
    for s in os.getenv(
        "VALIDATOR_AUTO_RETRY_ERROR_TYPES",
        "proxy,network,timeout,db_timeout",
    ).split(",")
    if s.strip()
}
STALE_RUNNING_MINUTES = int(os.getenv("VALIDATOR_STALE_RUNNING_MINUTES", "120"))
AI_NOTIFY_ENABLED = os.getenv("VALIDATOR_AI_NOTIFY_ENABLED", "true").lower() == "true"
AI_MODEL = os.getenv("VALIDATOR_OPENAI_MODEL", "gpt-5-mini")
AI_MAX_RUNS = int(os.getenv("VALIDATOR_AI_MAX_RUNS", "40"))
AI_NOTIFY_COOLDOWN_MINUTES = int(os.getenv("VALIDATOR_AI_NOTIFY_COOLDOWN_MINUTES", "360"))
AI_FAILURE_NOTIFY_MINUTES = int(os.getenv("VALIDATOR_AI_FAILURE_NOTIFY_MINUTES", "30"))
AI_NOTIFY_STATE_PATH = Path(os.getenv("VALIDATOR_AI_NOTIFY_STATE_PATH", "/tmp/validator_ai_notify_state.json"))
RETRY_COOLDOWN_MINUTES = int(os.getenv("VALIDATOR_RETRY_COOLDOWN_MINUTES", "60"))
RETRY_STATE_PATH = Path(os.getenv("VALIDATOR_RETRY_STATE_PATH", "/tmp/validator_retry_state.json"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MAX_OUTPUT_TOKENS = int(os.getenv("VALIDATOR_AI_MAX_OUTPUT_TOKENS", "1200"))
RUN_STEPS_TABLE = os.getenv("RUN_STEPS_TABLE", "scrape_run_steps")
VALIDATOR_RUN_FETCH_LIMIT = int(os.getenv("VALIDATOR_RUN_FETCH_LIMIT", "180"))
VALIDATOR_RUN_FETCH_RETRIES = int(os.getenv("VALIDATOR_RUN_FETCH_RETRIES", "3"))
VALIDATOR_RUN_STEPS_LIMIT = int(os.getenv("VALIDATOR_RUN_STEPS_LIMIT", "100"))


def _load_site_stale_overrides() -> dict[str, int]:
    overrides: dict[str, int] = {}
    raw = os.getenv(
        "VALIDATOR_STALE_RUNNING_MINUTES_BY_SITE",
        "mercari:360,yafuoku:360,yahoofleama:360",
    ).strip()
    if not raw:
        return overrides
    for chunk in raw.split(","):
        part = chunk.strip()
        if not part or ":" not in part:
            continue
        site, minutes = part.split(":", 1)
        site = site.strip()
        minutes = minutes.strip()
        if not site or not minutes:
            continue
        try:
            overrides[site] = int(minutes)
        except ValueError:
            continue
    return overrides


SITE_STALE_RUNNING_MINUTES = _load_site_stale_overrides()


def _stale_minutes_for_site(site: str | None) -> int:
    if not site:
        return STALE_RUNNING_MINUTES
    return SITE_STALE_RUNNING_MINUTES.get(site, STALE_RUNNING_MINUTES)

def _load_notify_state() -> dict[str, Any]:
    try:
        if AI_NOTIFY_STATE_PATH.exists():
            return json.loads(AI_NOTIFY_STATE_PATH.read_text())
    except Exception:
        pass
    return {}


def _save_notify_state(payload: dict[str, Any]) -> None:
    try:
        AI_NOTIFY_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception:
        pass


def _load_retry_state() -> dict[str, Any]:
    try:
        if RETRY_STATE_PATH.exists():
            return json.loads(RETRY_STATE_PATH.read_text())
    except Exception:
        pass
    return {}


def _save_retry_state(payload: dict[str, Any]) -> None:
    try:
        RETRY_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception:
        pass

def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


def _fetch_runs(limit: int | None = None) -> list[dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    window_start = (datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES + STALE_RUNNING_MINUTES)).isoformat()
    params = {
        "select": "id,site,status,error_summary,started_at,finished_at",
        "status": "in.(running,failed,error,success)",
        "started_at": f"gte.{window_start}",
        "order": "started_at.desc",
        "limit": str(limit or VALIDATOR_RUN_FETCH_LIMIT),
    }
    started = time.monotonic()
    last_exc: Exception | None = None
    for attempt in range(VALIDATOR_RUN_FETCH_RETRIES):
        try:
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/{RUNS_TABLE}",
                headers=_headers(),
                params=params,
                timeout=30,
            )
            if res.status_code >= 500:
                preview = res.text[:300].replace("\n", " ")
                raise requests.HTTPError(f"Supabase {res.status_code}: {preview}", response=res)
            res.raise_for_status()
            body = res.json()
            rows = body if isinstance(body, list) else []
            json_log(
                "info",
                "validator runs fetched",
                rows=len(rows),
                limit=params["limit"],
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            return rows
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == VALIDATOR_RUN_FETCH_RETRIES - 1:
                break
            time.sleep(1.5 * (2 ** attempt))
    raise RuntimeError(f"validator failed to fetch runs: {last_exc}")


def _fetch_run_steps(run_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    if not SUPABASE_URL or not SUPABASE_KEY or not run_id:
        return []
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/{RUN_STEPS_TABLE}",
        headers=_headers(),
        params={
            "select": "id,run_id,step_name,status,started_at,finished_at",
            "run_id": f"eq.{run_id}",
            "order": "started_at.desc",
            "limit": str(limit or VALIDATOR_RUN_STEPS_LIMIT),
        },
        timeout=30,
    )
    res.raise_for_status()
    body = res.json()
    return body if isinstance(body, list) else []


def _is_recent(ts: str | None, now_utc: datetime) -> bool:
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt >= now_utc - timedelta(minutes=LOOKBACK_MINUTES)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _minutes_since(ts: str | None, now_utc: datetime) -> int | None:
    dt = _parse_iso(ts)
    if not dt:
        return None
    return int((now_utc - dt).total_seconds() // 60)


def _is_transient(error_summary: str | None) -> bool:
    return is_transient_error(error_summary)


def _site_running(runs: list[dict[str, Any]], site: str) -> bool:
    now = datetime.now(timezone.utc)
    stale_minutes = _stale_minutes_for_site(site)
    for r in runs:
        if r.get("site") != site or r.get("status") != "running":
            continue
        last_activity = _parse_iso(r.get("_last_activity_at")) or _parse_iso(r.get("started_at"))
        # Ignore stale running records; they are handled by stale cleanup below.
        if last_activity and last_activity < now - timedelta(minutes=stale_minutes):
            continue
        return True
    return False


def _run_sort_key(run: dict[str, Any]) -> datetime:
    return _parse_iso(run.get("finished_at")) or _parse_iso(run.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc)


def _latest_run_by_site(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        site = run.get("site")
        if not site:
            continue
        current = latest.get(site)
        if current is None or _run_sort_key(run) > _run_sort_key(current):
            latest[site] = run
    return latest


def _site_process_running(site: str) -> bool:
    try:
        res = subprocess.run(
            ["ps", "-eo", "comm=,args="],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception:
        return False
    for line in (res.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if not (line.startswith("python ") or line.startswith("python3 ")):
            continue
        if "apps/runner/main.py" not in line:
            continue
        if f"--site {site}" in line:
            return True
    return False


def _compute_last_activity(run: dict[str, Any], run_steps: list[dict[str, Any]]) -> tuple[str | None, int | None]:
    candidates: list[datetime] = []
    for step in run_steps:
        finished = _parse_iso(step.get("finished_at"))
        started = _parse_iso(step.get("started_at"))
        if finished:
            candidates.append(finished)
        elif started:
            candidates.append(started)
    started_at = _parse_iso(run.get("started_at"))
    if started_at:
        candidates.append(started_at)
    if not candidates:
        return None, None
    last_dt = max(candidates)
    age_minutes = int((datetime.now(timezone.utc) - last_dt).total_seconds() // 60)
    return last_dt.isoformat(), age_minutes


def _attach_run_activity(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run in runs:
        row = dict(run)
        if row.get("status") == "running" and row.get("id"):
            try:
                steps = _fetch_run_steps(row["id"])
            except Exception as exc:  # noqa: BLE001
                json_log("warning", "failed to fetch run steps", run_id=row.get("id"), error=str(exc))
                steps = []
            last_activity_at, last_activity_minutes = _compute_last_activity(row, steps)
            row["_last_activity_at"] = last_activity_at
            row["_last_activity_minutes"] = last_activity_minutes
            row["_step_count"] = len(steps)
        out.append(row)
    return out


def _mark_run_failed(run_id: str, error_summary: str) -> None:
    payload = {
        "status": "failed",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error_summary": error_summary[:1000],
    }
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/{RUNS_TABLE}?id=eq.{run_id}",
        headers={**_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
        json=payload,
        timeout=20,
    ).raise_for_status()


def _retry_site(site: str) -> dict[str, Any]:
    payload = {
        "name": "retry_failed_step",
        "arguments": {"site": site, "max_pages": RETRY_MAX_PAGES},
    }
    res = requests.post(f"{MCP_BASE_URL}/mcp/call", json=payload, timeout=20)
    res.raise_for_status()
    return res.json()


def _extract_response_text(body: dict[str, Any]) -> str:
    text = body.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    parts: list[str] = []
    for item in body.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _parse_model_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    return json.loads(text)


def _call_openai_responses(prompt: str, signal: dict[str, Any]) -> str:
    res = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": AI_MODEL,
            "reasoning": {"effort": "low"},
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(signal, ensure_ascii=False)}]},
            ],
            "max_output_tokens": AI_MAX_OUTPUT_TOKENS,
        },
        timeout=45,
    )
    res.raise_for_status()
    return _extract_response_text(res.json())


def _call_openai_chat_completions(prompt: str, signal: dict[str, Any]) -> str:
    res = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": AI_MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(signal, ensure_ascii=False)},
            ],
            "max_tokens": AI_MAX_OUTPUT_TOKENS,
        },
        timeout=45,
    )
    res.raise_for_status()
    body = res.json()
    choices = body.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _build_ai_signal_payload(
    now: datetime,
    runs: list[dict[str, Any]],
    stale_marked: list[dict[str, Any]],
    failed_recent: list[dict[str, Any]],
    retries: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> dict[str, Any]:
    recent_running: list[dict[str, Any]] = []
    for run in runs:
        if run.get("status") != "running":
            continue
        started_at = _parse_iso(run.get("started_at"))
        age_minutes = None
        if started_at:
            age_minutes = int((now - started_at).total_seconds() // 60)
        recent_running.append(
            {
                "site": run.get("site"),
                "run_id": run.get("id"),
                "started_at": run.get("started_at"),
                "age_minutes": age_minutes,
                "last_activity_at": run.get("_last_activity_at"),
                "last_activity_minutes": run.get("_last_activity_minutes"),
                "step_count": run.get("_step_count"),
            }
        )

    trimmed_failed = []
    for run in failed_recent[:AI_MAX_RUNS]:
        finished_or_started = run.get("finished_at") or run.get("started_at")
        trimmed_failed.append(
            {
                "site": run.get("site"),
                "run_id": run.get("id"),
                "status": run.get("status"),
                "started_at": run.get("started_at"),
                "finished_at": run.get("finished_at"),
                "age_minutes": _minutes_since(finished_or_started, now),
                "error_type": classify_error(run.get("error_summary")),
                "error_summary": (run.get("error_summary") or "")[:400],
            }
        )

    return {
        "checked_at": now.isoformat(),
        "stale_running_minutes_default": STALE_RUNNING_MINUTES,
        "stale_running_minutes_by_site": SITE_STALE_RUNNING_MINUTES,
        "stale_marked": stale_marked[:AI_MAX_RUNS],
        "failed_recent": trimmed_failed,
        "running_sites": recent_running[:AI_MAX_RUNS],
        "retries": retries[:AI_MAX_RUNS],
        "skipped": skipped[:AI_MAX_RUNS],
    }


def _build_ai_notification_fingerprint(
    stale_marked: list[dict[str, Any]],
    failed_recent: list[dict[str, Any]],
    retries: list[dict[str, Any]],
) -> str:
    fingerprint_payload = {
        "stale_marked": [
            {
                "site": item.get("site"),
                "reason": "stale_running",
            }
            for item in stale_marked[:AI_MAX_RUNS]
        ],
        "failed_recent": [
            {
                "site": run.get("site"),
                "error_type": classify_error(run.get("error_summary")),
            }
            for run in failed_recent[:AI_MAX_RUNS]
        ],
        "retries": [
            {
                "site": item.get("site"),
                "error_type": item.get("error_type"),
            }
            for item in retries[:AI_MAX_RUNS]
        ],
    }
    return hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _include_failed_run_in_ai(run: dict[str, Any], runs: list[dict[str, Any]], now: datetime) -> bool:
    age_minutes = _minutes_since(run.get("finished_at") or run.get("started_at"), now)
    if (age_minutes or 10**9) > AI_FAILURE_NOTIFY_MINUTES:
        return False
    site = run.get("site") or "unknown"
    if _is_transient(run.get("error_summary")) and _site_running(runs, site):
        return False
    return True


def _retry_fingerprint(site: str, error_summary: str | None) -> str:
    base = f"{site}\n{(error_summary or '').strip()[:500]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _should_skip_retry(site: str, error_summary: str | None, now: datetime) -> bool:
    state = _load_retry_state()
    if state.get("site") != site:
        return False
    if state.get("fingerprint") != _retry_fingerprint(site, error_summary):
        return False
    retried_at = _parse_iso(state.get("retried_at"))
    if not retried_at:
        return False
    return retried_at >= now - timedelta(minutes=RETRY_COOLDOWN_MINUTES)


def _record_retry(site: str, run_id: str | None, error_summary: str | None, now: datetime) -> None:
    _save_retry_state(
        {
            "site": site,
            "run_id": run_id,
            "fingerprint": _retry_fingerprint(site, error_summary),
            "retried_at": now.isoformat(),
        }
    )


def _should_suppress_ai_notification(fingerprint: str, now: datetime) -> bool:
    state = _load_notify_state()
    if state.get("fingerprint") != fingerprint:
        return False
    notified_at = _parse_iso(state.get("notified_at"))
    if not notified_at:
        return False
    return notified_at >= now - timedelta(minutes=AI_NOTIFY_COOLDOWN_MINUTES)


def _record_ai_notification(fingerprint: str, now: datetime, message: str) -> None:
    _save_notify_state(
        {
            "fingerprint": fingerprint,
            "notified_at": now.isoformat(),
            "message": message[:2000],
        }
    )


def _ai_notify_decision(
    now: datetime,
    runs: list[dict[str, Any]],
    stale_marked: list[dict[str, Any]],
    failed_recent: list[dict[str, Any]],
    retries: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not AI_NOTIFY_ENABLED or not OPENAI_API_KEY:
        return None

    ai_failed_recent = [run for run in failed_recent if _include_failed_run_in_ai(run, runs, now)]
    if not stale_marked and not retries and not ai_failed_recent:
        return {"notify": False, "reason": "no_fresh_incident"}

    signal = _build_ai_signal_payload(now, runs, stale_marked, ai_failed_recent, retries, skipped)
    fingerprint = _build_ai_notification_fingerprint(stale_marked, ai_failed_recent, retries)
    if _should_suppress_ai_notification(fingerprint, now):
        return {"notify": False, "reason": "cooldown", "fingerprint": fingerprint}

    prompt = (
        "You are an operations incident detector for an e-commerce scraping system. "
        "Decide whether the current state merits a Chatwork alert to a human operator. "
        "Notify when there is a meaningful operational issue such as stale runs, repeated failures, "
        "unexpected long-running jobs, or suspicious conditions likely needing human attention. "
        "Do not notify for healthy or expected states. "
        "A long-running job with recent step activity is usually expected and should not be alerted just for duration.\n\n"
        "Return JSON only with keys: notify (boolean), severity (low|medium|high), "
        "title (string), message (string), reasons (array of short strings).\n"
        "The message must be concise Japanese for Chatwork and include concrete site names and why it matters."
    )
    raw = _call_openai_responses(prompt, signal)
    if not raw:
        raw = _call_openai_chat_completions(prompt, signal)
    if not raw:
        raise RuntimeError("OpenAI response was empty")
    decision = _parse_model_json(raw)
    decision["fingerprint"] = fingerprint
    return decision


def _maybe_notify_ai(
    now: datetime,
    runs: list[dict[str, Any]],
    stale_marked: list[dict[str, Any]],
    failed_recent: list[dict[str, Any]],
    retries: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        decision = _ai_notify_decision(now, runs, stale_marked, failed_recent, retries, skipped)
    except Exception as exc:  # noqa: BLE001
        json_log("warning", "validator ai decision failed", error=str(exc))
        return {"status": "error", "error": str(exc)}

    if not decision:
        return None
    if not decision.get("notify"):
        return {"status": "skipped", "reason": decision.get("reason") or "model_declined"}

    title = (decision.get("title") or "Validator Alert").strip()
    message = (decision.get("message") or "").strip()
    if not message:
        return {"status": "skipped", "reason": "empty_message"}
    notify_chatwork(f"[AI] {title}\n{message}")
    _record_ai_notification(decision.get("fingerprint") or "", now, message)
    return {
        "status": "sent",
        "severity": decision.get("severity"),
        "title": title,
        "reasons": decision.get("reasons") or [],
    }


def run_validator() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    runs = _attach_run_activity(_fetch_runs())
    stale_marked: list[dict[str, Any]] = []
    stale_skipped_active: list[dict[str, Any]] = []

    for r in runs:
        if r.get("status") != "running":
            continue
        site = r.get("site") or "unknown"
        stale_minutes = _stale_minutes_for_site(site)
        dt = _parse_iso(r.get("_last_activity_at")) or _parse_iso(r.get("started_at"))
        if not dt:
            continue
        if dt >= now - timedelta(minutes=stale_minutes):
            continue
        run_id = r.get("id")
        if not run_id:
            continue
        if _site_process_running(site):
            stale_skipped_active.append(
                {
                    "site": site,
                    "run_id": run_id,
                    "last_activity_at": r.get("_last_activity_at"),
                    "last_activity_minutes": r.get("_last_activity_minutes"),
                    "stale_minutes": stale_minutes,
                    "reason": "process_still_running",
                }
            )
            continue
        try:
            _mark_run_failed(run_id, f"auto-marked failed by validator: no step activity over {stale_minutes}m")
            stale_marked.append(
                {
                    "site": site,
                    "run_id": run_id,
                    "last_activity_at": r.get("_last_activity_at"),
                    "last_activity_minutes": r.get("_last_activity_minutes"),
                    "stale_minutes": stale_minutes,
                }
            )
        except Exception as exc:  # noqa: BLE001
            json_log("warning", "failed to mark stale running", site=site, run_id=run_id, error=str(exc))

    if stale_marked:
        runs = _attach_run_activity(_fetch_runs())

    latest_by_site = _latest_run_by_site(runs)
    failed_recent = [
        r for r in runs
        if (r.get("status") in ("failed", "error"))
        and ((not ALLOWLIST) or r.get("site") in ALLOWLIST)
        and _is_recent(r.get("finished_at") or r.get("started_at"), now)
        and latest_by_site.get(r.get("site"), {}).get("id") == r.get("id")
    ]

    retries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    processed_failed_sites: set[str] = set()

    for run in failed_recent:
        site = run.get("site") or "unknown"
        run_id = run.get("id")
        err = run.get("error_summary")

        if site in processed_failed_sites:
            skipped.append({"site": site, "run_id": run_id, "reason": "duplicate_failed_site", "error_type": classify_error(err)})
            continue
        processed_failed_sites.add(site)

        if not _is_transient(err):
            skipped.append({"site": site, "run_id": run_id, "reason": "non_transient_error", "error_type": classify_error(err)})
            continue

        error_type = classify_error(err)
        if AUTO_RETRY_ERROR_TYPES and error_type not in AUTO_RETRY_ERROR_TYPES:
            skipped.append({"site": site, "run_id": run_id, "reason": "retry_error_type_blocked", "error_type": error_type})
            continue

        if _site_running(runs, site):
            skipped.append({"site": site, "run_id": run_id, "reason": "site_running", "error_type": classify_error(err)})
            continue

        if not AUTO_RETRY:
            skipped.append({"site": site, "run_id": run_id, "reason": "auto_retry_disabled", "error_type": classify_error(err)})
            continue

        if _should_skip_retry(site, err, now):
            skipped.append({"site": site, "run_id": run_id, "reason": "retry_cooldown", "error_type": classify_error(err)})
            continue

        try:
            result = _retry_site(site)
            _record_retry(site, run_id, err, now)
            retries.append({"site": site, "failed_run_id": run_id, "error_type": classify_error(err), "retry_result": result})
            json_log(
                "info",
                "validator auto-retry triggered",
                site=site,
                failed_run_id=run_id,
                error_type=classify_error(err),
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append({"site": site, "run_id": run_id, "reason": f"retry_failed: {exc}", "error_type": classify_error(err)})
            json_log(
                "warning",
                "validator retry failed",
                site=site,
                failed_run_id=run_id,
                error=str(exc),
                error_type=classify_error(err),
            )

    ai_notification = _maybe_notify_ai(now, runs, stale_marked, failed_recent, retries, skipped)

    report = {
        "checked_at": now.isoformat(),
        "lookback_minutes": LOOKBACK_MINUTES,
        "stale_running_marked": stale_marked,
        "failed_recent": len(failed_recent),
        "retried": retries,
        "skipped": skipped,
        "stale_skipped_active": stale_skipped_active,
        "ai_notification": ai_notification,
    }
    json_log("info", "validator run finished", **report)
    return report


if __name__ == "__main__":
    run_validator()
