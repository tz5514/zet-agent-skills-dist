#!/usr/bin/env python3
"""Locate the current codex session transcript.

Reads CODEX_THREAD_ID and resolves the matching rollout file. The sessions dir
is nested three levels by date (YYYY/MM/DD) and the filename carries a timestamp
prefix, so we glob on the id rather than assembling the dated path:
~/.codex/sessions/*/*/*/rollout-*-<id>.jsonl. The glob must match
exactly one file; 0 or >1 matches -> not resolved -> return None. If
CODEX_THREAD_ID is unset -> not resolved -> return None.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def locate(env: dict, home: Path, cwd: str) -> str | None:
    """Return the absolute transcript path, or None if not resolved.

    `cwd` is part of the shared locator signature but unused here — codex
    resolves purely by id-glob under the home directory.
    """
    thread_id = env.get("CODEX_THREAD_ID")
    if not thread_id:
        return None
    sessions = home / ".codex" / "sessions"
    matches = sorted(sessions.glob(f"*/*/*/rollout-*-{thread_id}.jsonl"))
    if len(matches) != 1:
        return None
    return str(matches[0])


if __name__ == "__main__":
    result = locate(dict(os.environ), home=Path.home(), cwd=os.getcwd())
    if result is None:
        sys.exit(1)
    print(result)
