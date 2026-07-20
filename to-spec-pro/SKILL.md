---
name: to-spec-pro
description: Turn the current conversation into a spec published to the project issue tracker, by loading the installed official to-spec skill as the runtime baseline and layering this project's overlay rules on top — no interview, just synthesis of what you've already discussed.
disable-model-invocation: true
---

This skill wraps the official `to-spec` skill: at runtime it loads the official prompt as the baseline process, then layers this project's overlay rules on top. It carries no copy of the official prompt.

## Baseline loading

1. Locate the installed official skill named `to-spec` at runtime: resolve it by skill name within the installed-skills directories of the current environment (for example, a directory named `to-spec` alongside this skill). Never use a hard-coded absolute path.
2. If no installed official `to-spec` skill can be found, stop here. Report that the official `to-spec` skill is not installed, include the install command `npx skills@latest add mattpocock/skills`, and end the run without producing a spec. Never execute the overlay rules below on their own.
3. Read the resolved `to-spec` skill's `SKILL.md` in full. That document is the baseline process: execute it as written.

## Overlay

If the current conversation has used the adr skill to create or modify an ADR, or has identified an existing ADR that this spec will implement or must follow, read [ADR-REFERENCE-HANDLING.md](ADR-REFERENCE-HANDLING.md) in full before beginning the baseline process, complete its normalization and path-validation steps before the general repository exploration at the start of the baseline process, and complete every remaining step before publishing.

## Post-publication review

The baseline process is executed exactly as written: seam confirmation, publication, and the ready-for-agent marking all happen at the baseline's own points, and nothing in this section reschedules, replaces, or rewrites any baseline step. After the baseline process has published the spec, run the three stages below in order.

### Stage 1 — Settled-decision checklist reconciliation

Run this in the main session; it requires the conversation and is never delegated to a context-free sub-agent.

1. **Extract.** Go through the conversation and extract every decision the user explicitly settled, one sentence per item, into a checklist. Write the checklist to a file in a run directory under the OS tmp area (or the session scratchpad); it is run evidence — never write it into bounded-context folders or the spec.
2. **Locate.** For each item, identify its landing point in the published spec or in a related ADR the spec lists, and record that landing point on the checklist.
3. **Close every item.** Every item must end in exactly one of two states: **landed** — a located landing point is recorded — or **explicitly excluded** — the checklist states the item is not included and why. There is no third state: no settled decision may silently disappear.

Any item with neither a landing point nor an explicit exclusion is a blocker: write the missing content in, then redo the reconciliation until every item closes in one of the two states.

### Stage 2 — Blind review

Invoke the `review-spec` skill on the published spec in `initial` mode, supplying the inputs its interface requires: the spec path, and — as the allowed document set — the related ADR files the spec lists, the `CONTEXT.md` of each bounded context the spec touches, and any external design reference the spec identifies. review-spec dispatches a blind reviewer holding no conversation context and returns a mechanically validated, structured findings report; its blockers drive Stage 3.

### Stage 3 — Blocker repair loop

The loop is driven by blockers only. A non-blocker never triggers a modification on its own; it may only ride along with the same round's blocker repairs.

- **Minimal repair.** Each round, apply the smallest edits that fix that round's reported blockers, plus any ride-along non-blocker fixes, and nothing else.
- **Coupling check.** Whenever a repair changes a scope of coverage, a count, or an obligation, sweep every reference pointing at the changed content in the same round and align them all in the same direction.
- **Re-review.** After each repair round, invoke `review-spec` in `post-fix` mode. Pass the prior-round disposition its interface requires: a JSON file recording, for every finding of the prior round's report, the repair's claimed disposition.
- **Done.** The loop reaches its done state when a review round — initial or post-fix — reports zero blockers and the spec receives zero modifications after that round. Any modification after a round, including a non-blocker touch-up, invalidates that round's result and requires a re-review.
- **Pens down.** On reaching the done state, the spec is closed to writing. Remaining non-blockers are listed as-is in the final report; any later modification belongs to a new review cycle, not this loop.
- **Circuit breaker.** At most seven valid review rounds in total, the initial round included. Hitting the cap is an explicit failure terminal state: report the remaining blocker list to the user for adjudication, and never present it as a pass.
- **Invalid rounds.** A round whose report fails review-spec's mechanical validation does not count toward the seven-round cap; re-dispatch that round once. If the re-dispatch is invalid again, that is a failure terminal state: stop and report it to the user.
