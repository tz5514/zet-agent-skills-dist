"""Detect the supported runtime from transcript record structure."""

import json


_CLAUDE_CODE_TYPES = frozenset({
    "queue-operation",
    "attachment",
    "user",
    "assistant",
    "system",
    "last-prompt",
    "ai-title",
    "file-history-snapshot",
})
_CODEX_TYPES = frozenset({
    "session_meta",
    "event_msg",
    "response_item",
    "turn_context",
    "compacted",
})


def detect_runtime(path):
    """Return a runtime identifier, or ``unknown`` when no format matches."""
    with open(path, "rb") as transcript:
        sample = [transcript.readline() for _ in range(30)]

    for raw_line in sample:
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        if (
            "sessionId" in record
            and record.get("type") in _CLAUDE_CODE_TYPES
        ):
            return "claude_code"
        if (
            record.get("role") in ("user", "assistant")
            and "message" in record
            and "sessionId" not in record
            and "type" not in record
        ):
            return "cursor"
        if (
            "payload" in record
            and "timestamp" in record
            and record.get("type") in _CODEX_TYPES
        ):
            return "codex"
    return "unknown"
