#!/usr/bin/env python3
"""Detect the host runtime the skill is executing inside, from env vars.

Usage: python detect_runtime.py
Prints the host runtime identifier to stdout, or nothing if none is detected.

Unlike research-transcript's detect_runtime (which reads a *file's contents* to
judge which tool produced it), this detector reads *environment variables* to
judge the live host runtime — before any transcript file is in hand.
"""
from __future__ import annotations

import os
import sys


def detect(env: dict) -> str | None:
    """Return the host runtime, decided innermost-first."""
    if env.get("CURSOR_AGENT"):
        return "cursor"
    if env.get("CODEX_THREAD_ID"):
        return "codex"
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE_SESSION_ID"):
        return "claude_code"
    return None


if __name__ == "__main__":
    runtime = detect(dict(os.environ))
    if runtime is None:
        sys.exit(1)
    print(runtime)
