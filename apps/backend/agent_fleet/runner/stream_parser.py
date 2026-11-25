"""Incremental parser for Claude Code `--output-format stream-json` (newline-delimited JSON).

feed() accepts raw bytes in any chunk size and returns the complete messages found so far. A line that
is not valid JSON, or not a JSON object, becomes a ParseIssue instead of stopping the stream.
"""

import json
from dataclasses import dataclass
from typing import Any

MAX_LINE_BYTES = 32 * 1024 * 1024


@dataclass
class ParseIssue:
    reason: str
    preview: str


class NdjsonParser:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[dict[str, Any] | ParseIssue]:
        self._buffer.extend(chunk)
        out: list[dict[str, Any] | ParseIssue] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                if len(self._buffer) > MAX_LINE_BYTES:
                    out.append(
                        ParseIssue("line too long; dropped", bytes(self._buffer[:200]).decode("utf-8", "replace"))
                    )
                    self._buffer.clear()
                return out
            line = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            item = self._parse(line)
            if item is not None:
                out.append(item)

    def flush(self) -> list[dict[str, Any] | ParseIssue]:
        """Parse a final line that had no trailing newline."""
        line = bytes(self._buffer)
        self._buffer.clear()
        item = self._parse(line)
        return [item] if item is not None else []

    @staticmethod
    def _parse(line: bytes) -> dict[str, Any] | ParseIssue | None:
        text = line.decode("utf-8", "replace").strip()
        if not text:
            return None
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            return ParseIssue(f"invalid JSON: {exc.msg}", text[:200])
        if not isinstance(value, dict):
            return ParseIssue("JSON value is not an object", text[:200])
        return value
