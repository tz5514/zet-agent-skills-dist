---
name: review-spec
description: Blind seven-gate review of one spec document — a context-free sub-agent checks self-sufficiency, contradictions, reality conflicts, disguised non-decisions, undecidable acceptance, boundary gaps, and unavailable dependencies, then reports structured graded findings without touching the reviewed file. Use when a spec needs a pre-publication blind review, when a spec-production pipeline dispatches a review round, or when the user asks to review a spec document from any source.
---

review-spec reviews exactly one spec document per invocation by dispatching a **blind sub-agent** — a reviewer holding no conversation context, no author intent, and no production history — against the seven-gate set defined in `GATE-PROMPT.md`. It is independently callable on a spec from any source (pipeline-produced, hand-written, pre-existing).

**Report only.** review-spec never modifies the reviewed spec or any other file; its sole product is a structured findings report. Fixing findings, deciding whether to run another round, and every other loop control belong to the caller.

## Interface

Inputs the caller supplies:

- **Spec path** — the one document under review.
- **Allowed document set** — the caller-identified list of documents (files or directories) an implementer may rely on besides the spec and the codebase; typically the spec's related ADRs and the bounded context's `CONTEXT.md`. This set defines the self-sufficiency boundary: what the spec needs beyond it is a finding. The repository codebase is always additionally readable to the reviewer, for verification only.
- **Review mode** — `initial`: the first blind review of a spec text, taking no prior review information. `post-fix`: the re-review after a repair round; it additionally requires the prior-round disposition below. Both modes review the full text against the complete gate set — the mode changes only attention allocation and bookkeeping: a post-fix round must produce a prior-round fix checklist (items fixed and holding in the current text are marked fixed and not re-reported) and run a cross-reference priority scan (count words; gate–obligation alignment; positive/negative evidence-sentence co-directionality).
- **Prior-round disposition** (post-fix only) — a caller-written JSON file listing every finding of the prior round with the repair's claimed disposition:

  ```json
  {
    "items": [
      {
        "gate": "<canonical gate id>",
        "severity": "blocker|non_blocker",
        "evidence_location": "<from the prior report>",
        "issue": "<from the prior report>",
        "disposition": "fixed|not_fixed",
        "note": "<what the repair changed, or why the item was left>"
      }
    ]
  }
  ```

  The assembler validates this input, assigns each item a stable positional id (`P1`…`Pn`; caller-supplied ids and extra fields are dropped), writes the normalized copy into the run directory as `prior-round-disposition.json`, and embeds it in the prompt. The reviewer treats each disposition as a claim to verify against the current text, never as a verdict to copy.

Output: the path and parsed content of a mechanically validated report (schema below). Blockers drive whatever repair process the caller runs; non-blockers are advisory.

## Workflow

1. **Create a run directory** under the OS tmp area (or the session scratchpad). Reports and prompts are run evidence: never write them into bounded-context folders, specs, ADRs, or any production docs.
2. **Assemble the prompt** — one command:

   ```
   python3 <this skill>/scripts/prompt_assembly.py \
     --spec <spec path> --run-dir <run dir> \
     --allowed-doc <path> [--allowed-doc <path> ...] \
     --mode <initial|post-fix> [--prior-round <disposition json>]
   ```

   `--prior-round` is required with `--mode post-fix` and rejected with `--mode initial`. The command instantiates `GATE-PROMPT.md` for the given mode (post-fix prompts carry the checklist and priority-scan obligations plus the embedded normalized disposition; initial prompts carry none of them), prepends a per-run random integrity marker, writes the prompt file into the run directory, and prints run metadata JSON (`prompt_path`, `report_path`, `integrity_marker`, `review_mode`, `spec_path`, plus `prior_disposition_path` in post-fix mode). Keep that metadata: validation needs the marker. The written prompt file is the **sole authority** for the prompt at dispatch time — never transcribe, summarize, or amend its content in the dispatch.
3. **Dispatch the blind reviewer** per the Dispatch section below, delivering the prompt file.
4. **Extract the report path mechanically.** The reviewer's reply carries one fixed-format line, `REVIEW_REPORT_PATH: <path>`. Save the reply/stdout to a file and let the validator resolve it (`--from-reply`); any other prose in the reply is ignored and is not a contract violation.
5. **Validate the round mechanically** — one command:

   ```
   python3 <this skill>/scripts/report_validation.py \
     --from-reply <saved reply file> \
     --expected-marker <integrity_marker> --expected-mode <mode> \
     [--prior-disposition <run dir>/prior-round-disposition.json]
   ```

   `--prior-disposition` is passed in post-fix mode, pointing at the normalized disposition the assembler wrote; it makes the validator check that the report's checklist covers exactly the dispatched items. `valid <report path>` accepts the round. Any `invalid: …` output — no extractable path line, unreadable report, marker mismatch, mode mismatch, or illegal structure — makes the round **invalid**: discard it entirely; never eyeball-accept a report the validator rejected. Whether an invalid round is re-dispatched is the caller's policy.
6. **Return the report to the caller**: blockers, non-blockers, and the per-gate verification conclusions, plus the report path.

## Report schema

The reviewer writes the report JSON itself and self-checks it with the same validator (without the marker, which only the dispatcher can vouch for):

```json
{
  "spec_path": "<absolute path of the reviewed spec>",
  "review_mode": "initial|post-fix",
  "integrity_marker": "<echoed verbatim from the prompt file head>",
  "allowed_docs": ["<the allowed document paths>"],
  "findings": [
    {
      "gate": "<canonical gate id>",
      "severity": "blocker|non_blocker",
      "evidence_location": "<file plus line/section, precise enough to relocate>",
      "issue": "<what is wrong>",
      "failure_scenario": "<required for blockers: where and how an implementer fails or deviates>",
      "suggested_fix": "<how to fix it>"
    }
  ],
  "gate_conclusions": {
    "<each gate id with zero findings>": "<one-sentence verification conclusion: what was checked, why judged clean>"
  },
  "prior_fix_checklist": [
    {
      "id": "<prior-round item id (P1…Pn)>",
      "status": "fixed|not_fixed",
      "verification": "<one sentence: where in the current text it was checked, why the status holds>"
    }
  ],
  "reviewer_close_status": "completed|tool_failed|scope_limited"
}
```

`prior_fix_checklist` exists only in post-fix reports (it is illegal in initial ones): one entry per prior-round item, `fixed` meaning fixed **and holding in the current text** — such items are not re-reported in `findings`; anything else is `not_fixed`, and a `not_fixed` problem that still impairs implementation reappears as a current finding.

The seven canonical gate ids, in formal order (single authority: `scripts/report_validation.py` `GATE_IDS`): `self_sufficiency`, `internal_contradiction`, `reality_conflict`, `undecided_disguised_as_decided`, `acceptance_undecidable`, `boundary_gap`, `dependency_unavailable`. Their operational definitions, the blocker/non-blocker grading criterion, and the failure-scenario obligation live in `GATE-PROMPT.md` — the reviewer-facing single authority; this file does not restate them.

Structural validity enforced by the validator: every finding names a canonical gate and a legal severity and carries non-empty `evidence_location`, `issue`, and `suggested_fix`; every blocker carries a non-empty `failure_scenario`; every gate with zero findings carries a non-empty conclusion sentence (so all seven gates are covered — silence is never a pass); marker and mode match the dispatched round. In post-fix mode additionally: `prior_fix_checklist` is present, every entry carries a unique `id`, a legal `status`, and a non-empty `verification`, and — when the dispatcher passes `--prior-disposition` — the checklist ids cover exactly the dispatched items.

## Dispatch

Blind reviewer dispatch reuses the reviewer-dispatch rule this project already field-tested for ADR quality review. The rule's full statement — channel assignment rationale, tier evidence, and the temporary patch's exit conditions — lives in `../adr/QUALITY-REVIEW-PROMPTS.md` (section "ADR quality-review dispatch parameters"); review-spec maintains no dispatch policy of its own, and when that shared rule changes, this section follows it. The operative points:

- **Foreground blocking:** dispatch foreground-synchronous and join before continuing. Never background the reviewer.
- **Blind delivery:** the reviewer receives the assembled prompt file and nothing else — no conversation context, no author intent, no repair history beyond the normalized prior-round disposition the prompt itself embeds in post-fix mode. A runtime that can pass file content through a non-LLM channel (e.g. shell) brings it in directly; otherwise send only a one-line fixed bootstrap instructing the reviewer to read that file and follow it.
- **Claude Code** — dispatch through the CLI by piping the assembled prompt file in:

  ```
  claude -p --model opus --effort high \
    --tools Read Write Bash \
    --permission-mode auto --allowedTools "Read Write Bash" \
    < <prompt file> > <saved reply file>
  ```

  This is the shared rule's temporary patch: in-harness sub-agent dispatch cannot set per-invocation reasoning effort, so a plain sub-agent silently inherits the main session's effort tier. The CLI carries only model and effort — never review rules or prompt content. Foreground-synchronous; never `--bg`. The default text output suffices; the saved stdout is the reply file the validator resolves.
- **Codex / Cursor / other runtimes** — dispatch through the runtime's **native sub-agent facility**, never through any CLI. Model and effort follow the shared rule's per-runtime assignments (`gpt-5.6-sol` + `xhigh` on Codex; `cursor-grok-4.5-high` + `high` on Cursor; elsewhere the strongest instruction-following model available).
- **Timeout:** budget from expected full-review duration. A reviewer failure that still closes yields a structured report with `reviewer_close_status: tool_failed`; a round that produces no validating report at all is an invalid round. Either way the round goes to the caller's round policy and is never silently passed.

## Boundaries

- Reviews exactly one spec per invocation; never edits the reviewed spec or any repository file.
- No preference-based redesign findings — "a different design would be better" is not a finding.
- The spec's declared authority split between documents is settled division of labor; the reviewer must not report the declared split itself as a contradiction.
- Never feeds the reviewer session transcripts, author intent, or repair history beyond the embedded prior-round disposition of a post-fix round.
- Owns no repair loop: grading exists so the caller's loop can be blocker-driven, but rounds, convergence, and caps are the caller's.

## Scripts

`scripts/prompt_assembly.py` (per-run prompt instantiation) and `scripts/report_validation.py` (report-path extraction and report validation) are the mechanical seam. Their tests run from `scripts/`: `python3 -m pytest`.
