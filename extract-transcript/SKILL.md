---
name: extract-transcript
description: Extract a runtime-neutral, category-selective JSONL artifact from a Claude Code, Cursor, or Codex session transcript for review or analysis.
---

# Extract Transcript

Extract one agent session into compact normalized JSONL while preserving the
selected semantic content and its source-relative order.

## Invocation

```bash
python3 {skill_dir}/scripts/extract_transcript.py [transcript.jsonl] \
  [--content-category CATEGORY]... \
  [--include-launched-agents]
```

The transcript path is optional. When omitted, the current session path is
resolved through the sibling `transcript-path` skill. Current-session
self-exclusion fixes the extraction boundary before this invocation; if that
boundary cannot be proven, extraction fails without delivering an artifact.

Repeat `--content-category` to select more than one of these runtime-neutral
categories:

- `user_prompt`
- `user_visible_agent_output`
- `reasoning`
- `tool_activity`
- `agent_instructions`
- `turn_lifecycle`

With no category arguments, the default selection contains:

- `user_prompt`
- `user_visible_agent_output`
- the call of the runtime's known interactive question tool — the
  per-runtime tool identities are defined once in the "interactive question
  tool" entry of this skill's `CONTEXT.md`
- that call's paired result, whenever the source stored one

A question whose result the source never stored, or whose result cannot be
paired with the call, contributes only the call. No other tool activity enters
this default. Passing any `--content-category` selects exactly the categories
listed instead, so explicit `tool_activity` still yields every tool activity.

Session basic data is always the first record and is not a selectable
category. Images follow the prompt, visible output, or tool activity that owns
them. If a tool result splits one raw user message into multiple prompt
records, those records share a runtime-neutral `prompt_id` and carry
zero-based `segment_index` values; unsegmented prompts omit both fields. Any
prompt images remain attached to that shared logical prompt identity.

Codex `agent_message` records can directly prove visible output images and are
packaged with their output record. The observed Claude Code and Cursor sources
only prove assistant text as visible output; their prompt and tool-result images
remain in those owning categories and are never guessed to be visible output.

Launched-agent export is disabled unless `--include-launched-agents` is given.
When enabled, only relationships directly proven by the source runtime are
followed, recursively. The primary agent and every successfully exported child
receive separate JSONL artifacts with navigable parent and child paths.

## Delivery and errors

On success, stdout reports exactly these two absolute paths:

```text
Session artifact directory: /absolute/path/to/extraction
Primary artifact: /absolute/path/to/extraction/transcript.jsonl
```

The artifact directory also contains `extraction-manifest.json`, which binds
the primary artifact's SHA-256 digest and every materialized image asset's
canonical `assets/image-NNNN.<gif|jpg|png|webp>` path and SHA-256 digest to this
producer, manifest version, selected categories, and launched-agent option.
Image numbers use at least four digits and continue growing when an extraction
contains more than 9,999 images. Consumers that require the fixed default
extraction use this manifest to reject an unaccompanied, shortened,
selection-changed, path-aliased, or content-modified JSONL file or image. An
intact artifact, its sibling assets, and their matching manifest may move
together without changing that contract.

When source evidence limits completeness or readability of retained content,
stderr emits one centralized `Extraction conditions:` report. It identifies
omitted categories, exceptional conditions, and unknown judgments without
adding report records or sidecars to the artifact. A routine successful
extraction emits no condition report. Every condition names
`transcript.jsonl` or the relevant `agent-NNNN.jsonl`, so identical local record
identifiers remain distinguishable.

An explicitly named transcript is reported as a fixed active snapshot only
when runtime lifecycle records directly prove an in-progress state at the
snapshot boundary. Matching the current-session path or observing later file
growth is not active-state evidence. The content records and fixed header are
both derived from the same byte boundary.

Invalid input, an unsupported runtime, an unreliable current-session boundary,
or a primary-source decoding failure exits non-zero and does not claim a
delivered artifact. A failed launched agent is isolated: successful artifacts
remain valid, the failed child receives no navigation path, and stderr names
the failure.
