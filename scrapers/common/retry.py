import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry_with_backoff(fn: Callable[[], T], retries: int = 3, base_seconds: float = 1.5) -> T:
    last_error = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == retries - 1:
                break
            sleep_sec = base_seconds * (2 ** attempt) + random.uniform(0.2, 0.8)
            time.sleep(sleep_sec)
    raise last_error
