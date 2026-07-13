#!/usr/bin/env python3
"""extract-grill-session: an agent session transcript -> clean dialogue.

Keep only the human-typed prompts and the agent's text outputs, in
chronological order, never truncated. Supports claude code, cursor, and codex
transcripts: the runtime is detected from the file's content and mapped to a
per-runtime adapter; rendering is shared, so the output format is identical
for every runtime.

CLI:  extract_grill_session.py [transcript.jsonl] [output.md]
      no transcript -> resolve the current session's own transcript via the
      transcript-path skill; no output.md -> write to a temp file under the
      OS temp dir and print its path.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import detect_runtime
import extract_claude_code
import extract_codex
import extract_cursor

# runtime identifier (as detected from content) -> adapter module. Every
# adapter satisfies the same contract: extract_events(messages) yields
# ("user" | "assistant", text) in order, session_meta(messages) yields
# (session_id, first_ts, last_ts).
_ADAPTERS = {
    "claude_code": extract_claude_code,
    "codex": extract_codex,
    "cursor": extract_cursor,
}


def render_conversation(events, *, session_id=None,
                        first_ts=None, last_ts=None):
    """Render (role, text) events as id-tagged dialogue blocks. Never truncates.

    `USER_PROMPT id="{turn}"` and `AGENT_OUTPUT id="{turn}-{segment}"`. Multiple
    agent outputs in one turn stay as separate, individually-addressable blocks —
    that boundary is the natural gap the removed thinking/tool left, and keeping
    it spares the reader a "why did this jump?" seam. Tags occupy their own lines
    so a consumer locates blocks by line-anchored tags, not a strict XML parser
    (content is verbatim and may itself contain such tags).
    """
    user_turns = sum(1 for r, _ in events if r == "user")
    out_blocks = sum(1 for r, _ in events if r == "assistant")

    lines = ["---"]
    if session_id:
        lines.append(f"session_id: {session_id}")
    if first_ts or last_ts:
        lines.append(f"period: {first_ts} → {last_ts}")
    lines.append(
        f"content: {user_turns} human-typed prompts, {out_blocks} agent output "
        f"blocks — thinking, tool calls, and system/skill-injected user messages "
        f"excluded; verbatim, never truncated; chronological"
    )
    lines.append('legend: USER_PROMPT id="{turn}", AGENT_OUTPUT id="{turn}-{segment}"; '
                 "tags occupy their own lines; locate blocks by line-anchored tags, "
                 "not a strict XML parser")
    lines.append("---")

    turn = 0
    seg = 0
    for role, text in events:
        if role == "user":
            turn += 1
            seg = 0
            lines.append(f'\n<USER_PROMPT id="{turn}">')
            lines.append(text)
            lines.append("</USER_PROMPT>")
        else:
            seg += 1
            lines.append(f'\n<AGENT_OUTPUT id="{turn}-{seg}">')
            lines.append(text)
            lines.append("</AGENT_OUTPUT>")
    return "\n".join(lines)


def load_messages(path):
    """Read a JSONL transcript into a list of dicts, skipping blank/invalid lines."""
    messages = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return messages


_TRANSCRIPT_PATH_ENTRY = (Path(__file__).resolve().parent.parent.parent
                          / "transcript-path" / "scripts" / "main.py")


def _locate_current_transcript():
    """The current session's transcript path, asked of the transcript-path skill.

    Zero-arg runs mean "extract this very session": locating is delegated to
    the sibling transcript-path skill (its contract: stdout is exactly one
    path, or exit non-zero with empty stdout). Returns the path, or None.
    """
    result = subprocess.run(
        [sys.executable, str(_TRANSCRIPT_PATH_ENTRY)],
        capture_output=True, text=True)
    path = result.stdout.strip()
    if result.returncode != 0 or not path:
        return None
    return path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        src = argv[0]
        out_path = argv[1] if len(argv) > 1 else None
    else:
        src = _locate_current_transcript()
        if src is None:
            print("error: no transcript given and the current session's "
                  "transcript could not be resolved via the transcript-path "
                  "skill", file=sys.stderr)
            return 2
        out_path = None

    runtime = detect_runtime.detect(src)
    adapter = _ADAPTERS.get(runtime)
    if adapter is None:
        print(f"error: unrecognized transcript format in {src} "
              f"(supported: {', '.join(sorted(_ADAPTERS))})", file=sys.stderr)
        return 2

    messages = load_messages(src)
    events = adapter.extract_events(messages)
    session_id, first_ts, last_ts = adapter.session_meta(messages)
    md = render_conversation(events, session_id=session_id,
                             first_ts=first_ts, last_ts=last_ts)

    if out_path:
        out_file = open(out_path, "w", encoding="utf-8")
    else:
        out_file = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", prefix="grill-session-", suffix=".md",
            delete=False)
        out_path = out_file.name
    with out_file:
        out_file.write(md)
    prompts = sum(1 for r, _ in events if r == "user")
    outputs = sum(1 for r, _ in events if r == "assistant")
    print(f"wrote {out_path} — {prompts} prompts, {outputs} outputs, "
          f"{len(md)} chars", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
