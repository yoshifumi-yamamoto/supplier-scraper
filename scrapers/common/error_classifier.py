from typing import Final


DB_TIMEOUT_PATTERNS: Final[tuple[str, ...]] = (
    "57014",
    "statement timeout",
    "canceling statement due to statement timeout",
    "read timed out",
    "readtimeout",
    "supabase 500",
    "supabase 502",
)

PROXY_PATTERNS: Final[tuple[str, ...]] = (
    "proxy",
    "tunnel connection failed",
    "cannot connect to proxy",
)

NETWORK_PATTERNS: Final[tuple[str, ...]] = (
    "connection reset",
    "connection aborted",
    "name or service not known",
    "temporary failure in name resolution",
    "max retries exceeded",
    "remote end closed connection",
)

SELECTOR_PATTERNS: Final[tuple[str, ...]] = (
    "no such element",
    "stale element reference",
    "invalid selector",
    "element not interactable",
)

TIMEOUT_PATTERNS: Final[tuple[str, ...]] = (
    "timeout",
    "timed out",
    "timeouterror",
)


def classify_error(error: str | None) -> str:
    text = (error or "").lower()
    if not text.strip():
        return "unknown"
    if any(pattern in text for pattern in DB_TIMEOUT_PATTERNS):
        return "db_timeout"
    if any(pattern in text for pattern in PROXY_PATTERNS):
        return "proxy"
    if any(pattern in text for pattern in NETWORK_PATTERNS):
        return "network"
    if any(pattern in text for pattern in SELECTOR_PATTERNS):
        return "selector"
    if any(pattern in text for pattern in TIMEOUT_PATTERNS):
        return "timeout"
    return "unknown"


def is_transient_error(error: str | None) -> bool:
    return classify_error(error) in {"db_timeout", "proxy", "network", "timeout"}
