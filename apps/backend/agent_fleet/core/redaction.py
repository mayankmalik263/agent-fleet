"""Remove secrets, hidden reasoning and oversized values before data is stored or logged."""

import re
from typing import Any

MAX_STRING = 4_000
MAX_DEPTH = 8
MAX_ITEMS = 200

# A key ending in "token" (token, access_token, accessToken) is secret; usage counters such as input_tokens
# end in "tokens" and stay visible.
_SECRET_KEY = re.compile(
    r"(api[_-]?key|secret|password|passwd|authorization|cookie|credential|session[_-]?key|private[_-]?key|token$)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(sk-ant-[A-Za-z0-9_\-]{8,}|sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._\-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}|AKIA[0-9A-Z]{16}|xox[abposr]-[A-Za-z0-9\-]{10,})"
)
# Keys that hold model reasoning. Agent Fleet never stores hidden reasoning.
_REASONING_KEYS = {"thinking", "redacted_thinking", "reasoning", "signature"}

REDACTED = "[redacted]"


def redact_text(value: str, limit: int = MAX_STRING) -> str:
    value = _SECRET_VALUE.sub(REDACTED, value)
    if len(value) > limit:
        return value[:limit] + f"... [truncated {len(value) - limit} chars]"
    return value


def sanitize(value: Any, *, depth: int = 0) -> Any:
    """Return a JSON-safe copy of value with secrets and reasoning removed."""
    if depth > MAX_DEPTH:
        return "[max depth]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for i, (key, item) in enumerate(value.items()):
            if i >= MAX_ITEMS:
                out["_truncated_keys"] = len(value) - MAX_ITEMS
                break
            key = str(key)
            if key in _REASONING_KEYS:
                continue
            out[key] = REDACTED if _SECRET_KEY.search(key) else sanitize(item, depth=depth + 1)
        return out
    if isinstance(value, list | tuple):
        items = [sanitize(v, depth=depth + 1) for v in list(value)[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            items.append(f"[{len(value) - MAX_ITEMS} more items]")
        return items
    if isinstance(value, str):
        return redact_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return redact_text(str(value))
