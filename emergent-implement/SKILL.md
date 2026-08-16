---
name: emergent-implement
description: "Implement exactly one settled ticket or spec only when the current task explicitly names the emergent-implement skill and identifies one concrete unit of work. Do not use for general coding requests, planning, or multiple tickets."
argument-hint: "<single ticket, issue URL, file path, or settled unit of work>"
---

# Emergent Implement

Implement exactly one settled unit of work.

The scope and decisions are settled upstream. Execute the agreed work without reopening planning or expanding its scope, and let everything the settled input leaves unspecified emerge through code, tests, and integration feedback.

## Invocation gate

Proceed only when all of the following are true:

- The current task explicitly names the `emergent-implement` skill.
- Exactly one ticket, spec, or settled unit of work is identified.
- Its scope and acceptance criteria are clear.

If any condition is missing, do not edit code. Report the missing prerequisite and stop.

## Authorities and methods

Every legal run formally loads three skills, each in a fixed role:

- **`emergent-design`** — the sole engineering-philosophy authority for the entire invocation: it draws the human-decision boundary, says what may emerge during implementation, and assigns each piece of information to the carrier that owns it. Load failure is a hard stop.
- **`codebase-design`** — a subordinate implementation method: the module／interface／seam vocabulary and design principles. Load failure is a hard stop.
- **`tdd`** — a subordinate implementation method: the red→green loop. Load it where possible; skip it only when the run will not use it.

The methods stay subordinate: they shape how the free space gets built, and neither method overrides the loaded `emergent-design` on what is reserved for humans.

### Formal load

A formal load means the current runtime's formal skill-loading mechanism returns the complete skill body into context. Memory, a description, a summary, or a paraphrase never stands in for a loaded skill, and writing a slash-token (or any single UI string) is not the cross-runtime load contract.

- **Claude Code:** invoke the Skill tool for the named skill. Only if that path fails／rejects／is unavailable may you fall back to reading the complete `SKILL.md`. Success evidence: Skill-tool result containing the skill body, or a full-file Read of `SKILL.md` after documented Skill-tool failure.
- **Cursor:** formal load is reading the complete `SKILL.md` at its resolvable full path (session skill list／installed skills path). Do not demand Claude Code's Skill tool. Success evidence: tool transcript shows a complete Read of that `SKILL.md`.
- **Codex:** formal load is reading the complete `SKILL.md` after authorized selection. Success evidence: tool transcript shows a complete Read of that `SKILL.md`.

Use the current runtime's skill discovery surface only (do not invent a second private search). If multiple installed copies exist, prefer the one the runtime's skill registry／session skill list resolves for that name.

**Load failure** means any of: skill not installed; not discoverable on the runtime's skill discovery surface; Skill tool／Read fails; or only a description／summary was obtained without the full body.

### Fail closed on load failure

If the formal load of `emergent-design` or `codebase-design` fails, stop before any code edit: report the exact blocker naming the runtime, the discovery surface tried, and the path or registry key attempted. Fail closed — a copied restatement of either skill never replaces the loaded body, and no code edits may follow the failure.

On **Cursor**, the blocker must include every **attempted full path** to that skill's `SKILL.md` (from the session skill list／installed skills path). Naming only the skill／registry key is not enough.

## Binding and free

The loaded `emergent-design` splits the unit into what the run must preserve and what it may shape:

- **Binding** — every ratified commitment in the settled Spec／ticket, internal implementation requirements included: implement them as written, and do not re-review, weaken, or reopen them.
- **Free to emerge** — explicitly non-binding suggestions and every internal design choice the settled input leaves unspecified: real code, tests, and integration feedback own these, so improve them whenever implementation evidence exposes a better answer.

Vertical slices and short feedback loops keep the free space on course: build in thin end-to-end slices, let each slice's evidence steer the next, and keep observable behavior executable while internal structure keeps emerging. They are working guidance, never approval checks — no slice waits for sign-off.

## codebase-design: active or reference-only

After its formal load, decide how the method applies to this unit — judge by what the unit actually does to structure, never by file type, class, or dependency-injection blacklists:

- **Active** — the unit creates or reshapes a module, interface, responsibility boundary, or seam, including an internal one: give depth, seam placement, and testability deliberate attention with the loaded design guidance while you shape it.
- **Reference-only** — the unit's behavior change stays inside existing responsibilities: keep the vocabulary and principles available without turning the unit into a design exercise.

Neither mode authorizes redesign of settled commitments or scope expansion: reuse settled seams and contracts, and keep `emergent-implement` as the session driver in both modes. Never open `DESIGN-IT-TWICE.md` or run the Design-it-twice／parallel alternative-interface workflow or sub-agents.

### Reference deepening

Follow `codebase-design` links into reference files only when the unit's settled work involves seam placement or replaceable-adapter design — and then **only** load `DEEPENING.md` (complete Read at its resolvable path beside the loaded `codebase-design` skill). If that load is required and `DEEPENING.md` is unreadable／missing, hard-stop with the exact path attempted; no this-unit code edits may exist before or after that failure.

### Constraint locus (emergent-implement-path only)

These active／reference-only／non-driver rules live in `emergent-implement` only (no dual-role framing added to `codebase-design`). Other entry points may keep model-invoked discovery.

## user-decision blocker

A missing decision is a **user-decision blocker** only when all four conditions hold:

1. A concrete obligation from the settled ticket or Spec cannot be fulfilled without the answer.
2. The question is specific and unavoidable — no implementation route inside the settled scope sidesteps it.
3. The settled ticket or Spec that defines the unit, any parent Spec, applicable ADRs, the shared domain language, the repository state, and the loaded authorities provide no compatible answer.
4. Answering it yourself would cross the loaded philosophy's human-decision boundary — the choice creates a commitment reserved for humans.

A hard problem, low confidence, or an ordinary internal design choice fails these conditions and stays implementer-owned: solve it with the loaded methods inside the free-to-emerge space. An unsettled or half-specified caller-visible contract or replaceable seam is the standing example of condition 4 — never invent one; return it as a user-decision blocker.

### On a user-decision blocker

Freeze only the work whose correctness depends on the pending ruling; everything else in the unit keeps going:

1. Stop advancing the affected work the moment the blocker is confirmed — before or during implementation alike.
2. Complete and verify every unaffected, independently completable part; return only after no such part remains.
3. Commit material ruling-independent work as an **unblocked-work commit** — completed, verified work whose correctness does not depend on any pending ruling. When no material such work exists, produce no commit; never fabricate an empty or padding commit.
4. Leave the working tree clean: the unblocked-work commit holds everything that ships, and edits whose correctness depends on a pending ruling stay out of the tree — the report carries their state instead.
5. Return every pending decision together in one report (see Completion). An unblocked-work commit is shared progress, never Spec or ticket completion.

## Workflow

1. Read the referenced ticket or spec in full, including relevant parent context and comments.
2. Read repository instructions, the domain glossary, and relevant ADRs.
3. Verify that all declared blockers exist in the current repository state.
4. Before writing any code, search the codebase for existing similar implementations and conventions; reuse existing work instead of rewriting it.
5. Formally load the complete `emergent-design` skill; on load failure, stop per Fail closed on load failure.
6. Formally load the complete `codebase-design` skill; on load failure, stop the same way. Decide active or reference-only, and complete the `DEEPENING.md` load when Reference deepening requires it.
7. Where possible, formally load the complete `tdd` skill. This step is **load only** — the red→green loop and all code／test edits belong to step 8. When not using `tdd`, skip this step.
8. Implement only the identified unit of work. When step 7 loaded `tdd`, follow that skill's loop here (including its test and implementation edits); otherwise test at the seam the ticket specifies or per the repository's existing testing conventions. Edit code／tests only after steps 5–6 succeeded (and step 7 completed or was skipped).
9. Run focused tests and typechecking regularly.
10. Run the full relevant test suite when implementation is complete.
11. Use the `code-review` skill to review the result against repository standards and the originating ticket or spec.
12. Fix all review findings within this unit's scope.
13. Commit the completed work to the current branch.

A user-decision blocker confirmed at any step routes the run through On a user-decision blocker: steps 9–13 then apply to the unaffected work that continues, and the final commit is the unblocked-work commit when one is warranted.

## Carriers

Write toward the long-lived carrier that owns each piece of information; together they keep the finished work self-explaining:

- **Tests** preserve the observable behavior the user stories require, exercised through the agreed seams — the durable, executable record of what the one-shot Spec asked for.
- **Code** preserves the concrete implementation and every intent it can make evident through names, types, structure, and behavior, so a later reader understands the design without chasing anything outside the code.
- **Local comments** preserve only intent code cannot make evident. Reach for a **decision comment** on a single checkable question: does this implementation deliberately avoid a more obvious, more common approach? When it does, that choice is a fence — leave one line saying why the obvious approach was rejected, so the next reader does not tear the fence down and walk back into the problem you steered around. When the implementation is already the natural, obvious solution, the code speaks for itself — default to nothing, and earn the comment through the fence question. When you do write that line, it states the decision itself — the reason standing on its own — not a pointer back to whatever document prompted it.

This direction is a compass for what to write where, never a set of extra gates to pass. It governs every text file the run newly produces — source, tests, comments, docstrings, docs shipped alongside the code, and, when the unit's work is designing a skill, that skill's prompt text. The spec, issue, ticket, ADR, CONTEXT.md you read to do the work are inputs, not outputs, and commit messages and other git metadata sit outside it too. It binds the output you newly produce from here on, not code that already shipped.

## Boundaries

- Do not implement multiple tickets in one invocation.
- Do not start sibling or downstream tickets.
- Do not implement missing blockers.
- Do not reopen settled product or architecture decisions.
- Do not add speculative features or unrelated refactors.
- Do not cite the spec, issue, ticket, or ADR in the output you produce; let the code carry intent, and when a rationale is unavoidable state the decision itself, not the document (see Carriers).
- Do not create, switch, merge, or delete branches or worktrees.
- Do not manage ticket scheduling, integration, or completion status; the calling orchestrator owns those responsibilities.
- Do not declare completion while tests fail or acceptance criteria remain unmet.
- Do not edit code after a failed formal load of `emergent-design` or `codebase-design` (see Fail closed on load failure).
- Do not violate the non-redesign rule (including any Read of `DESIGN-IT-TWICE.md`; see codebase-design: active or reference-only).
- Do not settle a question that meets all four user-decision blocker conditions; return it as a user-decision blocker.
- When repository state or a missing prerequisite outside those four conditions prevents implementation, report the exact problem as an ordinary failure and stop.

## Completion — three outcomes

Begin every return with exactly one outcome line, so the caller reads the result instead of guessing from prose:

`Outcome: completed` ／ `Outcome: user-decision blocker` ／ `Outcome: failed`

**completed** — the whole unit is done and verified. Also return:

- Implementation summary
- Acceptance criteria status
- Tests, typechecks, and checks run
- Code-review findings and fixes
- Final commit SHA
- Any unresolved risk
- The codebase-design mode used (active or reference-only); when active, which loaded guidance shaped the work and confirmation that no alternative-interface exploration ran

**user-decision blocker** — every unaffected part is complete and verified, and at least one ruling is still needed. For each pending decision, return:

- The concrete question needing a ruling
- Why it belongs to the human side of the decision boundary
- The unfinished work affected by it

and once for the whole return:

- The verification performed on the completed unaffected work
- The unblocked-work commit SHA, or the explicit statement that no material ruling-independent work existed

**failed** — the unit could not be completed, and no pending human ruling explains why.

On failure, additionally return: the approaches already attempted, why each failed, and the directions that must not be tried again.
