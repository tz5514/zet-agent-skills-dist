# ADR Format

ADRs record an architecture decision (what + why). They live in **three explicit folders** under a bounded context's `docs/adr/`, and **the folder an ADR sits in is the single signal of its state and mutability**:

- `docs/adr/draft/` — decisions **not yet implemented** (`status: not_implemented_yet`); **freely editable** (a draft does not yet correspond to the codebase, so it is not ground truth).
- `docs/adr/active/` — decisions **implemented and still in force** (including ones only *partially* superseded); **immutable**.
- `docs/adr/archived/` — decisions that have been **fully superseded** (`status: fully_superseded`); **immutable**.

New ADRs use stable date-random ids across the **whole set** (see ADR ids): `{YYYYMMDD}-{random4}-{slug}.md`, where `random4` uses lowercase letters and digits excluding visually-confusable characters. Existing four-digit ADR filenames remain valid during migration and in historical references. Create any folder lazily — only when the first ADR that belongs in it is needed. To change an `active`/`archived` decision you never edit it in place: you write a new draft that supersedes it. The supersession scan compares a new/modified draft only against `active/` ADRs — **`draft/` and `archived/` are never comparison targets** (a draft is not yet ground truth; an archived decision cannot be superseded again).

An ADR carries a supersession lifecycle: a new decision never edits an old one, it *supersedes* it. The format below is what makes that lifecycle machine-navigable — who is still alive, who replaced whom, and exactly which decisions were replaced.

## Template

```md
---
status: not_implemented_yet
description: {a retrieval trigger — required; must not reveal the decision result}
---

# {Short title of the decision}

## Background

{The problem and its drivers — what situation made this decision necessary. Neutral historical framing only: not the answer, not current ground truth, and not a citation to another ADR as a stand-in for the old state. Optional / keep brief when the decision is self-evident.}

## Atomic Decisions

- **a.** {The first atomic decision: a single, independently-comparable unit of new decision content.}
- **b.** {The second atomic decision, if this is a compound decision.}

## Rationale

{Why this answer, how the atomic decisions relate, the basis, and any trade-off / limitation / residual risk. Carries the *why*, never restates the *what*, and never cites another ADR as a substitute for explaining the reason directly.}
```

**Body order is fixed** — three English headings serving as machine anchors: `## Background` (the problem space, *before* the decision — optional/brief if self-evident) → `## Atomic Decisions` (the atomic decisions — the authority) → `## Rationale` (the *why*, *after* the decision). Background frames the problem so the decision reads in context; the atomic decisions state what was decided exactly once; Rationale explains it without restating it. Decision content is recorded once, as atomic decisions; Background and Rationale carry only context and *why*. Apply the all-atomic-decisions-superseded truth test to all non-atomic sections: if every atomic decision in this ADR were later superseded, the `description`, Background, and Rationale must still read as true historical framing, not stale current truth.

## `write` operation contract

`write` is the clean content-writing operation. It creates a new draft ADR or substantively modifies an existing draft ADR; it does not run the quality-review loop, supersession scan, or promotion lifecycle. Orchestration belongs to the operation that calls `write`.

**Inputs:**

- `bounded_context_path` — optional when `target_adr_path` is supplied and derivable from that path; required for creating a new draft.
- `target_adr_path` — required for modifying an existing ADR. The operation derives and verifies the target's bounded context from this path.
- `mode` — `create` or `modify`.
- source material — the caller's current decision source, used only to write the ADR and to build review support data; it is not copied wholesale into the ADR.

**Scope:**

- Default scope is new draft ADR creation or existing draft ADR modification.
- For a new draft, derive `docs/adr/draft/` from the bounded context and generate a fresh ADR id for the new filename.
- For an existing target, verify the target belongs to the bounded context before writing.
- Active or archived ADR content rewrite is allowed only when the user explicitly requests one-time migration or special rewrite work. Ordinary `write`, `produce`, and dispatcher flows must not imply normal active/archived content mutation.

**Terminal states:**

- `written` — creates or modifies the target ADR and returns `target_adr_path`, `adr_id`, `created_or_modified`, `created_or_changed_atomic_decision_ids`, `source_decision_extract_path`, and `writer_self_check_evidence_status`.
- `no_adr` — the source material does not justify an ADR. No draft is created and no Source Decision Extract is written.
- `needs_context_ruling` — the write needs a new or changed CONTEXT.md term. Stop without inventing or writing unratified vocabulary.

**Source Decision Extract:**

The Source Decision Extract is non-durable ADR 品質審查輔助資料. It exists only to let a later blind ADR 品質審查 compare the draft against the decision source without giving the reviewer the full conversation or an answer key. It is written only to an OS tmp structured run directory or an equivalent non-bounded-context evidence bundle, and `write` returns its path.

Include only compact accounting of decision source material that must be preserved in the ADR: possible new decisions, explicit supersession intent, decision boundaries, and material exclusions that prevent accidental scope creep.

Exclude transcript content, expected final wording, reviewer answer keys, writer intent, repair history, rationale prose, Background-only facts, anti-confusion notes, not-the-topic scope corrections, already-existing facts, implementation details, examples, and writer-facing instructions as durable decision clauses. Writer self-check evidence may be retained only as status/path/accounting metadata for the writer or produce report; it is not reviewer input.

Writer self-check evidence records whether the writer checked Source Decision Extract closure, `description` answer leakage, section-role boundaries, atomicity, same-file id use, CONTEXT.md vocabulary, and support-data placement. Record status and evidence path only; do not turn the self-check into reviewer input or durable ADR prose.

## Frontmatter — machine-readable metadata only

Frontmatter holds short, structured metadata. Keep it lean: an ADR that no supersession has touched carries **the `status:` and `description:` lines** (both are always present — `status` is derived for every ADR, `description` is required from the draft stage on). The `superseded_by` / `supersedes` keys **grow only when a real supersession relationship exists** — never leave them as empty placeholders.

```yaml
status: not_implemented_yet   # DERIVED, never hand-set — one of: not_implemented_yet | fully_ground_truth | partially_superseded | fully_superseded (see "Status enum"); MUST stay consistent with folder + the per-atomic-decision record below
description: 管轄議題一句。觸發詞：詞1、詞2、詞3   # required retrieval trigger; single string ≤300 chars; see "The `description` field"
superseded_by:            # grows ONLY when THIS file has been superseded; lives on the superseded file
  - adr: <the OTHER file's stable id/filename>   # resolved across active/ + archived/, so archiving never breaks the link
    atomic_decisions:
      - { ours: <old atomic decision id in THIS file>, theirs: <new atomic decision id or [ids] in the OTHER file> }
      # listed PER ATOMIC DECISION — whether fully or partially superseded, every replaced atomic decision of THIS file is listed,
      # with multiple replacing decisions grouped in the `theirs` array,
      # so even a fully_superseded file lets you see which atomic decision of it was killed by whom
supersedes:               # grows ONLY when THIS file supersedes another; lives on the superseding file
  - adr: <the OTHER file's stable id/filename>   # resolved across active/ + archived/
    atomic_decisions:
      - { ours: <new atomic decision id or [ids] in THIS file>, theirs: <old atomic decision id in the OTHER file> }
      # SYMMETRIC to superseded_by — same relationship, ours/theirs swapped on each side (see "Symmetric supersession schema")
```

- **`status` is derived, never hand-set, and the legal values are exactly the four in "Status enum" below.** There is no `accepted` (removed) and no `deprecated` — "retired with no successor" is a different lifecycle, marked manually by a human, and is not what supersession scanning manages.
- **`status` must agree with the folder and the per-atomic-decision record** (it is the projection of both): a file in `draft/` is `not_implemented_yet`; otherwise none of its atomic decisions superseded ⇒ `fully_ground_truth`, some ⇒ `partially_superseded`, all ⇒ `fully_superseded`.
- **`adr` references use the stable id/filename and resolve across `active/` + `archived/`.** A link does not break when the target is archived (moved from `active/` to `archived/`); a supersession link never points at a draft.
- A file can be superseded by many files, and one new file can supersede many — both `superseded_by` and `supersedes` are **lists** that hold multiple relationship entries.

### Symmetric supersession schema

`supersedes` and `superseded_by` are **two views of the same relationship, 100% inter-convertible** — either side fully determines the other.

- **Every atomic decision pair is `{ ours, theirs }`**, and the words are file-relative: **`ours` is an atomic decision id in *the file this frontmatter sits in*; `theirs` is an atomic decision id in the *other* file.** The old decision side is always scalar. The new decision side is scalar for one replacing decision, or a flow-style id array when multiple new decisions jointly replace the same old decision.
- **The same relationship, mirrored.** When new ADR N supersedes atomic decision `x` of old ADR O via N's atomic decisions `a` and `b`: O's `superseded_by` carries `{adr: N, atomic_decisions: [{ours: x, theirs: [a, b]}]}`, and N's `supersedes` carries `{adr: O, atomic_decisions: [{ours: [a, b], theirs: x}]}`. Converting one side to the other is purely: swap `ours` ↔ `theirs` in each atomic decision pair, and swap the `adr` pointer to the other file. No information is added or lost in either direction.
- **One old atomic decision can be fully replaced by one or more new atomic decisions.** `supersedes` uses `{ ours: [a, b], theirs: x }` when multiple new decisions replace old decision `x`; `superseded_by` mirrors that as `{ ours: x, theirs: [a, b] }`. A single replacing decision stays scalar, not a one-item array. Do not force retained old payload plus new changes into one oversized new atomic decision just to express complete replacement.
- **No `apply_status` (or any per-entry status) field.** A superseded file's aggregate `status` is never stored per relationship — it is computed from (folder + which of its atomic decisions are superseded) by the status calculator, and written to the single `status` line. Storing a per-entry status would be a second copy that can drift.

### Status enum

`status` is **derived, not authored** — the folder plus the per-atomic-decision supersession record are the only authority, and `status` is their projection. Recompute it (and write it back) at every moment that can change it: when an ADR is created, when a draft is moved into `active/`, and when a supersession mark is applied. The four legal values:

- **`not_implemented_yet`** — the ADR is in `draft/` (not yet implemented; the folder alone decides this, regardless of any atomic decision record).
- **`fully_ground_truth`** — in `active/`, with **none** of its atomic decisions superseded.
- **`partially_superseded`** — in `active/`, with **some but not all** of its atomic decisions superseded (it still has live atomic decisions, so it stays in `active/`).
- **`fully_superseded`** — **all** of its atomic decisions superseded; this is exactly the condition for the file to live in `archived/`.

## The `description` field — a retrieval trigger

`description` is a **required** frontmatter field, written and edited **only while the ADR is a draft**; the moment the ADR moves into `active/`, the `description` locks together with the decision body and is **never edited again** (the one exception is the present one-time backfill of this newly-added field into ADRs that predate it — see "On pre-existing `active` ADRs" at the end of this section). It exists because a consumer's opening may load only the `description`s of `active/` ADRs — not their full text — and decides from them which few to read in full. So the field's one job is to make the agent pull this ADR up at the right moment.

**It is a trigger, not a summary.** Write it so a future discussion *recognises it should open this ADR* — never as a stand-in for the decision. The agent must not act on a `description` as if it were the decision content: the atomic decisions in `## Atomic Decisions` are the only authority, and a `description` that an agent treats as a summary is exactly how a still-binding atomic decision gets silently skipped.

**Form.** A single string, **≤ 300 characters** (CJK characters counted), holding **1–20** trigger keywords. Internal convention: `管轄議題一句。觸發詞：詞1、詞2、詞3` (one sentence on the governed issue, then `觸發詞：` and the comma-separated keywords). The length ceiling is a **single global value, not split by language** — every bounded context uses the same 300, whatever the canonical language of its glossary; character count is language-relative (Latin letters carry less per character than CJK), so a per-language ceiling was deliberately rejected in favour of one number a writing agent never has to look up. The length and count ceilings are a blow-out valve set far above the normal case — they are not a target to fill. **The ceiling is informational, never enforced.** It tells the writing agent the expected bound and is expected to be respected, but going over it triggers **no special handling at all** — no length-validation gate, no truncation, no "which keyword to cut" flow. A single over-long `description` does almost no harm, so adding any enforcement machinery is not worth its cost; the real control on keyword-padding is the discrimination test below, not this ceiling.

**Must contain — two parts:**

1. **The governed issue, one sentence.** Name the *question or aspect* this ADR settles, **phrased as a topic, never as the resolution** — it should read like a table-of-contents entry, not an abstract of the decision. Frame it as "the issue of *when / whether / how* X" and write it in **CONTEXT.md's ratified vocabulary** (see the keyword rule). Then apply the conclusion-leak test below.
2. **Trigger keywords.** The words a discussion would use to surface this ADR. **Lead with CONTEXT.md's ratified terms** — pull the relevant glossary headwords first, in their exact wording, then add discriminating synonyms and near-terms; **never use a term CONTEXT.md lists as _Avoid_** (the glossary is the governance boundary). Bias toward **recall** on discriminating synonyms — over-listing one is cheap; missing one means the ADR is not pulled when it should be. Keywords are retrieval hooks only, not summaries and not carriers of the selected answer.

**Must NOT contain:**

- **The decision's conclusion — the single most common mistake.** Apply the **conclusion-leak test**: *could a reader who sees only this `description` state what the ADR decided?* If yes, you have leaked the conclusion — rewrite the sentence so it names only the question/dimension the ADR settles, not the resolution. The danger is concrete: an agent that can infer the decision from the `description` stops reading and silently skips the atomic decisions — the exact failure the "trigger, not summary" rule exists to prevent.
- **The resolving property — a subtler form of the same leak.** A sentence can read as topic-framed and *still* leak by naming the **property that resolves the issue** instead of the **neutral dimension** the issue lives on. The discriminating test is **axis vs value**: does the word name the *axis* (the open question — neutral, the reader still cannot guess the answer) or the *value chosen on that axis* (the answer itself)? `可變性判準`（the mutability *criterion* — an axis) is safe; `不可竄改性質`（immutab*ility* — the value chosen) leaks. `schema 採什麼形式`（*what form* — an axis) is safe; `schema 對稱性`（symmetr*y* — the form chosen) leaks. The tell is any word *or framing* that is itself a settled quality — not only a bare adjective (`不可竄改`, `對稱`, `一律委派`, `即時寫入`), but also a **multi-word characterisation** (`雙讀者設計取向` — that the design serves two audiences *is* the decision) or a **presupposition** that treats the answer as a given premise (`呈現後的同意語意` — that consent is fixed *by presentation* is exactly what the ADR decided). Run the test on **every noun phrase** in the sentence, not just the adjectives: if removing it would stop a reader from naming the decision, it was carrying the answer. **Name the axis; never the value on it — and never smuggle the value in as a framing noun or a presupposition.**
- **Code-level implementation names** — functions / variables / classes (same reasoning as the ADR-body rule; they go stale).
- **Rationale, trade-offs, or background narrative** — those belong in `## Rationale`; a trigger does not need them.
- **ADR ids, ADR decision citations, or file paths** as durable content. If the old state matters, describe the old state directly and decision-relative, without making the reader open another ADR to know what issue this one governs.

**Worked example — conclusion-leak vs topic-framed** (same ADR, on deferred supersession marking):

- ✗ **Leaks the conclusion:** "推翻標記延後到 draft 實作搬入 active 才套用、schema 改為對稱可互轉。觸發詞：…" — a reader now knows *what was decided* (defer it; make the schema symmetric) and has no reason to open the ADR.
- ✓ **Topic only:** "推翻標記何時套用、以及兩側 supersession schema 採什麼形式的議題。觸發詞：推翻標記逆推處理、延後標記、對稱 schema、ours/theirs" — names the two *questions* the ADR settles; the answer still requires the full read. (`延後標記` is fine as a keyword *search hook*; the ban is on the sentence asserting the resolution.)

**Second worked example — the resolving-property leak** (axis vs value; on ADR-immutability):

- ✗ **Names the value:** "active/archived ADR 的**不可竄改性質**及可變性判準的議題。觸發詞：…" — `不可竄改` *is* the answer; the sentence reads as a topic but a reader already knows the decision.
- ✓ **Names the axis:** "active/archived ADR 的**可變性判準與修改途徑**的議題。觸發詞：…" — names the open question (are they mutable, and through what path); that they are immutable still requires the read.

**Third worked example — the value hidden as a framing noun or a presupposition** (on an output-template ADR and a consent ADR):

- ✗ **Framing noun carries it:** "輸出區塊是否採固定模板、及其**雙讀者設計取向**的議題。觸發詞：…" — `雙讀者設計取向` presupposes the templates serve two audiences, which *is* the decision.
- ✓ **Open question:** "輸出區塊是否採固定模板、以及該模板**服務哪些讀者**的議題。觸發詞：…" — `服務哪些讀者` is the open axis; that the answer turned out to be two (human + machine) still requires the read.
- ✗ **Presupposition carries it:** "推翻報告**呈現後的同意語意**…的議題。觸發詞：…" — ties consent to presentation, the ADR's answer, as a settled premise.
- ✓ **Open question:** "推翻報告呈現時**使用者同意如何認定**的議題。觸發詞：…" — names the open question; that presentation-without-objection counts as consent still requires the read.

**Discrimination test (apply to every keyword).** Ask: *"if I searched the bounded context's ADRs with only this word, how many would it pull up?"* If it would pull up a large fraction of them, the word has no discriminating power — **cut it**. Each keyword must separate *this* ADR from its siblings. This test, not the count ceiling, is what stops keyword-padding: padding can happen well under 20 keywords, and only the discrimination test catches it. Recall is therefore opened only to *discriminating* synonyms, never to generic words.

**Banned generic-word examples** (for this bounded context — each would match half the ADRs, so it discriminates nothing): `ADR`, `決策`, `推翻`, `掃描`, `流程`, `grill`, `documentation gate`, `輸出`, `驗證`. Naming the broad area is fine in the governed-issue sentence; do not list these as trigger keywords.

**Retrieval modifier ledger.** Treat every keyword or modifier as a retrieval hook with a clear role: ratified CONTEXT.md headword, discriminating synonym, near-term, or scope modifier. If a keyword does not have one of those roles, cut it. Do not use a modifier to smuggle the selected answer into `description`.

**Headword role fidelity.** When using a CONTEXT.md headword, preserve the role defined by the glossary. A lifecycle state headword must still mean a lifecycle state; a process headword must still mean that process. Do not reuse a ratified headword as a loose label for a new concept.

**Written once, then frozen — so write it to survive supersession.** Because the `description` locks at draft→`active` and is never updated, it can never be edited to track what happens to the ADR afterward. So it must be written so that **no future supersession of this ADR's atomic decisions can make it wrong**. It achieves that the same way the axis-vs-value rule already demands: by naming the *issue* the ADR addresses, never the decision content. An issue does not stop being the issue when its decision is overturned — "the issue of *what form* the schema takes" stays a true description of the ADR even after that decision is fully superseded; "the schema *is symmetric*" becomes false the moment it is. So **never scope the `description` to which atomic decisions are currently live — in either direction.** Do not drop part of the issue because an atomic decision was later superseded; and do not start naming the *superseded decision* (its chosen mechanism or value) in order to "cover" it — that is still decision content, still banned, and is how a stale mechanism's retired vocabulary gets dragged back in. A `partially_superseded` ADR's `description` is identical to the day it was written and names the **same issue** it always did, at issue level; the supersession is recorded in `superseded_by`, not in the trigger. (This is why the field can lock at all: a correctly axis-framed `description` needs no update when atomic decisions die.)

**Vocabulary is current as of when it was written.** A draft writes its `description` in the CONTEXT.md current at that moment. For the one-time backfill of a pre-existing ADR, "current" is **today's** CONTEXT.md — so when an older body uses a term the glossary has since moved to `_避免_` (e.g. a pre-lifecycle ADR says `歷史 ADR` / `本輪 grill ADR`, now retired in favour of `draft` / `active` / `archived`), the backfilled `description` uses the **current ratified term**, not the body's retired wording. **Mirroring the body is not an excuse for a retired term.** Cross-check the governed-issue sentence *and* every keyword against CONTEXT.md's `_避免_` list before finalising.

**Generation procedure (in order):**

1. State the governed issue in one topic-phrased sentence, in CONTEXT.md's vocabulary; then run the **conclusion-leak test** — if a reader could state the decision from it, rewrite it to name only the question. Then run the **axis-vs-value check** on **every noun phrase** in that sentence: if any names the *value chosen* rather than the *open axis* — whether as a bare adjective (`不可竄改` / `對稱`), a framing noun (`雙讀者設計取向`), or a presupposition (`呈現後的同意語意`) — swap it for the axis.
2. List possible trigger keywords — **lead with the exact CONTEXT.md glossary headwords** relevant to this ADR, then add their discriminating synonyms and near-terms; never use a term the glossary marks _Avoid_ — including when the ADR body itself uses a since-retired term (translate it to the current headword, per "Vocabulary is current as of when it was written").
3. Run the discrimination test on each possible keyword; drop any that would pull up a large fraction of the ADRs.
4. Check the whole string is ≤ 300 characters and holds 1–20 keywords; assemble as `議題。觸發詞：…`. (The ceiling is informational — over-length is not gated or truncated; see "Form".)
5. **Self-check (three questions):** *"(a) sees only this `description`, would another session think to open this ADR? (b) could it state the decision without opening it? (c) would it still be a correct description if any or all of this ADR's atomic decisions were later superseded?"* — (a) must be yes, (b) must be no, (c) must be yes.

**Quality responsibility.** The writer must run the self-check above while writing. ADR 品質審查 may later report `description` defects, but the writer must not outsource the first-pass judgement to a later reviewer. The extractor script verifies that a `description` can be *pulled out*, never that it is *good*.

**All `description` writing guidance lives here in ADR-FORMAT.md** — it is not duplicated into any other prompt file.

**On pre-existing `active` ADRs.** ADRs created before this field existed were given a `description` by a **one-time backfill**. That backfill is the only reason an immutable `active`/`archived` file's metadata was ever touched outside supersession marking — it closed a gap that adding the field created, and it does **not** make `active` metadata generally editable. The immutability rule stands unchanged: from here on, the only routine writes to an `active`/`archived` file are its supersession marking (`status` / `superseded_by`) and archival relocation.

## `## Atomic Decisions` — the atomic decisions, the single source of truth

The decision content lives in a fixed body block whose heading is **always the English `## Atomic Decisions`** — a language-independent machine anchor, so a scan can locate it whether the ADR is otherwise written in English, Chinese, or anything else.

- Each atomic decision carries a **stable `id`** (`a.`, `b.`, …).
- **`id` is frozen once written**: a later-added atomic decision takes the next unused letter; a deleted atomic decision's letter is **never recycled**; existing `id`s are **never reordered or renumbered**. This is what keeps every cross-file `{ ours, theirs }` reference pointing at the right atomic decision forever — an `id` cannot drift or be re-pointed when atomic decisions are added or removed, so a `superseded_by` link written months ago still resolves correctly.
- **Even a single-decision ADR lists its (one) atomic decision** — so a scan always has a clean, uniformly-formatted list to compare against.
- **A compound decision stays in one ADR**, using prose to describe how its atomic decisions relate — it is *not* hard-split into multiple files. Keeping related decisions together preserves the context that ties them.
- **Single source of truth**: the atomic decisions in `## Atomic Decisions` are the only authority for *what was decided*. `## Background` frames the problem and `## Rationale` carries the why / how-atomic-decisions-relate / basis / trade-offs; both may name same-file atomic decision ids but **must not restate a decision and must not contradict the atomic decisions**. A decision is stated exactly once — there is no parallel copy that can drift.
- **New decision content only**: atomic decisions must not carry existing facts, old decisions, source explanations, process notes, implementation details, supersession convenience restatements, examples, reviewer instructions, or rationale/background prose. If the text is not a new indivisible decision this ADR is making, it does not belong in `## Atomic Decisions`.

### Splitting decisions into atomic units — the partial-supersession test

"Atomic" is not "as small as logically possible." An atomic decision is the unit at which a future ADR could plausibly supersede it, so the test for where to split is the **partial-supersession test**, with a **convergence floor** that stops over-splitting.

- **One atomic decision answers one question and gives one answer.** Apply the test: *could a future ADR credibly supersede only part of this decision while the rest still stands — i.e. are these parts genuinely different questions that would get different future answers for different reasons?* If yes, split at that question seam — each side becomes its own atomic decision. If no, keep it as one decision. **Do not split just because a decision is logically decomposable**; almost any compound statement can be partially overturned in the abstract, and splitting on that alone produces an unusable swarm of fragments.
- **Convergence floor — multiple facets of one question stay together.** When several facets belong to the *same* question and would in practice change together (e.g. the input, output, and scope of one contract — overturn one and you re-decide them as a set), they are one atomic decision, not several. The floor is what keeps the partial-supersession test from atomising every decision down to nothing.
- **Relationship preservation — a *decided* relationship is its own atomic decision.** If the original continuous description carries a **decided** behavioural relationship between decisions — e.g. "decision `a`, under condition X, causes decision `b`" — splitting `a` and `b` naively would silently drop that relationship. The relationship is part of *what was decided*, so it must become its **own** atomic decision rather than being demoted to prose. A purely explanatory, non-decided relationship stays in prose; a binding conditional or causal relation becomes decision content. Promoting it to its own atomic decision also lets it be superseded independently. Decisions with **no** causal or conditional relationship are simply independent — do not invent a relationship decision for them.
- **Same-file ids carry references, not domain content.** It is valid for one atomic decision to refer to another same-file atomic decision by id when a binding relation must be preserved, but the id itself must not hide the domain content. The sentence must still say the actual condition, default, exception, or relation in domain language.
- **Default decisions and conditional relations split.** When a decision has a default rule and a conditional override, write the default as one atomic decision and the condition/override relation as another atomic decision. Do not make one bullet carry both the base rule and the conditional dependency if a future ADR could plausibly supersede only the condition.
- **Protected payload vs id-carried content.** The protected payload is the domain decision text in the atomic decision sentence. Same-file ids are references only. If deleting the id would delete the reader's ability to understand the domain rule, the payload is hidden in the id and must be rewritten into the sentence.
- **Dependent content atoms.** If one decision depends on another in a binding way, the dependency itself is decision content and must be represented by an atomic decision or by explicit domain text inside an existing atomic decision. Do not leave a binding dependency only in Background or Rationale.
- **Readiness/sufficiency endpoint atoms.** When the source decision defines a readiness threshold, sufficiency endpoint, acceptance endpoint, or stop condition, that endpoint is decision content. Put it in an atomic decision instead of leaving it as rationale or process narration.
- **Enforcement is the author's own self-check at `write` time.** Atomicity is a semantic judgement. The author applies the test above while writing; ADR 品質審查 may later report defects, but the writer must not defer the judgement.
- **Cheap structural lint as a self-check aid — `scripts/atomicity_lint.py`.** Run the atomicity lint over your own draft as a near-zero-cost backstop. It mechanically scans each decision bullet in `## Atomic Decisions` and flags two structural smells: a **markdown table row** crammed into one bullet, and a **multi-item enumeration** (two or more nested sub-bullets or inline `N.` ordinals) crammed into one bullet — the most common way a multi-question decision is smuggled in as one bullet. The lint only **flags suspects by a reproducible counting rule**; it does not decide atomicity (that semantic re-judgement, via the partial-supersession test, stays with you), it never blocks, and it dispatches no LLM. A flag is a prompt to re-apply the test, not a verdict.

**Design trade-off (recorded here so a reader understands it):** atomic decision content lives in the body, not in frontmatter, because frontmatter's extraction advantage is for *short* metadata; multi-sentence decision content stuffed into YAML is both cramped and brittle. The cost is that the body block relies on the fixed English heading to stay machine-locatable (a frontmatter key is inherently fixed; a body heading has to be enforced — which `## Atomic Decisions` does).

## `## Background` and `## Rationale` — historical context, never current ground truth

The supersession mechanism tracks **only** `## Atomic Decisions` — `status` and `superseded_by` are recorded per atomic decision. `## Background` and `## Rationale` are immutable but **untracked** prose: when a decision is superseded, these two sections are not (and cannot be) updated. So they are defined as **historical, point-in-time** context, and they must never carry current ground truth — otherwise a fact written into them silently rots the moment a decision is overturned, and a later agent reading the full text mistakes the frozen prose for the present.

- **`## Background` records the situation *before* the decision** — the premises and circumstances that made the decision necessary. It carries pre-decision context only: never decision content, never current ground truth.
- **`## Rationale` records the considerations *at the moment of deciding*** — the reasons, weighing, and trade-offs that led to the answer. It carries those deliberations only: never decision content, never current ground truth.
- **Both sections sit outside the supersession mechanism's reach** — untracked, never updated when a decision dies — so **any current fact or binding relationship belongs in `## Atomic Decisions`**, which is tracked and supersedable. This generalises the relationship-preservation rule: it is not only decided relationships but *every* current ground truth that must live in `## Atomic Decisions`, never in the two prose sections.
- **Write both sections as history that survives supersession** — phrase them as "the premise *was* …", "we *weighed* …", so that even after the decision is later overturned, "what the premise was" and "what we weighed at the time" stay true. This is the same survive-supersession discipline the `description` field already follows (axis-not-value framing), applied to prose.
- **A reader treats both sections as historical context and reads current truth only from `## Atomic Decisions` plus each atomic decision's `status`.** Never assume Background or Rationale still reflects the present. The deliberately strict line — all current ground truth concentrated in the tracked `## Atomic Decisions` rather than asking a reader to sort historical prose from still-true prose sentence by sentence — gives the reader a single rule: *for the present, read only `## Atomic Decisions` and its statuses.*
- **Do not cite other ADR decisions or ADR ids as durable content.** If the old state matters, describe the old state directly. If an external source matters, cite that source directly. Background and Rationale must remain meaningful if all other ADR files are unavailable.
- **Apply the all-atomic-decisions-superseded truth test.** If every atomic decision in this ADR later dies, Background and Rationale must still be true as the historical problem and reasoning. If any sentence becomes false, it was carrying decision content or current ground truth and must move to `## Atomic Decisions` or be rewritten.
- **Rationale selected-facet scan.** Scan every selected facet named in Rationale: if it states the chosen behaviour, threshold, default, exception, dependency, endpoint, or current ground truth, move it into `## Atomic Decisions`. Rationale may explain why a facet was selected; it must not be the only place the selected facet is recorded.

## Supersession relationships live ONLY in frontmatter

A relationship counts as a supersession **only** when it is recorded in `superseded_by` / `supersedes`. Body prose never creates a supersession relationship — the scan and every reader recognise supersession only from frontmatter. This keeps casual prose from being misread as lifecycle metadata.

## Self-sufficiency — a shipped file must outlive its conversation

An ADR (like any shipped document, including a CONTEXT.md entry) is written during a conversation but read without it. The judgement test: delete the conversation that produced the file — the file must still be fully meaningful, with every reference resolvable. Apply this test before considering a file done.

Only these reference forms are legal in a shipped file:

1. **Descriptive text** — naming a thing by its content ("the retry queue introduced for failed webhooks"), not by a conversation-local codename.
2. **Machine lifecycle links** — the `adr:` values inside `superseded_by` / `supersedes`, where the frontmatter schema owns the relationship.
3. **External source links** — markdown links to sources outside the repo.

A premise or codename that resolves through none of the three forms is a violation: option codes ("Option B" with no in-file definition), deictic phrases ("the approach we just discussed"), plan-stage labels ("Phase 2"). These read fine to the writer — whose conversation resolves them — and read as nothing to every reader after.

## No ADR-id prose citations

- **ADR body prose does not cite ADR ids, ADR filenames, or other ADR decision ids as durable content.** Encode the behaviour directly in the current ADR instead of making a reader open another ADR to know what this one means.
- **The frontmatter `adr:` keys are unaffected** — they are machine fields keeping their own schema. A supersession link always points at a file that lives in an implemented lifecycle folder, never at a draft.
- **Conversation output is not bound by this rule.** Chat output follows its own output templates and may carry point-in-time file links.
- **Existing citations inside immutable ADRs stay frozen unless an explicit id-migration pass rewrites only the reference spelling.** `active/` and `archived/` ADRs are immutable; they are read as-is, and ordinary work never retro-fixes prose citations.

## Writing conventions for ADR prose

Two conventions govern what an ADR's body may name and how it names recurring output blocks.

- **Do not record code-level implementation names; record stable contract names instead.** Function, variable, class, and internal-helper names are implementation-internal identifiers that drift as the code evolves under emergent design, so writing them into an ADR makes the record go stale while the decision itself has not changed. What an ADR *may* name are stable contract-level names: shipped documents, data formats, process rules, output blocks, and machine-readable fields. When you need to point at a concrete implementation, leave that to the code, the tests, or the implementation plan — not the ADR.
- **Name a recurring output block by its role, never by its emoji glyph.** When an ADR's prose refers to one of grill's fixed output blocks, call it by its role — e.g. "the ADR supersession report", "the self-sufficiency verification block" — and do not write the emoji glyph that prefixes that block's label. The role name is taken from that block's label text in the consumer's output-format spec, which is the single source for these names. This convention is scoped to **ADR prose only**: it does not touch that output-format spec's own block label lines, where the leading `### ` + emoji is a machine-identification contract and must stay; and it does not bind emoji references in other prose such as a SKILL.md, which is not an ADR.

## ADR ids

New ADRs use ids in the form `{YYYYMMDD}-{random4}` and filenames in the form `{YYYYMMDD}-{random4}-{slug}.md`. The date is the creation date. `random4` is generated from lowercase digits/letters excluding `0`, `o`, `i`, and `l`, so ids remain readable in filenames and prose-free machine links. Generate a fresh id for every new draft; do not scan for the highest existing filename and increment it. ADR ids are **never reused** — once an id is taken it is never reclaimed, even after the original is archived. Historical four-digit ids and filenames remain valid for existing ADRs and for migration tooling.

## When to offer an ADR

All three of these must be true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will look at the code and wonder "why on earth did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons

If a decision is easy to reverse, skip it — you'll just reverse it. If it's not surprising, nobody will wonder why. If there was no real alternative, there's nothing to record beyond "we did the obvious thing."

### What qualifies

- **Architectural shape.** "We're using a monorepo." "The write model is event-sourced, the read model is projected into Postgres."
- **Integration patterns between bounded contexts.** "Ordering and Billing communicate via domain events, not synchronous HTTP."
- **Technology choices that carry lock-in.** Database, message bus, auth provider, deployment target. Not every library — just the ones that would take a quarter to swap out.
- **Boundary and scope decisions.** "Customer data is owned by the Customer bounded context; other bounded contexts reference it by ID only." The explicit no-s are as valuable as the yes-s.
- **Deliberate deviations from the obvious path.** "We're using manual SQL instead of an ORM because X." Anything where a reasonable reader would assume the opposite. These stop the next engineer from "fixing" something that was deliberate.
- **Constraints not visible in the code.** "We can't use AWS because of compliance requirements." "Response times must be under 200ms because of the partner API contract."
- **Rejected alternatives when the rejection is non-obvious.** If you considered GraphQL and picked REST for subtle reasons, record it — otherwise someone will suggest GraphQL again in six months.
