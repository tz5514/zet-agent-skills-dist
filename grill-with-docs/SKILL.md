---
name: grill-with-docs
description: Grilling session that surfaces the implicit assumptions behind your plan, challenges it against the existing domain model, sharpens terminology, and updates documentation (CONTEXT.md, ADRs) inline as decisions are made. Use when user wants to stress-test a plan against their project's language and documented decisions.
disable-model-invocation: true
---

<what-to-do>

## Before asking any questions

Load the domain context for this session:

1. Check if `CONTEXT-MAP.md` exists at the repo root.
   - If yes: read it, identify which bounded context matches the user's topic, read that bounded context's `CONTEXT.md`.
   - If no: check for a root `CONTEXT.md`. Read it if it exists.
2. Read [OUTPUT-FORMAT.md](./OUTPUT-FORMAT.md) in the same batch — it holds the fixed templates for every recurring output block this round emits (binding, documentation-gate results, scan reports, pending-items map, closing blocks). Every such block must use its template; skipping this read means falling back to improvised output for the whole round.
3. **Load the bounded context's ADRs by the fixed three-state load sequence.** ADRs live in three subfolders of `docs/adr/` — `draft/` (not yet implemented, freely editable), `active/` (implemented and still in force, immutable), `archived/` (fully superseded, immutable) — and **the folder a file sits in is the single signal of its state and mutability** (the full three-state lifecycle model is governed by `/adr` — invoke it for the ADR mechanism). Load them in this exact order, never all at once:
   1. **All `draft/` ADRs — full text.** Frame every one as a **tentative, editable draft that is not ground truth**: it is loaded only so a new decision can be checked against it for conflict (and the draft amended if they clash), never built on as an already-implemented basis. Continuing a discussion *on top of* a specific draft requires the user to say so explicitly.
   2. **All `active/` ADR `description`s — not their full text.** Obtain them by **invoking `/adr` via the Skill tool with the `extract-active-adr-desc` operation keyword**, which returns the `{filename → description}` index table for this bounded context's `active/` folder; read only that table — do not open the active files, and do not run any `/adr` internal script directly (the ADR mechanism is reached only through `/adr`). A `description` is a retrieval trigger (its spec is governed by `/adr`), so the table tells you which active decisions exist and when each becomes relevant, without spending context on full text you will not use.
   3. **The full text of the active ADRs the current topic makes relevant.** Judge relevance from the descriptions and formally load those few in full — that is the real, complete decision context you begin with.
   4. **Never proactively load `archived/`.** Two exceptions only: the user names a specific archived ADR to read, or the user asks you to scan `archived/` for an already-superseded record on a particular topic. Otherwise archived stays out of context, so retired decisions cannot pollute it.

   After the opening sequence, keep loading relevant active full text **on demand** throughout the discussion, at a **low threshold, triggered by relevance**: once you have genuinely judged an active ADR related to the current topic, read it readily rather than worrying about over-reading — mis-reading an unrelated ADR costs little, while missing a related one is backstopped by the later draft promotion flow, not during the interview. It must still rest on a real, reasoned relevance, not unconditional full loading (which would recreate the load-everything problem the description index exists to solve).
4. Existing terms and active ADRs are your starting constraints. Every question you ask must respect them. If the user's plan conflicts with an existing term or an active ADR, surface the conflict as a question instead of silently ignoring the prior decision.
5. **Bind this round and emit the 📍 block.** One grill round operates exactly one bounded context — the one identified in step 1 (inferred via `CONTEXT-MAP.md`, or implied by the single root `CONTEXT.md`; if the inference is uncertain, ask the user directly). Every CONTEXT.md and ADR write this round stays inside that bounded context. If the bound bounded context has no CONTEXT.md yet, create the skeleton file **now, at binding time**: title + a one-sentence description + an empty Language section — **zero terms**, which keeps the skeleton compatible with the CONTEXT.md write iron rule (no term enters the file without the user's explicit ratification; see the documentation gate). The path the binding block prints must always point at a real file. Then output the 📍 binding block using its template in OUTPUT-FORMAT.md, filling the active / archived / draft counts from the folders you just loaded.

## What you are doing in this interview

Your primary job is not to walk a checklist of topics. It is to **surface the implicit assumptions** — the things the user takes for granted and would not think to mention, but which shape the spec. The user is here to be interviewed, not to find questions; if you do not surface an assumption, it will not appear in the conversation, and the resulting PRD will silently bake in a guess.

After every answer, ask yourself before anything else: in what they just said, what did they assume without saying? What context did they presume you already share? What edge cases or trade-offs did they skip past because the answer felt obvious to them? Those are your next questions.

When you identify an assumption to surface, classify its source before framing it: does this follow directly from what the user has said, or are you projecting from your priors? Frame the second kind as a hypothesis to check, not as the user's assumption: "I'm guessing you're assuming X here — is that right, or have you been thinking about it differently?" Never present a projected assumption as a fact about the user's mental model.

**No invisible premises.** This extends one step further: any premise that a later step will depend on — the next question, a document write, or the downstream spec — must appear in your **visible text output**, or be archived into CONTEXT.md / an ADR. It must never live only in your reasoning. A premise you formed in thinking and silently treated as settled was never put to the user, so they had no chance to challenge it; and a downstream process that reconstructs context from the conversation text alone (not your thinking) loses it entirely, leaving every decision that rested on it without its reason. So before you build on a premise you projected, surface it as a hypothesis to confirm (per the rule above) — do not carry it forward as if the user had already agreed. This is a behavioural discipline, not a mechanical check: nothing scans your output for hidden premises, so the obligation rests on you. (Purely operational process state — a verifier's retry count, a scan's internal bookkeeping — is not such a premise and is exempt; it shapes no decision and surfaces at the point it actually matters.)

This is the engine that drives the interview. The techniques in `<supporting-info>` (sharpening fuzzy language, edge-case scenarios, cross-referencing code) are supporting tools that help you execute it — not goals of their own.

Treat depth as obligation, not courtesy. Every additional layer of probing brings more of what would otherwise stay buried in the user's head into the conversation.

A note on word choice. When phrasing your questions and proposals, prefer plain language over jargon. Words like "canonical", "artifact", "kind", "digest", "verdict" feel precise to you but make the conversation harder to follow. Use the simpler word the user would naturally use, unless the technical term carries a meaning that no plain word captures. The user is the domain expert here — speak their language, not yours.

This goes deeper than vocabulary. Your default mode of explanation should be: precise terms from the project's shared vocabulary (the CONTEXT.md glossary) plus a concrete user story illustrating the actual flow. Not abstract noun phrases like "entity transition" or "partial failure semantics" — those are how you think, not how the user lives the system. A user story is: a real role, doing a real action, encountering a real situation, with a real outcome. "A customer hits cancel on an order that has already shipped" lands. "Handling state transitions with side effects under partial failure" does not.

Reach for cross-domain analogies only when the abstraction is genuinely hard to describe directly, or when the user has signalled multiple times they are not following. Default to staying inside the project's own vocabulary and flows — that almost always communicates effectively without leaving the domain. A misplaced analogy can simplify away the very detail that matters.

Why this matters structurally, not as a courtesy: the grill-and-PRD phase is the only phase where the human is fully in the loop before AFK execution begins. If the user does not understand what is being decided, the user is not participating in the decision. A decision the user did not participate in becomes a black box in the spec — and every downstream gate that checks against that spec carries that blindness forward. "Speak so the user understands" is therefore not a polite habit; it is what keeps the spec sound.

## Asking each question

The principle behind this filter: every question you ask should carry genuine decision content the user cannot delegate — to general engineering knowledge, or to you. Volume of questions is not the concern; the concern is asking questions whose answers you already know or could derive, which dilutes the signal of the questions that genuinely need the user's input.

Before you put forward a point, issue, or recommended answer, ground its load-bearing premises (when unsure whether a premise is load-bearing, treat it as one) — not just the headline claim — against the most direct source available, in this priority order:

1. **Codebase or existing docs.** This tier fires only when the premise actually connects to something the codebase implements, names, or constrains — it is not a per-premise step; trigger it on a real connection to existing code, not for every premise (the triggers are listed in `<supporting-info>` under "Cross-reference with code"). When it does fire, the code is the most reliable ground truth for what the system actually does, and an answer built on what you remember is weaker than one built on what the system is. For a brand-new feature the codebase will often have nothing to offer — that is expected, not a failure; move to the next tier rather than hunting for code that does not exist. If a check would need so much code that your context risks saturation, delegate it to an Explore subagent with a focused brief and use only its summary.
2. **The web.** If (1) cannot settle it, or local evidence is too thin for high confidence, you **must** search for high-credibility references — but a pure design judgement, with nothing factual to verify, is exempt and goes straight to tier 3. Treat web lookup as a normal, expected move — not a last resort.
3. **Your own speculation or design judgement.** Only when neither of the above yields solid support — whether because the fact could not be verified, or because the point is a design call with nothing factual to verify. Advance it, but say plainly that its confidence is low.

Your own training knowledge does not count as high-confidence evidence — there is no "I just know" escape hatch: if you believe something is a fact or best practice but the codebase does not show it, find a web source; if you cannot, it drops to low confidence. A premise resting on a checkable fact must be checked; a pure design judgement, with nothing factual to verify, is not web-searched — it is the tier-3 case above, advanced with low confidence. This is where you do not save tokens: the cost of a search is far smaller than the cost of a confident, wrong premise being ratified into the spec.

When you put the point to the user, attach its basis inline. If it has a source (tier 1 or 2), wrap the descriptive text in a markdown link to that source (a code location or a web reference) rather than printing the raw URL. If it has no source — a tier-3 judgement or unverified guess, which by definition has nothing to link — do not manufacture a link; instead say in words, plainly, that this is your own low-confidence call. Let the confidence you state follow the tier — codebase or web can be high, a tier-3 call is low — never a self-rated number. Keep solid-source tags quiet and the no-source / low-confidence flags loud, so your basis-tags concentrate the user's scrutiny on what is weak rather than dispersing it.

This grounding catches only premises you actually surface as claims; a premise you are so sure of that you never state it can still slip through, and that residual is for the user and any downstream review to catch — not something this step can guarantee.

Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each candidate question, form your own recommended answer in your head. Hold this explicitly as your prior — your view, not anything the user has said yet. You will need this distinction later when the engine asks you to classify whether an assumption you are about to surface comes from the user or from your priors. Then run this filter before deciding whether to ask:

1. **Is the decision under this question architecture-level?** A decision is architecture-level if it meets ALL three ADR criteria: (a) hard to reverse, (b) surprising without context, (c) the result of a real trade-off. If yes — or if you are not sure whether it qualifies — you **must ask**, regardless of whether you can guess a default answer. Architecture-level decisions need explicit user ratification because they shape every downstream question and are expensive to undo. When in doubt, treat as architecture-level.

2. **Otherwise: can you answer this from general engineering knowledge or the existing codebase?** If yes, decide it yourself, state your choice in passing so the user can object if it is wrong, do not ask. Only ask non-architectural questions where the answer depends on project-specific context, business logic edge cases, or user-specific preferences that general knowledge cannot supply.

Ask the questions one at a time, waiting for feedback on each question before continuing. If a question can be answered by exploring the codebase, explore the codebase instead.

## After each answer — documentation gate

Before asking the next question, run this gate.

**Cycle semantics — write immediately; batch only the checks.** One documentation-gate cycle is the one-time processing of a single ratified answer. Every document write that answer triggers executes immediately, at ratification time — never delay a write into a later cycle to accumulate a batch. "Batch" refers only to what happens after the writes: the delivery-check results merge their output per cycle — **batching governs the checks, never the write timing**. At interview time the ADR write goes through `produce-for-HITL`, which runs only the lightweight write plus the CONTEXT.md glossary-approval preflight and no supersession scan, so the cycle's output blocks are 📝 → ✅ — the 🔍 / 📣 scan blocks are not emitted at interview time (their templates in OUTPUT-FORMAT.md stay for non-interview or future use).

**Ratification check first**: the routing in steps 1–3 applies only to answers the user has **explicitly ratified** — phrases like "yes, decided", "let's go with that", "OK that's the answer", or any equivalent explicit ratification signal in the user's language. If the user is still discussing, weighing, or has not given a clear "this is the answer", skip the routing — the decision is not yet made. The pending-items step at the end always runs.

**Route the ratified answer — don't just dump it.** The failure mode this prevents: checking "is this a term?", then "is this a decision?", and when neither fires, falling silent — so an answer that belongs in neither document vanishes without the user noticing. Walk every ratified answer through all three outcomes below. The first two fire independently and can both apply (one answer can be both a term and a decision). The third fires only when neither of the first two did, and it is spoken, not silent.

1. **CONTEXT.md — did this answer pin down, rename, or redefine a domain term?** If yes, update `CONTEXT.md` now, before the next question. `CONTEXT.md` is a glossary only — no implementation details, no specs, no temporary notes. Use the format in [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md). **When the answer renames or retires a term, remove the old entry whole — no `deprecated` remnant** (the full rule and the `_Avoid_`-alias mechanism for an old word still living in an immutable ADR body: see the Rules section of [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md)).

   **The CONTEXT.md write iron rule (holds across the whole grill flow, not just at this step):** no term the user has not explicitly ratified is ever written into CONTEXT.md — you propose, the user confirms, then you write; no exceptions. The rule applies at equal width to **modifying existing terms**: any semantic modification requires the user's explicit ratification or request. Carrying out the synchronisation of an already-ratified decision (e.g. propagating a ratified rename into related entries) counts as requested and may proceed directly — but must be shown explicitly in the 📝 block. The design goal behind the rule: CONTEXT.md must never contain a word or meaning the user has no memory of ratifying — one unratified entry is how a glossary starts to rot.

2. **An ADR — did this answer make a decision that meets ALL three ADR criteria**: (a) hard to reverse, (b) surprising without context, (c) the result of a real trade-off? If any criterion is missing, skip the ADR. Otherwise deliver it now, before the next question — a grill records decisions that are not yet implemented, so a new ADR is written into **`docs/adr/draft/`** with `status: not_implemented_yet` and its required `description` (it moves to `active/` only when implemented, the last task of the downstream build). **Invoke `/adr` via the Skill tool with the `produce-for-HITL` operation keyword** (this same keyword covers both creating a new draft and modifying an existing one) — `/adr` is the authoritative home for ADR writing, ADR 品質審查, support-data handling, supersession scanning, and lifecycle handoff. `produce-for-HITL` is the lightweight interview-time path: it runs only the write and the CONTEXT.md glossary-approval preflight — the two things that cannot wait for a user who is mid-interview — and deliberately defers full ADR quality review and supersession scanning, which would otherwise stall the interview on every filing. Follow its structured return rather than embedding those mechanisms here.

   **This is the ADR-lifecycle hinge.** Writing or modifying an ADR here is governed by `/adr`'s ADR mechanism (format, lifecycle, ADR 品質審查, supersession scanning, and supersession-mark back-derivation). Two boundaries apply at this point, every time, no exceptions:
   - **Immutability guard.** The folder a file sits in is the single mutability signal: only `draft/` ADRs are editable; `active/` and `archived/` are immutable. If the decision you are about to record changes a decision already in an `active/` (or `archived/`) ADR, you may **not** edit that file's decision content — route to writing a **new draft** ADR that supersedes it. `/adr` governs how the supersession relationship is later recorded into the new draft's `supersedes` and how the active side is marked. Because the interview-time path does not run the supersession scan, no `supersedes` detail is written at grill time — it is produced by `/adr revise-and-promote-draft-to-active` when the user carries the draft through draft→active migration, and the active side is marked at that migration.
   - **Deferred scan.** The interview-time path runs no supersession scan: `produce-for-HITL` writes the draft and runs the CONTEXT.md glossary-approval preflight, then stops. So at grill time there is no scan result to report, and the two scan output channels (🔍 routine line, 📣 report table) are **not emitted during the interview** — their templates stay in OUTPUT-FORMAT.md for non-interview or future use, they are simply not triggered here. The full supersession scan is deferred to the user's later draft promotion flow: the user invokes `/adr revise-and-promote-draft-to-active`, and that flow runs the full review and supersession scan before promotion; do not call `scan-supersession` from the gate. This is a deliberate trade of interview-time scan coverage for interview continuity, not a missing step — do not "fix" it by adding a scan back into the gate.

3. **Neither — did the answer match neither of the above?** Then it does not get filed — but say so in one line, so the user sees the outcome rather than a silent skip: that one line is the 📝 block's single-line not-filing variant (template in OUTPUT-FORMAT.md), naming in one sentence why the answer fits neither document and that it stays in the conversation for the user to record elsewhere if wanted. That spoken "not filing this" is the entire purpose of this outcome: it turns a decision that fits neither document from something that silently evaporates into something the user can see and override. CONTEXT.md and ADRs are the only documents this gate writes — do not invent a third file type to hold the leftover.

After routing a ratified answer, emit the **📝 block** (template in OUTPUT-FORMAT.md): list exactly the filing situations that occurred in this cycle — new ADR, modified this-round ADR, new CONTEXT.md term, modified existing term — or the single-line not-filing variant when none did. Then, if this cycle wrote any file:

4. **Delivery result handling — foreground, after the writes.** For ADR writes, consume `/adr produce-for-HITL`'s structured return. Before every dispatch decision, use `scripts/hitl_ruling_contract.py` to validate the four-field direct output and read and validate its outer report; never route from an unchecked direct status or from a ruling projection alone. Dispatch on the validated `final_status`:
   - `hitl_preflight_passed` → emit the merged ✅ delivery-check block stating the **lightweight preflight passed (full ADR quality review and supersession scan have not run)** — never word it as a completed `produce` acceptance pass. Do not emit the 🔍 / 📣 scan blocks at interview time; no scan ran.
   - `no_adr` → reflect that in the 📝 not-filing variant.
   - `needs_context_ruling` — either the early `write` terminal, or the preflight reporting a CONTEXT.md glossary-approval need; both carry `needs_user_ruling: true` — raise the user ruling and stop for the user's reply, do not continue to the next question.
   - `needs_user_ruling` with terminal `not_an_adr_candidate` — present the necessity ruling first and end the output turn. Do not call the terminal a pass and do not discard the validated outer report. If the user retains the draft, re-read and validate the same outer report; do not rerun `produce-for-HITL`. When that outer also carries glossary action data, present the glossary ruling and end the output turn again. After the glossary reply, or immediately when the same outer has no glossary action data, resume the original documentation flow.
   - `failed` — the draft could not be parsed, or a tool failed — surface the returned `structured_report_path` and stop; do not continue as if delivery passed.

   Necessity de-duplication is same-session conversation state only. Build its identity from the resolved draft path, terminal, gate id, and the complete raw validated necessity findings — including `action_data: null` and every other field. Canonicalize each finding only as `json.dumps(finding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")`, sort those raw UTF-8 bytes in lexicographic order without Unicode normalization, and retain the resulting identity in conversation context only. Never write it to the draft, frontmatter, or any persistent file. The same finding objects in a different reviewer output order are the same identity; any changed object is a new ruling. A seen necessity identity suppresses only that repeated necessity presentation and must not suppress glossary action data from a newly validated outer report.

   For CONTEXT.md-only writes, do not call a removed `/adr` verification operation; apply the CONTEXT.md iron rule from step 1 and emit the ✅ delivery-check block only when the written entry is self-sufficient under this skill's local glossary rules.

Then, always — whether or not the answer was ratified:

5. **Pending architecture-level items — maintain the running list, re-orient.** Scan back through the conversation: which architecture-level questions have been asked but not yet ratified? This list serves two purposes: (a) it orients your next question to the whole design tree, not just the local exchange — architectural items that block other questions take precedence, and a pending item that makes a sub-question premature should defer that sub-question; (b) it is the running record that the closing gate will require.

   Before asking the next question, state your current map in one line — addressed to the user — using the 🗺️ pending-items template in OUTPUT-FORMAT.md, showing the pending items and where the next question sits. This externalisation verifies your map is current and lets the user correct it if it has drifted.

   Presented supersession markings stay **out** of this list: presenting the 📣 report was the review moment — no rollback requested means consent, and a presented marking is never re-reminded (the rollback right itself never expires; the user can still ask for a symmetric rollback at any later point).

Do not batch updates to `CONTEXT.md` or ADRs. A resolved term or decided trade-off that isn't written down now will be forgotten by the next session.

## Output-turn structure — one aspect per turn

When an answer needs the user's ruling, **one output turn handles only one aspect.** The user's attention is the load-bearing resource of the grill: making them switch between several decisions in one turn degrades every ruling. The whole turn structure runs off a single distinction — does a block **halt the flow until the user replies**, or does it just report a completed result?

- **A user ruling point halts the flow and cannot resume until the user replies** with the ruling it asks for. A ruling point **ends the output turn**: you append no further decision question after it; the next aspect's question waits until the user has replied. Two ruling points have **no** corresponding single fixed-template block (so they cannot be classified by an OUTPUT-FORMAT.md tag and are stated here):
  - the **confirmation before an undefined-term candidate is written** into CONTEXT.md (the CONTEXT.md write iron rule);
  - **a design question you put to the user** — the question itself. The closing checklist (🏁) is this kind too: each unratified item it puts back to the user to ratify or defer is a design question, which is why that block is a ruling point and the session cannot close until every item is handled.
- **A non-blocking notification block reports a completed result, needs no reply, and does not end the turn** — so it may sit in the same turn as that turn's single aspect question. The supersession report is one such block (presenting it *is* the review moment, so it does not halt the flow and is not a ruling point).
- **The documentation gate does not run a whole batch of results plus the next question straight through.** When any ruling point fires mid-cycle, the output turn **ends at that ruling point**; the next aspect's question is held until the user replies. The non-blocking notifications produced up to that point still print — only the next *question* is withheld.

This split is total: every stop/ask point in this skill is **either** a ruling point (it halts and waits) **or** a non-blocking notification (everything else this flow emits) — there is no third category, and none is left unclassified. The two categories are the CONTEXT.md terms *user ruling point* and *non-blocking notification block*. For each fixed output block, which class it is (and, for the supersession report, the consent-by-presentation semantics and its ADR basis) is single-sourced from that block's turn-role tag on its template in OUTPUT-FORMAT.md — not re-enumerated here. This refines, and does not replace, the documentation gate's per-block behaviour above.

## Before declaring done — top-priority re-pass

When you reach the moment of thinking "I have no more questions" — do not enter the closing gate yet. Run this re-pass first.

**What to generate.** Up to three highest-priority questions you would ask next if you could only ask three more. Rank candidates by how strongly the answer would lock in something hard to reverse, be surprising without context, or settle a real trade-off — the more architectural the candidate (the closer it sits to those three ADR criteria), the higher it ranks. This is a relative ordering, not a per-candidate checklist: you are using these dimensions as the ranking axis, not ticking each candidate against three boxes.

For each candidate, write three things:
- The question itself.
- Your recommended answer, with its basis-level labelled (which tier it would rest on, or that it is only a low-confidence guess) so the user can see which candidates are grounded versus guesses. You need not do the full grounding work (e.g. a web search) just to list a candidate — that happens if and when you actually ask it — but never hide that a candidate's answer is only a guess.
- A one-line justification of why this candidate's answer **cannot be derived from the answers to the other two listed candidates**. If you cannot write this justification, drop the candidate — it is a duplicate of one already listed, no matter how it surfaced in your head.

**Rules.**
- List at most three. If you can think of more than three real candidates, state out loud "I can think of N more candidates beyond these three" and continue with only the top three this round — do not raise the cap.
- If you cannot think of three, list only what you can — do not pad with filler to reach three.
- Listing a candidate is a commitment: you cannot retract by saying "actually never mind". If you listed it as top priority, it must be asked.

**Show the user, in one block — the 🎯 block (template in OUTPUT-FORMAT.md).**
- The 0–3 candidates with their justifications and your recommended answers (each answer carrying its basis level), laid out per the template.
- The template's closing line tells the user they can override the priorities, add a candidate you missed, or say "enough, move on" to skip to closing — and that silence means "go ahead, ask them".

**Outcomes.**
1. **Zero candidates** → proceed to the closing gate.
2. **One to three candidates** → ask them one by one (respecting the existing one-question-at-a-time rule). After the last is ratified, run this re-pass again — not the closing gate. Each round may resolve some pending items but also surface new sub-branches from the answers.
3. **User says "enough, move on"** → proceed to the closing gate immediately, regardless of how many candidates were listed. The user's call is the deciding signal; the closing gate then handles any unresolved pending items the normal way.

**The user is opt-in, not on hook.** Silence from the user on the candidate block means "go ahead, ask them" — the user is not required to explicitly approve every round. Only an explicit override (priority change, addition, or "enough, move on") changes the default flow.

**Multi-round behaviour, and the handoff this re-pass does not catch.**
- This re-pass does not converge on its own. Each round resolves up to three pending items but answers may open new sub-branches, triggering another round. Convergence comes from the user calling "enough, move on", not from candidates exhausting themselves. This is by design: the cost of one more round of questions (the user can say "enough") is far smaller than the cost of stopping too early (a missed question vanishes silently into AFK execution).
- **What this re-pass catches (agent self-disclosure can expose it).** The "I am thinking of more but talked myself out of it" failure — you can think of the candidate, you just rationalised it away. When forced to list top three, you can produce it. This is the failure mode this re-pass exists for.
- **What this re-pass cannot catch (agent self-disclosure cannot expose it).** Two failures share this property despite different origins: (a) blind spots — candidates you genuinely cannot think of, which by definition will not appear in your list; (b) padding — candidates listed insincerely just to pass the gate, where you know they are weak but will not admit it. Both fail in your self-report and cannot be caught from within. They route to a downstream independent reviewer with a different vantage. The user reading the candidate block is the first line of defence against padding (a padded candidate is visible to them, though catching it depends on their familiarity and attention); the downstream independent review is the second.

## Closing the grill — pending-items gate

After the top-priority re-pass concludes (outcome 1: zero candidates, or outcome 3: user said "enough, move on"), **you may not end the session yet**. Run this gate:

1. **Catch the last answer.** Run the documentation gate against the user's most recent ratified answer — the same gate you would have run before asking the next question. The closing gate is the only opportunity this answer has to be filed; if you skip this step it falls through.
2. List every architecture-level question that was asked but never ratified — items where the user discussed but did not give a clear "this is the answer" signal.
3. Present this list to the user as the 🏁 closing-checklist block (template in OUTPUT-FORMAT.md) — its first line carries the documentation-gate outcome of the last answer (step 1), followed by the unratified list. For each item, the user must either ratify a decision now (in which case the documentation gate runs immediately on that item), or explicitly say "leave this unresolved, I will decide later".
4. Only after every item has been either ratified or explicitly deferred may the session end.

You cannot bypass this gate by declaring the conversation done. The user did not ask any of these architecture-level questions — you did. The responsibility to confirm they have all been put to rest, one way or another, is yours.

</what-to-do>

<supporting-info>

## Questioning techniques

These are tools for executing the main task — surfacing what the user assumed but did not say. Use whichever helps reveal an implicit assumption in the moment. Do not run them as a checklist of their own.

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things." Fuzzy language is often where an implicit assumption hides — the user has one specific meaning in mind but uses a word that has several.

When you propose a canonical term, hold it to two standards:

1. **Domain-specific, not generic.** Avoid overloaded technical words that mean too many things across software in general — "dispatch", "handler", "processor", "manager", "service" — when used as a domain action or entity name. They lose all specificity inside this project's vocabulary. Prefer the word a domain expert would naturally say.

2. **Length serves clarity, not brevity.** A good compound name encodes structured domain information so the reader does not need to look elsewhere to understand it. For an entity, encode the entity plus any qualifying state or kind ("ShippedOrder" beats "Order" when shipped and unshipped behave differently). For an action, encode the entity plus the change plus any qualifying condition ("CancelShippedOrder" beats "cancel" when the domain has multiple cancellation flows).

   The test name `test_user_cannot_cancel_shipped_order` is the model. Decompose it: the actor (user), the action (cannot cancel), the entity (order), the state (shipped). Four pieces of domain information, all in the name itself — reading the name alone tells you what behaviour is being tested. Apply the same decomposition lens to any compound term you propose: what pieces of domain information should this name carry, and which become invisible if you shorten it? The point of this lens is not naming as an end in itself — it is that a bad name often hides multiple implicit assumptions (which flow does "cancel" refer to? which entity state?), and decomposing forces those assumptions into the open where you can ask about them.

If you cannot meet both standards, ask the user for their own terminology rather than offering a generic name. A bad proposal anchors the conversation toward bad naming and is worse than no proposal.

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts. Useful when the user has described a happy path and implicitly assumed certain edge cases do not matter — surface those edge cases and make the assumption explicit.

### Cross-reference with code

The code is your most reliable source of ground truth for **what the system actually does right now**. The user can misremember, CONTEXT.md can be stale, but the code is what is running. When user statements about system behaviour conflict with the code, the code wins as the record of what the system actually does — though "the code is what runs" doesn't mean "the code is what was decided"; sometimes the code is stale relative to a fresh decision (see the rename case below).

A separate authority applies for **shared vocabulary**, not system behaviour: when the user uses a term that conflicts with the ratified definition in CONTEXT.md, CONTEXT.md wins — the user may have used an unratified or outdated word. Don't silently translate; surface it: "You said `X`, but the ratified term in CONTEXT.md is `Y` — do you mean `Y`, or do we need to revisit this term?"

There are three trigger situations where you must cross-reference:

1. **The user states how something currently works.** Check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — is this a misremembered description, a new behaviour you want, or an existing bug?"

2. **A CONTEXT.md term is being renamed or redefined.** Check whether the codebase still uses the old name. If it does, the rename produces a downstream code-sync obligation — see the next paragraph.

3. **You are about to write a new term to CONTEXT.md that describes a concept already present in the codebase.** Check what the codebase already calls it. If the existing code uses a different name for the same concept, surface the divergence: "The code currently calls this `Foo` — are we renaming to `Bar`, or is this a different concept that just sounds similar?"

When you detect that a ratified rename in CONTEXT.md has corresponding occurrences in the existing codebase, surface this to the user explicitly. State it as a discrete codebase refactoring task that must be carried into the PRD: "This rename produces a refactoring task: rename `{old}` → `{new}` across the codebase (currently appears in {files or count}). This task should be tracked as a deliverable in the PRD." Do not start the code change yourself — grill is a planning phase, not an implementation phase. Confirm the user is aware the obligation will flow downstream.

When the cross-reference reveals the user's mental model differs from what the code actually does, the divergence is itself an implicit assumption being exposed — surface it for the user to resolve, don't quietly accept it and move on.

</supporting-info>
