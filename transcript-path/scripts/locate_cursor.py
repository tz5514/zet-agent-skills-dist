#!/usr/bin/env python3
"""Locate the current cursor-agent session transcript by self-marking.

Cursor exposes no session-id env var, so we enumerate candidates with a
FIXED-DEPTH glob (~/.cursor/projects/*/agent-transcripts/*/*.jsonl) — never a
recursive scan, which would reach one level deeper into sub-agent transcripts —
search each for this skill's own invocation trace, and return the
most-recently-modified hit. Targets only the cursor-agent JSONL
transcript, never the Cursor IDE composer's SQLite store.

Why newest-among-traced rather than newest overall: `transcript-path` is not a
unique marker (it also appears in sessions that merely discussed the skill);
what pins the result to the current session is that the calling session is live
and so has the newest mtime among string-matching files.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# LOAD-BEARING NAME (US21): this grep string IS the skill's name.
# Self-marking works because invoking the skill leaves this string in the
# transcript. If the skill is ever renamed, update this string in lockstep, or
# self-marking silently breaks.
_TRACE = "transcript-path"


def locate(env: dict, home: Path, cwd: str) -> str | None:
    """Return the absolute transcript path, or None if not resolved.

    `env` and `cwd` are part of the shared locator signature but unused here —
    cursor has no session-id env var, so resolution is purely by trace + mtime.
    """
    projects = home / ".cursor" / "projects"
    # Fixed-depth glob — do NOT recurse (no rglob / grep -r), which would reach
    # the deeper sub-agent transcript level.
    candidates = projects.glob("*/agent-transcripts/*/*.jsonl")

    best: Path | None = None
    best_mtime = -1.0
    for cand in candidates:
        try:
            content = cand.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _TRACE not in content:
            continue
        mtime = cand.stat().st_mtime
        if mtime > best_mtime:
            best_mtime = mtime
            best = cand

    if best is None:
        return None
    return str(best)


if __name__ == "__main__":
    result = locate(dict(os.environ), home=Path.home(), cwd=os.getcwd())
    if result is None:
        sys.exit(1)
    print(result)
