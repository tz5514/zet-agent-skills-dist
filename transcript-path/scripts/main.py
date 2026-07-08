#!/usr/bin/env python3
"""transcript-path entry point: detect host runtime -> dispatch -> bare path.

Output contract: on success, stdout is exactly one line — the
absolute path of the current-session transcript — with no decoration. On
failure (no session resolved, including "no host runtime"), exit non-zero and
leave stdout empty.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from detect_runtime import detect

import locate_claude_code
import locate_codex
import locate_cursor


def resolve(env: dict, home: Path, cwd: str) -> str | None:
    """Detect the host runtime and dispatch to its locator.

    The dispatch table covers all three runtimes; each routes to its own
    locator script (US11). A "no host runtime" detection (None) resolves as
    'not resolved'.
    """
    runtime = detect(env)
    dispatch = {
        "claude_code": locate_claude_code.locate,
        "codex": locate_codex.locate,
        "cursor": locate_cursor.locate,
    }
    locator = dispatch.get(runtime)
    if locator is None:
        return None
    return locator(env, home, cwd)


def main() -> int:
    path = resolve(dict(os.environ), home=Path.home(), cwd=os.getcwd())
    if path is None:
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
