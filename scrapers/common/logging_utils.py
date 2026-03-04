import json
from datetime import datetime, timezone


def json_log(level: str, message: str, **context: object) -> str:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "context": context,
    }
    line = json.dumps(payload, ensure_ascii=False)
    print(line)
    return line
