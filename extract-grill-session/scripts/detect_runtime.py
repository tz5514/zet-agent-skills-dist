#!/usr/bin/env python3
"""Detect which agent runtime produced a transcript JSONL file.

Usage: python3 detect_runtime.py <transcript.jsonl>
Prints the runtime identifier to stdout: claude_code | codex | unknown

Detection is structural — each runtime's envelope shape is matched on the
first rows — never based on the file's path or name.
"""
import json
import sys

# Claude Code rows carry a sessionId plus this type vocabulary.
_CLAUDE_CODE_TYPES = frozenset({
    "queue-operation", "attachment", "user", "assistant", "system",
    "last-prompt", "ai-title", "file-history-snapshot",
})

# Codex rows are a {type, timestamp, payload} envelope with this vocabulary.
_CODEX_TYPES = frozenset({
    "session_meta", "event_msg", "response_item", "turn_context", "compacted",
})


def detect(path):
    """Read the first ~30 lines and return a runtime identifier."""
    with open(path, encoding="utf-8") as f:
        sample = [f.readline() for _ in range(30)]

    for raw in sample:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if "sessionId" in obj and obj.get("type") in _CLAUDE_CODE_TYPES:
            return "claude_code"

        if ("payload" in obj and "timestamp" in obj
                and obj.get("type") in _CODEX_TYPES):
            return "codex"

    return "unknown"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <transcript.jsonl>", file=sys.stderr)
        raise SystemExit(1)
    print(detect(sys.argv[1]))
