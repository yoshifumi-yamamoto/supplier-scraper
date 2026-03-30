def describe_exception(exc: Exception) -> str:
    text = str(exc).strip()
    if text and text != "Message:":
        return text

    msg = getattr(exc, "msg", None)
    if isinstance(msg, str) and msg.strip():
        return msg.strip()

    args = getattr(exc, "args", ())
    if args:
        parts = [str(part).strip() for part in args if str(part).strip()]
        if parts:
            return " | ".join(parts)

    return f"{exc.__class__.__name__}: {exc!r}"
