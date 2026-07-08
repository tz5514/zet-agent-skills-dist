---
name: transcript-path
description: Resolve and print the absolute path of the current agent session's transcript file, for whichever runtime the skill is running in (claude_code / codex / cursor-agent). Use when the user wants their current session's transcript path — e.g. to back it up, hand it off, or feed it to another tool.
---

# Transcript Path

Resolve the absolute path of the transcript file for the **current** agent
session — the session running right now, in the runtime executing this skill —
and print it. It locates only: it never opens, parses, converts, or analyses the
resolved transcript — what the path is used for is the caller's business, not
this skill's.

## Usage

One entry point detects the host runtime from the environment, dispatches to
that runtime's locator, and prints the path:

```bash
python3 {skill_dir}/scripts/main.py
```

It takes no arguments — the current session is read from the environment.

## Output contract

- **Success:** stdout is exactly one line — the absolute path — with no
  decoration (no runtime label, no JSON, no diagnostic line), so it drops
  straight into `$(...)`, a pipe, or the clipboard.
- **Failure (session not resolved):** exit non-zero and leave stdout empty. So
  stdout is always either one valid path or nothing — never a guess.

**If you are the agent running this skill, the path line IS your answer.** Relay
the script's stdout verbatim and stop. Do not wrap it in a sentence, prepend a
`host runtime:` label or a "here is your transcript" preamble, or append a
suggested next step or recommended use for the path — the skill resolves the
path and nothing more; what it is used for is the caller's to decide. On
failure, say only that the current session's transcript could not be resolved —
never invent a path.

## How it resolves

The host runtime is detected innermost-first, because an outer runtime's env
vars are inherited by an inner one it spawns: `CURSOR_AGENT` → cursor; else
`CODEX_THREAD_ID` → codex; else `CLAUDECODE` / `CLAUDE_CODE_SESSION_ID` →
claude_code; else no host runtime (not resolved). Each runtime has its own
locator script:

| Runtime | Locator | Method |
|---|---|---|
| claude_code | `scripts/locate_claude_code.py` | `CLAUDE_CODE_SESSION_ID` + cwd-slug → `~/.claude/projects/<cwd-slug>/<id>.jsonl` |
| codex | `scripts/locate_codex.py` | glob `~/.codex/sessions/*/*/*/rollout-*-<CODEX_THREAD_ID>.jsonl` (exactly one match) |
| cursor | `scripts/locate_cursor.py` | self-marking: among `agent-transcripts/*/*.jsonl` files containing the `transcript-path` trace, the newest by mtime (trace-filtered, not raw recency) |
