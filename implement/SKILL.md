---
name: implement
description: "Implement exactly one settled ticket or spec only when the current task explicitly names the implement skill and identifies one concrete unit of work. Do not use for general coding requests, planning, or multiple tickets."
argument-hint: "<single ticket, issue URL, file path, or settled unit of work>"
---

# Implement

Implement exactly one settled unit of work.

The scope and decisions must already be settled upstream. Execute the agreed work without reopening planning or expanding its scope.

## Invocation gate

Proceed only when all of the following are true:

- The current task explicitly names the `implement` skill.
- Exactly one ticket, spec, or settled unit of work is identified.
- Its scope and acceptance criteria are clear.

If any condition is missing, do not edit code. Report the missing prerequisite and stop.

## Dependency

This skill depends on `codebase-design`. Every legal run must formally load the complete `codebase-design` skill before loading `tdd` or editing code. The dependency is mandatory and visible here; it must not be inferred only from a workflow step.

## Formal load

On every legal start, after reading the ticket／repo instructions／glossary／relevant ADRs／blockers and searching existing conventions, and before loading `tdd` or writing code, formally load the complete `codebase-design` skill via the current runtime's formal skill-loading mechanism (full skill body). Memory, description-only awareness, or skipping load are not substitutes. Writing the slash-token `/codebase-design` (or any single UI string) is not the cross-runtime load contract.

### Rituals by runtime

- **Claude Code:** invoke the Skill tool for `codebase-design` as the formal load. Only if that path fails／rejects／is unavailable may you fall back to reading the complete `codebase-design/SKILL.md`. Success evidence: Skill-tool result containing the skill body, or a full-file Read of `SKILL.md` after documented Skill-tool failure.
- **Cursor:** formal load is reading the complete `codebase-design/SKILL.md` at its resolvable full path (session skill list／installed skills path). Do not demand Claude Code's Skill tool. Success evidence: tool transcript shows a complete Read of that `SKILL.md`.
- **Codex:** formal load is reading the complete `codebase-design/SKILL.md` after authorized selection. Success evidence: tool transcript shows a complete Read of that `SKILL.md`.

**Load failure** means any of: skill not installed; not discoverable on the runtime's skill discovery surface; Skill tool／Read fails; or only a description／summary was obtained without the full body.

### Discoverability

Use the current runtime's skill discovery surface only (do not invent a second private search). If multiple installed copies exist, prefer the one the runtime's skill registry／session skill list resolves for the name `codebase-design`.

### Hard-fail on load failure

If `codebase-design` is not installed, not discoverable, or formal load fails, stop. Report the exact blocker naming the runtime, the discovery surface tried, and the path or registry key attempted. Do not silently continue without the load. Do not edit code after that failure.

On **Cursor**, the blocker must include every **attempted full path** to `codebase-design/SKILL.md` (from the session skill list／installed skills path). Naming only the skill／registry key `codebase-design` is not enough.

## Apply-on-demand

After formal load succeeds, default to **reference-only**: keep `codebase-design` vocabulary and principles available, but do not treat them as active implementation constraints until apply judgment says so.

Run the following checklist and answer in substance (not a bare yes／no). Set **apply = yes** only if at least one is true for this unit:

- **(a) Caller-visible contract change:** callers must learn a new or changed fact to use the module correctly — signature, invariant, ordering, error mode, required config, or performance characteristic that callers rely on.
- **(b) Replaceable seam:** a new or changed **replaceable** place exists where behavior can be swapped without editing call sites — a real seam with／toward a second adapter, not a hypothetical.

Set **apply = no** when the change stays behind an unchanged caller-visible contract and does not add／move a replaceable seam (including refactors that only touch a module-**internal** seam).

Do **not** encode file-type／class／DI blacklists. Judge by contract and seam substance.

### What apply means

When **apply = yes**, constrain implementation using `codebase-design`'s glossary, depth／seam／testability principles, and — only when seam placement or replaceable-adapter design is in scope for this unit — `DEEPENING.md` (see Reference deepening).

`implement` stays the session driver. Even when apply = yes, do not use `codebase-design` to explore alternative interfaces or redesign: that means no Read／open of `DESIGN-IT-TWICE.md`, no Design-it-twice／parallel alternative-interface workflow or sub-agents, and no treating `codebase-design` as the run's workflow driver.

### Reference deepening

Follow `codebase-design` links into reference files only when **apply = yes** and the unit's settled work involves seam placement or replaceable-adapter design — and then **only** load `DEEPENING.md` (complete Read at its resolvable path beside the loaded `codebase-design` skill). Never open `DESIGN-IT-TWICE.md` (same non-redesign rule as above).

If apply = yes requires `DEEPENING.md` and that file is unreadable／missing, treat it as **deepening-load failure**: hard-stop with the exact `DEEPENING.md` path attempted; do not edit code for this unit before or after that failure.

### No redesign license

Formal load does not authorize exploring alternative interfaces, expanding scope, or overturning ticket／spec-settled seams and caller-visible contracts. Reuse settled seams and contracts; do not invent new ones inside `implement`.

### Constraint locus (implement-path only)

These reference-only／apply-on-demand／non-driver rules live in `implement` only (no dual-role framing added to `codebase-design`). Other entry points may keep model-invoked discovery.

## Architecture blocker (unsettled／half-specified contract or seam)

If the unit cannot be completed without newly deciding what callers must know or where behavior can be replaced, and ticket／spec did not settle that contract／seam — including **half-specified** tickets where a seam is implied but not an executable caller-visible contract — stop **before** modifying code. Report an **architecture blocker** naming the missing decision. Do not invent or settle that decision inside `implement`.

## Late discovery

If apply judgment initially set apply = no (or assumed the contract／seam was settled) but later `tdd`／implementation proves the unit cannot finish without a new／changed **unsettled** caller-visible contract or replaceable seam:

1. Stop immediately — make no further code edits.
2. Do **not** revert, create／switch／delete branches or worktrees, or otherwise clean the tree.
3. Leave any speculative uncommitted edits dirty. Do **not** commit them. Do **not** present them as a settled successful completion.
4. Failure return must: (a) use the architecture-blocker path naming the missing decision; (b) list dirty paths touched in this run; (c) include attempted approaches／do-not-retry directions.
5. Tree cleanup, if any, is the orchestrator's job — out of scope for `implement`. Do not claim a clean revert.

## Workflow

1. Read the referenced ticket or spec in full, including relevant parent context and comments.
2. Read repository instructions, the domain glossary, and relevant ADRs.
3. Verify that all declared blockers exist in the current repository state.
4. Before writing any code, search the codebase for existing similar implementations and conventions; reuse existing work instead of rewriting it.
5. Formally load the complete `codebase-design` skill per Formal load. On failure, hard-stop per Hard-fail on load failure and do not continue.
6. Run Apply-on-demand judgment. If an Architecture blocker applies, hard-stop before any code edits and report it.
7. When apply = yes and seam placement or replaceable-adapter design is in scope, complete the required `DEEPENING.md` load per Reference deepening before loading `tdd` or editing code. Unreadable／missing `DEEPENING.md` = deepening-load-failure hard-stop with the exact path; no this-unit code edits may exist before or after.
8. Where possible, formally load the complete `tdd` skill (full skill body via the current runtime's load ritual). Step 8 is **load only** — do not start the TDD red／green loop or other code／test edits here. When not using `tdd`, skip this step.
9. Implement only the identified unit of work. When step 8 loaded `tdd`, follow that skill's loop here (including its test and implementation edits). When step 8 was skipped, implement without `tdd`, testing at the seam the ticket specifies or per the repository's existing testing conventions. Edit code／tests only after steps 5–7 gates that apply have succeeded (and step 8 has completed or been skipped).
10. Run focused tests and typechecking regularly.
11. Run the full relevant test suite when implementation is complete.
12. Use the `code-review` skill to review the result against repository standards and the originating ticket or spec.
13. Fix all review findings within this unit's scope.
14. Commit the completed work to the current branch.

No code edits before steps 5–6 succeed. When step 7 applies, no code edits before step 7 succeeds either. Step 8 must not perform TDD-loop edits; those belong in step 9 after `tdd` is loaded (or after step 8 is skipped).

## Self-explaining output

Let the code you write carry its own intent — names, types, and structure should make the design obvious, so a later reader understands it without chasing anything outside the code. This is the target for every text file change you make while implementing: source, comments, docstrings, docs shipped alongside the code, and — when the unit's work is designing a skill — that skill's prompt text. It governs the output side only: the spec, issue, ticket, ADR, CONTEXT.md you read to do the work are inputs, not outputs, and commit messages and other git metadata sit outside it too. It binds the output you newly produce from here on, not code that already shipped.

Reach for a **decision comment** on a single checkable question: does this implementation deliberately avoid a more obvious, more common approach? When it does, that choice is a fence — leave one line saying why the obvious approach was rejected, so the next reader does not tear the fence down and walk back into the problem you steered around. When the implementation is already the natural, obvious solution, the code speaks for itself — default to nothing, and earn the comment through the fence question. When you do write that line, it states the decision itself — the reason standing on its own — not a pointer back to whatever document prompted it.

## Boundaries

- Do not implement multiple tickets in one invocation.
- Do not start sibling or downstream tickets.
- Do not implement missing blockers.
- Do not reopen settled product or architecture decisions.
- Do not add speculative features or unrelated refactors.
- Do not cite the spec, issue, ticket, or ADR in the output you produce; let the code carry intent, and when a rationale is unavoidable state the decision itself, not the document (see Self-explaining output).
- Do not create, switch, merge, or delete branches or worktrees.
- Do not manage ticket scheduling, integration, or completion status; the calling orchestrator owns those responsibilities.
- Do not declare completion while tests fail or acceptance criteria remain unmet.
- Do not continue coding if formal load of `codebase-design` failed; report the exact blocker and stop.
- Do not violate the non-redesign rule under What apply means (including any Read of `DESIGN-IT-TWICE.md`).
- Do not invent unsettled caller-visible contracts or replaceable seams inside `implement`; report an architecture blocker instead.
- On late discovery of an unsettled contract／seam, stop immediately, leave dirty edits uncommitted, list dirty paths, do not present them as settled, and do not claim clean revert／tree cleanup.
- If missing information or repository state prevents implementation, report the exact blocker and stop.

## Completion

Return:

- Implementation summary
- Acceptance criteria status
- Tests, typechecks, and checks run
- Code-review findings and fixes
- Final commit SHA
- Any unresolved blocker or risk
- **Apply record** (required when apply = yes and implementation proceeded): why apply triggered; which constraints were used (glossary／principles／DEEPENING as applicable); explicit note that Design-it-twice／alternative-interface exploration was not run. When apply = no, omit the apply record or state apply = no.

On failure, additionally return: the approaches already attempted, why each failed, and the directions that must not be tried again. Architecture-blocker and late-discovery failures must name the missing contract／seam decision. Late-discovery failures must also list dirty paths touched in this run.
