---
name: emergent-spec-review
description: Dual-axis review of one frozen spec document — two context-isolated reviewers judge the same text in parallel: one holds the complete conversation and checks decision fidelity in both directions, one holds no conversation and checks whether an implementer could build and verify it. Each returns its own mechanically validated blocker findings without touching the reviewed file. Use when a spec needs review before implementers receive it, when a spec-production pipeline dispatches a review round, or when the user asks to review a spec document from any source.
---

emergent-spec-review reviews exactly one frozen Candidate per invocation, along two independent axes at once.

- The **conversation decisions reviewer** holds the complete conversation evidence the caller delivered and checks the Candidate against it in both directions: did every decision the user ratified land, and does every commitment the Candidate binds trace back to an authority allowed to create it. `CONVERSATION-DECISIONS-PROMPT.md` is its axis template; after shared-fragment expansion, the written runtime prompt is its single reviewer-facing authority.
- The **implementation ready reviewer** holds no conversation at all and judges one question: can an implementer build and verify the Candidate working from it alone. `IMPLEMENTATION-READY-PROMPT.md` is its axis template; after shared-fragment expansion, the written runtime prompt is its single reviewer-facing authority.

Each reviewer's axis-specific checks, the material it may never demand, and its finding contract live in its own prompt template. Rules shared by both axes have one authoring source in `SHARED-REVIEW-PROMPT-FRAGMENTS.md`; assembly expands them into both complete runtime prompts. This file carries what a caller hands over and gets back. Both report blockers only — a problem with no concrete implementation, acceptance, or decision-fidelity failure behind it has nowhere to sit, and neither reviewer writes the repair.

**Report only.** emergent-spec-review does not modify the Candidate, declared inputs, or codebase; it writes only per-run review artifacts inside isolated run directories, and it never reviews on either reviewer's behalf. Merging the two reports, reranking them, adjudicating between them, repairing anything they found, and carrying open questions to a human all belong to the caller.

## Inputs

Both axes:

- **Candidate path** — the one frozen document under review, the same file for each axis. Its content derives the Candidate identity a reviewer carries into its report, so no report survives an edit to the text it reviewed.
- **Codebase** — live, read-only verification context for both reviewers. It is not copied into a run directory, snapshotted, or included in the assembled input digest.

Conversation decisions axis:

- **Conversation artifact** — the caller-prepared JSONL file holding this round's complete conversation evidence: one record object per line, already selected and already cut to the endpoint the caller intends for this round. emergent-spec-review delivers the artifact whole, every record in the caller's order, and does not require or verify a producer name, an extraction manifest, a schema version, a fixed category list, a selection profile, or any record-type set — it never re-cuts the conversation or hunts for its endpoint, and whether the evidence is complete, well-chosen, or cut correctly is the caller's responsibility alone, which emergent-spec-review cannot know and does not claim to judge. What it does check is deliverability: a primary artifact that is missing, unreadable, or not valid JSONL record objects fails the axis before dispatch. A prose summary, a settled-decision checklist, or any other account of the conversation is not a conversation artifact and fails the same way. Referenced images are best-effort evidence: an `images[].path` naming a safe normalized relative path with readable bytes is delivered beneath the artifact at that same relative path and bound by the round's input identity, while a missing, unreadable, unsafe, or otherwise undeliverable image is skipped with a note — never by itself a failed axis, a `tool_failed` close, or a read outside the artifact's directory.
- **Declared authorities** — the related ADRs, `CONTEXT.md` files, and external references the Candidate formally declares.

Implementation ready axis:

- **Declared documents** — the related ADRs, `CONTEXT.md` files, and external references the Candidate declares an implementer may rely on. They bound what the reviewer treats as available: what the Candidate needs beyond them and the codebase is a gap an implementer would hit.

The conversation, any account of it, the author's intent, and every earlier round's findings and repairs stay out of this dispatch; the assembler takes no conversation input, refuses a run directory that already holds one, and the report envelope has no field one could be recorded in. That absence is the instrument: what this reviewer cannot determine from the Candidate, an implementer cannot determine either.

## Workflow

1. **Create one run directory per axis, new for this invocation** under the OS tmp area (or the session scratchpad). Prompts, input snapshots and their manifest, delivered conversations, reports, and reviewer scratch notes are run evidence: never write them into bounded-context folders, specs, ADRs, or any production docs. A reviewer's run directory is the one place it may write and therefore reads, so reusing one carries an earlier review's Candidate text, conversation, findings, or notes into reviewers dispatched to judge the current Candidate alone; the assembler refuses any non-empty run directory, and refuses a delivered conversation on the implementation ready axis whoever left it there.

2. **Assemble both prompts** — one command per axis, each naming the same Candidate path:

   ```
   python3 <this skill>/scripts/prompt_assembly.py conversation_decisions \
     --candidate <candidate path> --run-dir <conversation decisions run dir> \
     --conversation <caller-prepared conversation artifact> \
     [--authority <path> ...]
   ```

   ```
   python3 <this skill>/scripts/prompt_assembly.py implementation_ready \
     --candidate <candidate path> --run-dir <implementation ready run dir> \
     [--allowed-doc <path> ...]
   ```

   Each command expands the shared fragments into its axis template, fills the round values, writes the complete prompt file, and prints run metadata JSON (`reviewer_role`, `prompt_path`, `report_path`, `candidate_path`, `candidate_snapshot_path`, `candidate_digest`, `input_digest`, `document_snapshots`, `input_manifest_path`, and the inputs that axis was given); the conversation decisions command also copies the caller's conversation artifact into its run directory whole, together with every referenced image it can deliver safely; an undeliverable image is skipped with a stderr note and left out of the round instead of failing assembly. `input_digest` binds the contents assembled for that axis: Candidate plus delivered conversation and its delivered images plus declared authorities on the conversation axis, and Candidate plus declared documents on the implementation axis. The assembler snapshots the Candidate and every local file, local directory, or fetched HTTP(S) response into the isolated run directory, records the source-to-snapshot mapping in `review-inputs.json`, and points the prompt only at those snapshots. The reviewer therefore reads the same bytes the digest names even if a source changes while the review runs. Validation re-hashes both the snapshots and the current source references; a changed snapshot, a source that drifted, or an external URL that no longer returns the snapshotted bytes invalidates the round. An unreadable declared input fails assembly rather than producing an identity that omits it.

   The two `candidate_digest` values are derived from the Candidate's own text: equal digests are the proof both axes reviewed one version, and unequal ones mean the Candidate moved between the two commands, so the invocation restarts from a freshly frozen Candidate.

   The written prompt file is the **sole authority** for the prompt at dispatch time — never transcribe, summarize, or amend its content in the dispatch.

3. **Dispatch both reviewers in parallel** per the Dispatch section below, delivering each its own prompt file, and wait for both to finish before doing anything with either result. Holding both until they land is what keeps the axes independent: neither reviewer's output can reach the other, and the text under review stands still for the whole round.

4. **Extract each report path mechanically.** A reviewer's reply carries one fixed-format line, `REVIEW_REPORT_PATH: <path>`. Save each reply to its own file and let the validator resolve it (`--from-reply`); any other prose in the reply is ignored and is not a contract violation.

5. **Validate both rounds mechanically** — one command per axis:

   ```
   python3 <this skill>/scripts/report_validation.py conversation_decisions \
     --from-reply <saved conversation decisions reply> \
     --expected-report <assembler report_path> --candidate <assembler candidate_path> \
     --input-digest <assembler input_digest> \
     --conversation-artifact <assembler conversation_artifact_path> \
     [--authority <each assembler authority_docs value> ...]
   ```

   ```
   python3 <this skill>/scripts/report_validation.py implementation_ready \
     --from-reply <saved implementation ready reply> \
     --expected-report <assembler report_path> --candidate <assembler candidate_path> \
     --input-digest <assembler input_digest> \
     [--allowed-doc <each assembler allowed_docs value> ...]
   ```

   Pass the assembler's printed values back exactly; never reconstruct or omit them. Each validator requires the reply path to equal the preassigned report path, loads the fixed `review-inputs.json` beside that report, re-derives the Candidate and assembled input identities from both the review snapshots and their current source references, and requires the report to echo that round's Candidate path, input digest, and axis inputs. If any Candidate snapshot, delivered conversation, referenced image, declared document snapshot, local source, or fetched external response changed after assembly, validation fails instead of accepting a report about different bytes. It also rejects a report that names the other role, carries another version's identity, closes unfinished, or breaks the envelope for its axis below. `valid <report path>` accepts that axis; any `invalid: …` output — including `authority_load_failure`, a reviewer's fixed one-line reply when it could not load `emergent-design` — makes that axis invalid and discards its report whole.

   The invocation passes only when both axes returned a valid report; a missing or invalid one is never read as zero findings on its axis. Whether a failed invocation is re-dispatched is the caller's policy.

6. **Return both reports, side by side and role-labelled**: each axis's blocker findings in the reviewer's own order, its per-check conclusions, and its report path. The two sets stay separate — no merged list, no cross-axis ranking, no verdict about which axis matters more.

## Conversation decisions report schema

A closed envelope, and any key outside it is a violation:

```json
{
  "reviewer_role": "conversation_decisions",
  "candidate_path": "<absolute path of the reviewed Candidate>",
  "candidate_digest": "<echoed verbatim from the prompt>",
  "input_digest": "<assembled review-input identity echoed from the prompt>",
  "conversation_artifact_path": "<the delivered conversation>",
  "authority_docs": ["<the declared authority paths>"],
  "findings": [
    {
      "check": "ratified_decision_landing|binding_commitment_authority",
      "candidate_location": "<where in the Candidate, precise enough to relocate>",
      "issue": "<what is wrong>",
      "failure_scenario": "<how an implementer deviates or is bound wrongly>",
      "evidence": ["<the sources actually checked>"]
    }
  ],
  "check_conclusions": {
    "<each check with zero findings; optionally a check with a paused dependent judgment>": "<one non-empty sentence: what was examined, or what judgment paused and why>"
  },
  "reviewer_close_status": "completed|tool_failed"
}
```

Structural validity enforced by the validator: the role, Candidate digest, and assembled input digest match the dispatched round; the close status is `completed`, so an unfinished review can never pass; every finding names one of the two checks and carries a non-empty `candidate_location`, `issue`, `failure_scenario`, and at least one evidence entry; every check with zero findings carries a conclusion sentence, so silence is never a pass, while a check with findings may also carry one only to record a paused dependent judgment. Every conclusion is a non-empty string, never a nested carrier for grading or repair advice. Grading and repair advice have no legal slot: a finding carrying a graded field, a proposed wording, or any other key outside the shape above is rejected, so no consumer can grow a branch that reads one.

## Implementation ready report schema

The same closed envelope, widened by this reviewer's own inputs and by those alone:

```json
{
  "reviewer_role": "implementation_ready",
  "candidate_path": "<absolute path of the reviewed Candidate>",
  "candidate_digest": "<echoed verbatim from the prompt>",
  "input_digest": "<assembled review-input identity echoed from the prompt>",
  "allowed_docs": ["<the declared document paths>"],
  "findings": [
    {
      "check": "observable_behavior|caller_contract|acceptance_endpoint|testing_seam|unrelaxable_constraint",
      "candidate_location": "<where in the Candidate, precise enough to relocate>",
      "issue": "<what is wrong>",
      "failure_scenario": "<how an implementer stalls, guesses, or builds the wrong thing>",
      "evidence": ["<the sources actually checked>"]
    }
  ],
  "check_conclusions": {
    "<each check with zero findings; optionally a check with a paused dependent judgment>": "<one non-empty sentence: what was examined, or what judgment paused and why>"
  },
  "reviewer_close_status": "completed|tool_failed"
}
```

The five check ids are the determinations an implementer must be able to reach, and a finding has nowhere to sit unless it names one of them — which is what keeps unbound internal design out of the report (single authority: `scripts/report_validation.py` `IMPLEMENTATION_READY_CHECKS`).

Structural validity is enforced exactly as on the other axis, and against that axis's inputs too: `conversation_artifact_path`, `authority_docs`, or any other key outside the shape above is rejected, so this reviewer's isolation survives in the report even if something reached it at dispatch.

## Dispatch

Reviewer dispatch, on either axis, reuses the reviewer-dispatch rule this project already field-tested for ADR quality review. The rule's full statement — channel assignment rationale, tier evidence, and the temporary patch's exit conditions — lives in `../emergent-adr/QUALITY-REVIEW-PROMPTS.md` (section "ADR quality-review dispatch parameters"); emergent-spec-review maintains no dispatch policy of its own, and when that shared rule changes, this section follows it. The operative points:

- **Both at once, both joined:** issue both dispatches before awaiting either result, then join both before continuing — awaiting one reviewer before the other is even dispatched turns the round serial and costs the whole point of two axes. Each dispatch is foreground-synchronous; never background a reviewer.
- **Prompt-only delivery:** a reviewer receives its assembled prompt file and nothing else — no conversation context, author intent, or repair history beyond what that prompt file itself embeds or points at. A runtime that can pass file content through a non-LLM channel (e.g. shell) brings it in directly; otherwise send only a one-line fixed bootstrap instructing the reviewer to read that file and follow it.
- **Claude Code** — dispatch through the CLI by piping each assembled prompt file in, starting both before waiting on either:

  ```
  claude -p --model opus --effort high \
    --tools Read Write Bash \
    --permission-mode auto --allowedTools "Read Write Bash" \
    < <conversation decisions prompt> > <conversation decisions reply> &
  claude -p --model opus --effort high \
    --tools Read Write Bash \
    --permission-mode auto --allowedTools "Read Write Bash" \
    < <implementation ready prompt> > <implementation ready reply> &
  wait
  ```

  The single `wait` is the join, and the shell call itself blocks until both reviewers are done — so the round runs both axes concurrently while still being foreground; never `--bg`. This is the shared rule's temporary patch: in-harness sub-agent dispatch cannot set per-invocation reasoning effort, so a plain sub-agent silently inherits the main session's effort tier. The CLI carries only model and effort — never review rules or prompt content. The default text output suffices; each saved stdout is the reply file its validator resolves.
- **Codex / Cursor / other runtimes** — dispatch through the runtime's **native sub-agent facility**, never through any CLI, issuing both sub-agent calls in one batch so they run concurrently. Start each reviewer in a fresh sub-agent context with no inherited parent turns and deliver only the fixed bootstrap from the prompt-only rule above; on Codex, pass `fork_turns: "none"` so the parent conversation stays out and the model/effort override is valid. Model and effort follow the shared rule's per-runtime assignments (`gpt-5.6-sol` + `xhigh` on Codex; `cursor-grok-4.6-xhigh` on Cursor; elsewhere the strongest instruction-following model available).
- **Timeout:** budget from expected full-review duration. A reviewer failure that still closes yields a structured report with `reviewer_close_status: tool_failed`, which the validator rejects; a reviewer that produces no report at all fails the same way. Either outcome goes to the caller's policy and is never silently passed.

## Boundaries

- Reviews exactly one frozen Candidate per invocation, and never edits it or any other repository file.
- Owns dispatch, input isolation, mechanical report validation, and per-axis return — and nothing beyond them. Finding disposition, repair, convergence, and human questions are the caller's.
- Never merges, reranks, or adjudicates between the two axes: a pass on one axis says nothing about the other.

## Scripts

`scripts/prompt_assembly.py` (per-run prompt instantiation and conversation delivery) and `scripts/report_validation.py` (report-path extraction and report validation) are the mechanical seam. Their tests run from `scripts/`: `python3 -m pytest`.
