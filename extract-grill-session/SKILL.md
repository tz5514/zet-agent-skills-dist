---
name: extract-grill-session
description: Extract a clean dialogue from an agent session transcript — only the human-typed prompts and the agent's text outputs, in chronological order, never truncated. Thinking blocks, tool calls/results, and system/skill-injected user messages are stripped. Use when the user points at a session transcript .jsonl and wants just the conversation (prompts + replies) to re-read or archive, or asks to extract a grill/design session's pure dialogue. Supports Claude Code and Codex transcripts (auto-detected).
---

# extract-grill-session

Turn an agent session transcript (jsonl) into a clean conversation: only
what the human actually typed and what the agent replied — chronological, full
text, never truncated. Claude Code and Codex transcripts are both supported;
the runtime is detected from the file's content, and both render into the
exact same output format.

## Quick start

```bash
python3 scripts/extract_grill_session.py [transcript.jsonl] [output.md]
```

- With `transcript.jsonl`: extracts that transcript (runtime auto-detected).
- Without any arguments: extracts **the current session itself** — the running
  session's transcript path is resolved by calling the sibling
  `transcript-path` skill; if it cannot be resolved, exits non-zero with an
  error on stderr.
- With `output.md`: writes that file.
- Without it: writes to a temp file under the OS temp dir and prints
  `wrote <path> — …` on stderr.

The input is a session jsonl from either runtime, e.g.
`~/.claude/projects/<project>/<session-id>.jsonl` (Claude Code) or
`~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-….jsonl` (Codex). An unrecognized
format exits non-zero with an error on stderr.

## Output format

Identical for every runtime (the renderer is shared; only parsing is
per-runtime). Line-anchored, id-tagged blocks — **not strict XML**: content is
verbatim and may itself contain tags, so consumers should locate blocks by
their own-line open/close tags, not an XML parser.

```
<USER_PROMPT id="1">
…what you typed…
</USER_PROMPT>

<AGENT_OUTPUT id="1-1">
…the agent's reply…
</AGENT_OUTPUT>
```

- `USER_PROMPT id="{turn}"` — each human prompt (queued interjections included,
  shown as ordinary prompts).
- `AGENT_OUTPUT id="{turn}-{segment}"` — the agent's text outputs within that turn,
  kept as separate, individually-addressable segments (the boundary is the gap the
  removed thinking/tool left; merging them would read as a non-sequitur jump).
- A leading YAML frontmatter (`---` … `---`) carries session_id / period /
  counts / legend. (Deliberately **not** the source transcript path — so a
  consuming LLM can't go read the raw jsonl instead of this filtered extract.)

## What it keeps vs strips

**Keeps** (the human↔agent dialogue):
- Human-typed prompts — plain messages, and (Claude Code) slash commands
  restored to the form you typed them (`/grill-with-docs <args>`).
- Prompts you typed while the agent was working (queued-command attachments).
- The agent's text outputs (what it showed you).

**Strips** (not dialogue):
- Thinking/reasoning blocks, tool calls, and tool results.
- System/skill-injected user messages — Claude Code: `isMeta` rows (a slash
  command's loaded body / `what-to-do` / `Base directory for this skill:`) and
  system event markers (`[Request interrupted…]`, `<local-command-stdout>`,
  `<ide_opened_file>`); Codex: AGENTS.md instruction rows, `<skill>` loads,
  `<goal_context>` / `<hook_prompt>` / `<turn_aborted>` rows, compaction
  history, developer messages.
- tool_result rows masquerading as user messages, and sub-agent
  `<task-notification>` / `<subagent_notification>` notices.

Whether a message is human-typed is decided by structure, **never by length** —
a one-word prompt like `停` is kept. Per runtime the structural test is:

- **Claude Code** (`scripts/extract_claude_code.py`): a `user` row is
  human-typed unless it is `isMeta` or a system event/output wrapper.
- **Codex** (`scripts/extract_codex.py`): the dialogue source is the event
  stream — `event_msg`/`user_message` is recorded exactly when the human
  submitted a message, and `event_msg`/`agent_message` carries the text the
  agent actually showed. Injections reach the model only as `response_item`
  rows and never get an event, and the assistant `response_item` copy can
  trail non-displayed attachments (e.g. `<oai-mem-citation>`) — so
  `response_item` rows are ignored entirely, which is a structural judgment,
  not a marker blacklist.

## Architecture

- `scripts/extract_grill_session.py` — shared core: content-based runtime
  dispatch, `load_messages`, `render_conversation`, CLI. One renderer ⇒ one
  output format.
- `scripts/detect_runtime.py` — structural detection (`claude_code` / `codex`
  / `unknown`) from the first rows' envelope shape, never from the path.
- `scripts/extract_claude_code.py`, `scripts/extract_codex.py` — runtime
  adapters. Shared contract: `extract_events(messages)` → ordered
  `("user" | "assistant", text)`; `session_meta(messages)` →
  `(session_id, first_ts, last_ts)`. Adding a runtime = one adapter module +
  a detection clause; the renderer and CLI stay untouched.

## Scope

Claude Code and Codex transcripts. Its only cross-skill dependency is the
zero-argument mode, which runs the sibling `transcript-path` skill's entry
script to resolve the current session; nothing else is imported or shared.
