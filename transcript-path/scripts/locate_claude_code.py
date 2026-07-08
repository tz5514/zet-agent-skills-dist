#!/usr/bin/env python3
"""Locate the current claude_code session transcript.

Reads CLAUDE_CODE_SESSION_ID and finds ~/.claude/projects/*/<id>.jsonl by
globbing on the session id. The id is a UUID and so unique across all project
dirs (verified on disk: no basename collisions among the transcripts), so the
glob matches exactly one file. This needs no knowledge of the cwd->project-dir
naming rule and does not assume the skill runs from the same cwd the session
was created in. The match is by id, never by recency. Unset env
var, or anything other than exactly one match -> not resolved -> return None.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def locate(env: dict, home: Path, cwd: str) -> str | None:
    """Return the absolute transcript path, or None if not resolved.

    `cwd` is part of the shared locator signature but unused here: resolution
    is by session id alone, which is exactly what makes it independent of the
    current working directory.
    """
    session_id = env.get("CLAUDE_CODE_SESSION_ID")
    if not session_id:
        return None
    matches = sorted((home / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
    if len(matches) != 1:
        return None
    return str(matches[0])


if __name__ == "__main__":
    result = locate(dict(os.environ), home=Path.home(), cwd=os.getcwd())
    if result is None:
        sys.exit(1)
    print(result)
