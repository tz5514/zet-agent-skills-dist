---
name: to-prd
description: Turn the current conversation context into a PRD and publish it to the project issue tracker. Use when user wants to create a PRD from the current context.
---

This skill takes the current conversation context and codebase understanding and produces a PRD. Do NOT interview the user — just synthesize what you already know.

The issue tracker and triage label vocabulary should have been provided to you — run `/setup-matt-pocock-skills` if not.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the PRD, and respect any ADRs in the area you're touching.

2. Sketch out the major modules you will need to build or modify to complete the implementation. Actively look for opportunities to extract deep modules that can be tested in isolation.

A deep module (as opposed to a shallow module) is one which encapsulates a lot of functionality in a simple, testable interface which rarely changes.

Check with the user that these modules match their expectations. Check with the user which modules they want tests written for.

3. Write the PRD using the template below, then publish it to the project issue tracker. Apply the `ready-for-agent` triage label - no need for additional triage.

<prd-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts — not a working demo, just the important bits.

Named exception — `## Related Draft ADRs` entry paths: each entry in the `## Related Draft ADRs` section below deliberately pairs the ADR number with its current draft path. **This is a deliberate exception to the "do NOT include specific file paths" rule above, not an oversight.** Rationale: a PRD is transient — it is obsolete once implementation finishes (including moving the listed drafts into active), so the path stays valid for the PRD's whole lifetime, while the paired stable number keeps "which ADR is this" unambiguous even if the file later moves. When processing this template downstream, do not delete or refuse to add these paths on account of the general rule.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this PRD.

## Further Notes

Any further notes about the feature.

## Related Draft ADRs

(Optional; appears only when the related draft ADR list is non-empty, placed at the end of the PRD.) Opens with a directive telling the downstream implementing agent to read each listed draft ADR's full body; then lists each entry as `- **ADR {number}** (`{current draft path}`)` (number = stable identity, path = current source location; writing the draft path here is the named exception noted above). The migration last task follows directly after the list (list first, migration after — one self-contained block). **This whole block is produced by the ADR reference-block generator, not hand-written in this template**; the migration last task's fixed text has its single source in the generator's template file (`templates/related-adrs-blocks.md`), and this template does not duplicate it.

## Related Active ADRs

(Optional; appears only when the related active ADR list is non-empty, placed at the end of the PRD.) Reference navigation only: lists each entry as `- **ADR {number}** (`{current path}`) — {relevance note}` (relevance note optional). **Zero-write**: this block never drives any migration or supersession marking. Also produced by the ADR reference-block generator.

</prd-template>

## ADR lifecycle reference handling

On every PRD, produce the two sections above according to the project's three-state ADR lifecycle (draft = not yet implemented, active = landed ground truth, archived = fully superseded). Steps:

1. **Relevance judgement (stays here as the caller; you judge it from the conversation):** From the **current conversation context**, judge (a) the draft ADRs this PRD's work will implement — these form the related draft ADR list; and (b) the optional related active ADRs that are not obvious to the implementer and worth pointing out, attaching a one-line relevance note to each. The source is the conversation itself — **do not enumerate by scanning the filesystem, and do not interview the user**. This judgement needs the conversation, is inherently non-extractable, and so stays in this skill.

2. **Criteria:**
   - The **related draft ADR list** takes drafts relevant to this PRD's spec **and that this PRD will implement**; this is independent of which session/grill round produced the draft — a draft that existed before this session, produced by another round but never carried through, is included as long as it is relevant and will be implemented. **A draft this PRD does not implement is not referenced in any form.**
   - The **related active ADR list** takes relevant actives that are "not obvious to the implementer, worth pointing out" (an active superseded by one of this PRD's drafts is a strong candidate).
   - **archived ADRs are never referenced.**

3. **Zero-write single-driver line:** `## Related Active ADRs` is **reference-only, zero-write** — it never drives any migration or supersession marking. The only write driver is `## Related Draft ADRs`: a superseded active is marked only via the superseding draft's `supersedes`, applied by supersession-mark back-derivation at move time. **Even if one of this PRD's drafts supersedes an active that appears in the reference list, that active is still marked only via the draft's `supersedes`, regardless of whether it appears in the reference list.** Never trigger any migration or marking because an active appears in the reference list.

4. **Call the ADR reference-block generator:** Feed it the judged lists (the related draft ADR list + optional related active ADR list — each entry carrying its `number`, `path`, and caller-supplied `bounded_context`; active entries also a `relevance_note`) plus this PRD's own bounded context, and it returns the `## Related Draft ADRs` and optional `## Related Active ADRs` block text. The generator does mechanical assembly only (fills rows and the same/cross bounded-context citation qualifier, drops an empty section); all semantic content is supplied by your relevance judgement above. **Each entry's `bounded_context` is judged and supplied by you, never inferred from the path** — so the handling is independent of repo layout.

5. **Call the path-existence check:** For each entry, mechanically check that its current path exists (resolved against an explicit repo root). **When the check reports a miss, investigate the cause from your own conversation context and fix the reference yourself** — a missing path is almost certainly a number or path you mis-recorded, and you hold the same context that produced the list, so you can fix it. **Do not interrupt PRD production, do not silently drop the entry, and do not hand off to a human.**

6. **Placement and omission:** Both sections go at the **end** of the PRD (after the standard template sections); both are optional and the whole section is omitted when its list is empty. When the related draft ADR list is empty there is no `## Related Draft ADRs` section **and no migration task** — the empty set is naturally a no-op, needing no "should I add the migration task" conditional branch.

**How the migration mechanism is referenced (skeleton stable / instance replaceable):** the migration last task points at the mechanism "for each draft in the list, call `/adr revise-and-promote-draft-to-active` with that draft's `draft_adr_path`." It is written in two layers: the **skeleton** "reference this project's ADR-lifecycle migration procedure" is fixed; the **current instance** names the command and its authoritative spec — `revise-and-promote-draft-to-active`. The instance names that command because `/adr` is the project's ADR-mechanism home and owns the supersession lifecycle, and this command completes each draft's delivery quality review before promoting it; should it ever move, only the instance half-sentence is swapped — the skeleton and the injection structure do not change. The migration last task's fixed text is NOT written in this SKILL.md: its **single source is the generator's template file `templates/related-adrs-blocks.md`**, and this section carries only the skeleton/instance reference and points at that template as the instance-swap site. The generator emits the same text on every PRD; this skill does not duplicate it or rewrite it per run, so the text cannot drift.

**Forward compatibility:** `/adr` already exists as the project's unified ADR-operations entry point. The ADR reference-block generator, its template, and the path-existence check **stay in to-prd** — they produce PRD content (how the PRD's related-ADR sections look), not ADR-mechanism governance, so they are not moved into `/adr`. This skill is the "judge the lists → call the generator" caller; the migration last task it emits references the ADR-lifecycle migration procedure by its current instance — the `/adr revise-and-promote-draft-to-active` command.

**Test scope is already decided (this feature skips the two existing steps):** this feature's module split (relevance judgement, ADR reference-block generator, path-existence check) and test scope (unit-test the two mechanical modules; do not unit-test the relevance-judgement module — it is LLM judgement, not mechanically verifiable) are already decided. When implementing this feature, **skip** the "Check with the user that these modules match their expectations" and "Check with the user which modules they want tests written for" steps in Process step 2 above; do not ask the user again.
