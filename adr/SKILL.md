---
name: adr
description: The single entry point for all ADR (Architecture Decision Record) operations in this project — producing draft ADRs, writing ADR content, quality review, supersession scanning, and promoting a draft into active. Use when a consumer skill or any agent needs ADR lifecycle work. Invoke via the Skill tool; do not embed ADR mechanism specs in the consumer.
---

This skill is the authoritative home and unified entry point for every ADR operation in the project. Consumer skills **invoke `/adr` via the Skill tool** rather than embedding ADR mechanism specs of their own.

This SKILL.md is an **operation dispatcher**, not a spec. Each operation below points at the authoritative spec file or script and does **not** restate its rules — so the spec lives in exactly one place and maintenance touches only that place. When you run an operation, read the referenced spec in full and follow it; the bullets here only route you.

Authoritative spec files in this skill:

- `ADR-FORMAT.md` — ADR file format, `write` contract, three-section body, atomic-decision format, the `description` field, writing conventions, ADR ids, Source Decision Extract rules, and writer self-check evidence handling.
- `QUALITY-REVIEW-PROMPTS.md` — ADR quality-review report schema, dispatch parameters, the three named review modes, and how the per-mode reviewer prompt is mechanically assembled.
- `QUALITY-REVIEW-PROMPT-BLOCKS.md` — the single-authority fragments (shared framework, per-gate, and mode-specific rule blocks) the reviewer prompt is assembled from.
- `SCAN-SUPERSESSION-PROMPT.md` — the field-tested verbatim prompt template and dispatch parameters for supersession scanner sub-agents.
- `scripts/` — the mechanical helpers: `context_derivation.py`, `adr_subfolder.py`, `description_index.py`, `atomicity_lint.py`, `live_atomic_decision_corpus.py`, `scan_candidates.py`, `scan_supersession_input.py`, `scan_supersession_packet.py`, `scan_supersession_ledger.py`, `scan_supersession_result.py`, `scan_supersession_delivery.py`, `scan_rewrite_contract.py`, `produce_for_hitl_contract.py`, `quality_review_contract.py`, `review_prompt_assembly.py`, `review_verdict_report.py`, `revise_contract.py`, `revise_and_promote_contract.py`, `supersession_converter.py`, `status_calculator.py`, `supersession_mark_back.py`, `conflict_disposition.py`.

## Invocation contract

`/adr` is a **single skill** — its operations are not split into one sub-skill each. You select which operation runs with an **operation keyword: the first token of the args you pass when invoking `/adr`**.

The keyword is **mandatory and has no semantic fallback**: if the first token is missing or is not one of the nine keywords below, `/adr` **lists the valid keywords and stops** — it never guesses the intended operation from context. The nine valid keywords are:

- `produce`
- `produce-for-HITL`
- `write`
- `revise`
- `quality-review`
- `scan-supersession`
- `promote-draft-to-active`
- `revise-and-promote-draft-to-active`
- `extract-active-adr-desc`

**Every operation takes a named input schema and returns structured data, never consumer-formatted output.** The consumer renders the returned data with its own output templates and carries any user response. Each operation's named input schema and output contract is given with that operation below and is the format the caller fills in — the caller does not invent its own.

**`bounded_context_path` is required only when the input does not already carry a target ADR path that can derive it.** `scan-supersession` and `promote-draft-to-active` derive the bounded context from `draft_adr_path`. `write`, `quality-review`, and `produce` accept `target_adr_path` when modifying or reviewing an existing ADR; they accept or require `bounded_context_path` when creating a new draft or when no target path is available.

**Boundary the return contract does not move:** the structured-return rule governs only how data enters and leaves `/adr`. It deliberately does **not** relocate the supersession lifecycle. A consumer follows this skill's lifecycle operations; it does not re-implement or unbundle those steps.

## Operations

### `produce` — end-to-end draft ADR delivery

Create or modify a draft ADR through the full delivery flow. `produce` controls process and machine handoff: it calls `write` to create or modify the draft, then delegates the entire post-write delivery-completion flow to `revise`. It does **not** restate the draft ADR acceptance review loop, scan workflow, or scan-rewrite loop — those live in `revise`.

Flow:

1. Call `write`.
2. If `write` returns `no_adr`, stop immediately with `final_status: no_adr`. Do not create a draft, Source Decision Extract, reviewer report, or scan.
3. If `write` returns `needs_context_ruling`, stop immediately with `final_status: needs_context_ruling`. Do not invent vocabulary, write a draft, dispatch reviewer, or scan.
4. If `write` returns a written draft, call `revise` with `quality_review_mode: full_quality_review`, passing the written draft's path. `revise` owns the draft ADR acceptance check, reviewer finding repair, `scan-supersession`, the scan-rewrite loop, scan-result invalidation reruns, and the detailed report; `produce` does not duplicate any of them.

Runtime dispatch defaults for sub-agent / cli:

- Writing should run on a high-reasoning, instruction-following model because first-draft quality is the main cost driver for the downstream review loop.
- **Codex:** use `gpt-5.5` with `xhigh` reasoning effort for `write`. Do not enable fast mode. Do not pass a `service_tier` override; record it as omitted/default in run evidence.
- **Claude Code:** use Opus with high effort for `write`. This is the conservative production default until Claude cross-model smoke material can run again. The reviewer-disposition-repair and scan-request-rewrite dispatch defaults moved to `revise`, which owns those steps.

Input:

- Create mode — `bounded_context_path` and source material.
- Modify mode — existing draft `target_adr_path`; verify it is a draft ADR before modification.

Output — thin wrapper report:

- Direct output includes `draft_adr_path`, `structured_report_path`, `final_status`, and `needs_user_ruling`.
- `produce` writes a thin wrapper JSON report to an OS tmp structured run directory every time, including early terminal states. It records this layer's operation status, the `revise` sub-operation's report path, whether it advanced to the next step, and the final handoff status; it does **not** copy `revise`'s detailed review, scan, or report fields.
- **`final_status` value set (the authority for both `produce` and `revise`):** `final_status` supports `passed`, `no_adr`, `needs_context_ruling`, `blocked_after_review_limit`, `needs_user_ruling`, and `failed`. The `needs_user_ruling` boolean indicates caller handoff to the user and is not itself a failure state. When a supersession scan is carried pending, `final_status` is `needs_user_ruling`. `revise` takes these definitions by reference and does not restate the value set.

Early terminal states (produced by the `write` step and carried in `produce`'s thin wrapper report, not by `revise`):

- `no_adr` returns/report `final_status: no_adr`, `draft_adr_path: null`, `needs_user_ruling: false`, `source_decision_extract_status: not_created`, skipped reviewer and scan steps, and the no-ADR reason.
- `needs_context_ruling` returns/report `final_status: needs_context_ruling`, `draft_adr_path: null`, `needs_user_ruling: true`, missing concept/term, suggested ruling input, and skipped reviewer and scan steps.

### `produce-for-HITL` — lightweight human-in-the-loop draft flow

Create or modify a draft ADR during a human-in-the-loop interview with only the checks that cannot wait for the user. It runs just two stages — write the draft, then the CONTEXT.md glossary approval preflight — and stops. It deliberately does **not** run full ADR quality review, the draft ADR acceptance review/fix loop, `scan-supersession`, or any scan rewrite loop, and it never produces a complete `produce` acceptance pass. Its orchestration, `final_status` semantics, and JSON report contract live in `scripts/produce_for_hitl_contract.py`; this section only routes to that helper.

Flow:

1. Call `write` in create or modify mode.
2. If `write` returns `no_adr` or `needs_context_ruling`, stop immediately with no review and no scan.
3. If `write` returns `written`, call `quality-review` on the written draft with `review_mode: context_glossary_approval_preflight` and persisted child-report output. This is the only `quality-review` mode this operation ever uses; it never calls full quality-review mode.
4. If preflight reports a CONTEXT.md glossary approval need, stop and hand a user ruling back to the caller.
5. If preflight cannot evaluate because of structural unreadability or tool failure, stop with a non-pass terminal status.
6. If preflight completes without a blocking finding, return `hitl_preflight_passed` — a success state for the lightweight flow only, never the full `produce` `passed` status.

Supersession scan trigger rule: outside `produce-for-HITL`, every newly created or modified draft ADR must still trigger `scan-supersession`; an agent may not decide on its own that a change is too small or unrelated and skip the scan. `produce-for-HITL` is the single human-in-the-loop exception to that rule — inside this operation the scan is intentionally skipped and recorded as `scan_status: skipped_for_hitl` in the structured report. This exception does not relax the scan trigger rule for any other case. `produce-for-HITL` never calls `scan-supersession`, never dispatches a scanner sub-agent, and never writes scan-derived `supersedes`.

Input:

- Create mode — `bounded_context_path` and source material.
- Modify mode — existing draft `target_adr_path` and source material. It rewrites the existing draft with `write`'s modify behavior instead of creating a new one, and reuses `write` modify validation that the target is an existing draft ADR. `bounded_context_path` is derived from the target path when available. The modify path reuses the create orchestration, report contract, and direct output envelope unchanged; only the writing stage differs.

Output:

- Direct output includes `draft_adr_path`, `structured_report_path`, `final_status`, and `needs_user_ruling` — the same machine-handoff envelope as `produce`.
- Every run persists a JSON report to an OS tmp structured run directory, including early terminal states. The report records which full-flow steps were skipped, marks the supersession scan bookkeeping as skipped for the human-in-the-loop flow once a written draft reaches the preflight path, keeps full ADR quality review flagged as not completed, and carries the preflight result summary, so no consumer mistakes the lightweight preflight for a complete draft ADR acceptance check.
- Skipped full-flow work is recorded only in the report. The draft ADR body and frontmatter carry no human-in-the-loop completion marker or lifecycle sub-state; draft mutability stays governed by the existing lifecycle rules.

### `write` — write ADR content

Create a new draft ADR or substantively modify an existing draft ADR. Follow **ADR-FORMAT.md** for section roles, atomic-decision rules, ADR eligibility, Source Decision Extract, writer self-check evidence, terminal states, and output fields. Run `scripts/atomicity_lint.py` over the draft as a cheap structural self-check; it flags suspects only and does not block.

- **Input** — `mode` (`create` | `modify`); `bounded_context_path` for create; `target_adr_path` for modifying an existing ADR; source material for the decision source.
- **Output** — `status` (`written` | `no_adr` | `needs_context_ruling`), ADR id when one exists, target path when one exists, whether it was created or modified, created/changed atomic decision ids, Source Decision Extract path when created, writer self-check evidence status, and any no-ADR or context-ruling details.

### `revise` — complete draft ADR delivery

Complete the delivery of an existing draft ADR: run the draft ADR acceptance check, dispatch every blocking finding to its disposition class and complete that disposition, run `scan-supersession` (as pre-acceptance evidence closure when a finding requires scan evidence, otherwise as the post-acceptance tail), run the scan-rewrite loop and scan-result invalidation reruns, and return a structured report. `revise` owns this flow (moved out of `produce`). It delegates writing rules to **ADR-FORMAT.md**, reviewer rules to **QUALITY-REVIEW-PROMPTS.md**, live active decision support data to `scripts/live_atomic_decision_corpus.py`, supersession detection to `scan-supersession`, and the scan-rewrite gate to `scripts/scan_rewrite_contract.py`; its acceptance-loop and scan-handoff orchestration contract lives in `scripts/revise_contract.py` — the blocking-finding disposition dispatch, scan freshness, the tail-scan evidence diff, and the scan-rewrite loop it drives with the orchestrating agent's injected accept judgement all live there, and it also carries the per-loop scan-rewrite bookkeeping the orchestrating agent supplies for externally orchestrated loops. It reuses those operations' existing input, prompt, and output definitions rather than restating them. `revise` never builds a new draft ADR.

Input:

- Required `draft_adr_path`. Its bounded context — and therefore the `active/` comparison set for scanning — is derived from this path. The live atomic decision corpus is rebuilt fresh each run; a previous run's report is never a reviewer input.
- Required `quality_review_mode`, one of `full_quality_review` or `frozen_glossary_quality_review` — **no default; if missing or unrecognised, `revise` aborts immediately without semantic inference.** These are revise-level concept names; `revise` maps `full_quality_review` to `quality-review`'s `quality_review` mode and `frozen_glossary_quality_review` to its `frozen_glossary_review` mode. The CONTEXT.md glossary approval preflight mode is never usable for `revise`.
- Optional `source_decision_extract_path` and `source_material`.
- If Source Decision Extract or other support data is missing, `revise` does not stop; it marks the report degraded and lets ADR quality review present the evaluable and non-evaluable ranges per the existing support-data rules.

Flow:

1. Draft ADR acceptance check: run `quality-review` in the resolved mode until either a round has no blocking findings or the shared round limit is exhausted. One `revise` execution has a single seven-round limit shared by **every** ADR quality-review call it makes — including the re-review after a scan-evidence closure, after a scan-rewrite loop, and after a tail-scan evidence change; there is no second review budget. When the limit is exhausted with blocking findings still open, stop and report `blocked_after_review_limit`.
2. Every review round uses the current target ADR, current Source Decision Extract, and current live atomic decision corpus. If the target or support data changes after a pass, rerun review or mark evidence degraded.
3. Blocking-finding disposition: every blocking finding a round reports is first mechanically dispatched to exactly one disposition class — the machine answer to "who resolves this finding, with what means" — and its disposition must complete before the next review round. The dispatch derives from the finding's `gate_id` and the review report's terminal result; the reviewer never assigns or sees disposition classes, and the quality-review report schema and reviewer prompt are unchanged. The dispatch table:
   - `live_active_atomic_decision_repetition_check` → `scan_evidence` (supersession-scan evidence closure);
   - `context_glossary_approval_need_check` under `full_quality_review` → `user_ruling`;
   - report terminal result `not_an_adr_candidate` → `terminal`, overriding every finding of that round;
   - every other blocking finding → `writer_repair`.
4. Immediate user hand-offs: any `user_ruling` finding ends the acceptance loop at once with a `needs_user_ruling` terminal carrying the ruling request, not counted as a repair round (the full-mode glossary approval semantics, unchanged). A `not_an_adr_candidate` terminal result ends the loop at once with a `needs_user_ruling` terminal carrying that judgement and its findings — no repair write, no scan, and no new `final_status` value: only the user can decide that draft's fate.
5. Writer repair: `writer_repair` findings are repaired through `write`'s modify mode on the same draft (`revise` does not build a new draft). A single repair write covers only that round's `writer_repair` findings; it must not hand-write `supersedes` and must not touch the atomic decisions a `scan_evidence` finding points at. At most one repair write runs between two review rounds — scan-rewrite writes are not repair writes and are not capped by this. Even a finding the main agent believes is a false positive still gets a recorded disposition; do not resend the same target/support-data combination unchanged and count it as a new round.
6. Frozen invariant: under `frozen_glossary_quality_review` the glossary is frozen — a repair `write` modify must not trigger `needs_context_ruling` (the frozen glossary forbids adding or changing terms; vocabulary problems are resolved only with an already-approved term or an ordinary-prose rewrite). If it happens anyway, that is a process error reported as a `failed` terminal; `revise` never invents vocabulary or escalates a ruling. Under `full_quality_review` the glossary is not frozen: when a repair `write` modify surfaces `needs_context_ruling`, `revise` hands off as a `needs_user_ruling` terminal carrying that ruling request — the same user-hand-off semantics as a glossary approval finding from review.
7. Semantic degradation from resolving a glossary gap by rewriting under the frozen glossary is recorded, together with the gap, in this run's final report.
8. Scan role duality — pre-acceptance evidence closure vs post-acceptance tail. When a round has a `scan_evidence` blocking finding and no non-invalidated completed scan result exists for the current `## Atomic Decisions`, run `scan-supersession` **before** acceptance: the scan is that finding's disposition, producing the durable `supersedes` evidence the repetition check requires. Within one round the repair write completes before this closure scan (a repair may change `## Atomic Decisions` and would invalidate a scan run first). A round with no `scan_evidence` finding never scans early — on the ordinary path `scan-supersession` still runs after acceptance as the post-acceptance tail. The structured scan workflow is preserved in both roles, and the detailed report records each scan's role.
9. Scan-result freshness: any change to `## Atomic Decisions` after a scan invalidates that scan result (content comparison, mechanical hash); a fresh scan is required before accepting the draft. A non-invalidated completed result is reused — neither the closure path nor the tail pays a second scan for unchanged content.
10. Reclassification and conflict, when a non-invalidated completed scan result exists for the current `## Atomic Decisions`: if it established no supersession relationship for the still-live active decision a repetition finding points at, that finding is reclassified `writer_repair` and the scan is not rerun — an accidental restatement has a writer exit instead of a scan/review ping-pong. If it did establish the relationship and review still reports the finding, `revise` returns a `needs_user_ruling` terminal carrying the review/scan conflict — no rescan, no repair: neither mechanism may overrule the other on the user's behalf. Decision-level matching between a repetition finding and the scan-established relationships uses a revise-side identity the orchestrating agent attaches to the finding it received — `repeated_live_decision`, carrying `target_atomic_decision_id`, `active_adr` (the active ADR's filename; a path resolves by its basename against the scan candidate's filename), `active_adr_number` (compatibility field carrying the active ADR id), and `atomic_decision_id`; the reviewer never writes it and the quality-review report schema is unchanged. Without that identity, any established relationship is conservatively treated as covering the finding: the clash goes to the user rather than letting a repair touch content that may legally restate a superseded decision.
11. Scan-rewrite loop: for an accepted scan rewrite request, call `write`, then immediately rerun `scan-supersession` before any further quality-review. If the rerun scan again returns an accepted rewrite request, continue the write-to-scan loop. A pending scan result — `awaiting_review`, or an `awaiting_rewrite` whose rewrite request the main agent did not accept — stops quality-review and returns that structured pending result to the caller.
12. In the scan-rewrite loop, quality-review may run only after the rerun scan has completed and any required rewrite-related durable `supersedes` evidence has been written. If the completed rerun scan finds no `supersedes` metadata to write, `revise` must still run quality-review again before accepting the draft. The non-scan write and reviewer-repair paths still run quality-review.
13. Scanner output cannot drive durable `supersedes` writes or promotion metadata unless structural validation has passed and the main agent has reviewed it. If either condition is missing, return a structured pending or review-needed result.
14. Tail-scan evidence diff: when the post-acceptance tail scan completes, its written result is diffed against the `supersedes` evidence the passing review round saw — the draft frontmatter's `supersedes` set at pass time. Additions only, or unchanged: the delivery passes with no further review (new evidence never supported the already-made pass). Removed or changed entries: one more quality-review round must re-judge acceptance — evidence the pass relied on is never pulled away silently — and that round counts into the shared round limit. When the pass landed on the last budgeted round and the owed re-review cannot run, `revise` ends `blocked_after_review_limit` and the report's `errors` carries `tail_evidence_rereview_budget_exhausted`, so the caller can mechanically read why the run blocked even though the last round itself had no blocking findings.
15. Passed composite: `revise` ends `passed` only when all of these hold — the last quality-review round has no blocking findings, a non-invalidated scan result for the current `## Atomic Decisions` exists with status `completed` or `skipped_no_active`, and no scan result is pending.

Runtime dispatch defaults for sub-agent / cli:

- Reviewer-disposition repair and scan-request rewrites should run on a high-reasoning, instruction-following model because first-draft quality is the main cost driver for the review loop.
- **Codex:** use `gpt-5.5` with `xhigh` reasoning effort for reviewer-disposition repair and scan-request rewrites. Do not enable fast mode. Do not pass a `service_tier` override; record it as omitted/default in run evidence.
- **Claude Code:** use Opus with high effort for reviewer-disposition repair and scan-request rewrites. This is the conservative production default until Claude cross-model smoke material can run again; do not report it as benchmark-proven while Claude quota or service health blocks validation.
- `quality-review` reviewer dispatch uses **QUALITY-REVIEW-PROMPTS.md**. Scanner dispatch uses **SCAN-SUPERSESSION-PROMPT.md**. Do not fork their prompt wording or judgement rules per model.

Output and required JSON report fields:

- Direct output includes `draft_adr_path`, `structured_report_path`, `final_status`, and `needs_user_ruling`.
- `revise` writes a detailed JSON report to an OS tmp structured run directory every time.
- Top-level report fields include `operation`, `final_status`, `draft_adr_path`, `structured_report_path`, `needs_user_ruling`, `ruling_request`, `quality_review_rounds`, `final_review_state`, `unresolved_blocking_findings`, `refused_findings`, `scan_status`, `final_scan_status`, `scan_rewrite_request_status`, `scan_rewrite_loops`, `scan_invalidated_by_atomic_decisions_change`, `pending_scan_result`, `scanner_output_structural_validation`, `main_agent_scan_review`, `scans`, `degradation_notes`, `child_report_paths`, `skipped_steps`, `evidence_status`, and `errors`.
- `final_status` uses the value set **defined in the `produce` section** (referenced, not restated here). The subset `revise` itself produces is `passed`, `needs_user_ruling`, `blocked_after_review_limit`, and `failed`, plus a supersession-scan pending carrier: the pending scan return rides in `pending_scan_result`, and when a pending scan is carried `final_status` is `needs_user_ruling` (pending is inherently a hand-off to the user). `no_adr` and write-stage `needs_context_ruling` are build-stage terminals produced by `produce`'s `write` step, not by `revise`.
- Evidence flags support `clean`, `degraded_writer_self_check_evidence`, `degraded_reviewer_evidence`, and `post_pass_polished_evidence`.
- Each quality-review round records round number, reviewer close status, verbatim reviewer report path, target ADR path, Source Decision Extract path, live atomic decision corpus path, per-finding blocking-finding dispositions, and whether the reviewed artifact still matches the final artifact.
- Blocking-finding dispositions are recorded per finding with the disposition class (`user_ruling`, `writer_repair`, `scan_evidence`, or `terminal`) and the disposition result — at least `fixed_by_write_modify`, `dispositioned_by_scan_supersession`, `scan_returned_awaiting_rewrite`, `scan_returned_awaiting_review`, `not_dispositioned_due_to_user_ruling`, and `terminal`; reclassified and review/scan-conflict findings carry their marker. `scans` records every scan with its role — pre-acceptance evidence closure or post-acceptance tail — and the tail scan's evidence-diff outcome.
- `scan_rewrite_loops` records each accepted scan rewrite loop with the write result, rerun scan status, whether rewrite-related durable `supersedes` evidence was written, and whether quality-review was allowed afterward.
- `scan_invalidated_by_atomic_decisions_change` is `true` whenever `## Atomic Decisions` changed after a scan; the report then records the invalidated scan result and the fresh scan that replaced it before acceptance.
- `pending_scan_result` is nullable and carries the structured `awaiting_rewrite` or `awaiting_review` scan return when revise stops before quality-review.
- `final_scan_status` records the final scan status that revise used for acceptance or pending handoff.
- `scanner_output_structural_validation` and `main_agent_scan_review` record whether scanner output passed structural validation and main-agent review before any durable metadata write or promotion metadata was produced.
- Refused findings record a disposition reason. Any unresolved blocking finding prevents `final_status: passed`.
- If scan rewrite disagreement indicates scan authority or lifecycle uncertainty, set `needs_user_ruling: true` and do not claim clean delivery.
- Child reviewer reports, Source Decision Extract, live atomic decision corpus, reviewer-loop evidence, and the revise report stay in OS tmp structured run directories or equivalent non-bounded-context evidence bundles.

### `quality-review` — independent ADR quality review

Review exactly one draft, active, or archived ADR at a time. Use **QUALITY-REVIEW-PROMPTS.md** for the report schema, review modes, status vocabulary, support-data handling, and dispatch parameters; the per-mode reviewer prompt is assembled by `scripts/review_prompt_assembly.py` from the single-authority fragments in **QUALITY-REVIEW-PROMPT-BLOCKS.md**. The reviewer only reports; it never edits files, asks questions, accepts author intent, reads writer self-check evidence, or reads hidden expected answers.

- **Input** — `target_adr_path`; optional `review_mode` (`quality_review` | `context_glossary_approval_preflight` | `frozen_glossary_review`; default `quality_review`); optional Source Decision Extract path; optional live atomic decision corpus path; bounded-context references needed for self-sufficiency and legal reference closure. Narrowing is carried by the mode name — there is no caller-chosen gate set/order parameter. `context_glossary_approval_preflight` runs only structural reviewability and CONTEXT.md glossary approval need checks, then stops; it is not complete ADR quality review and must not report full quality-review pass. `frozen_glossary_review` is the complete review minus the CONTEXT.md glossary approval need check, run with the glossary frozen; it is a narrowed subset (not an early-stop preflight) and may report a pass.
- **Output** — always a persisted JSON report file in an OS tmp run directory, returned as its path; there is no inline report form. The report file is generated mechanically from the reviewer's verdict payload by `scripts/review_verdict_report.py`, not hand-written by the reviewer.

### `scan-supersession` — supersession scanning

When a `draft/` ADR is created or modified, run the foreground supersession workflow for that trigger draft. First build the scan input with `scripts/scan_supersession_input.py`: it derives the bounded context from `draft_adr_path`, enumerates every `active/` comparison target, extracts `{filename -> description}` as advisory metadata, and never filters comparison targets by description. Then build Atomic-Decisions-only full packets with `scripts/scan_supersession_packet.py`; keep those full packet paths for ledger validation and result building. Model stages read compact decision JSON through the scanner prompt in **SCAN-SUPERSESSION-PROMPT.md**. Model output is provisional until structurally validated against the matching full packet by `scripts/scan_supersession_ledger.py` and re-reviewed by the main agent. Only after that review may `scripts/scan_supersession_result.py` write reviewed markable relationships into the trigger draft's `supersedes`; the same result helper also produces zero-active and review-pending structured returns.

Key constraints (do not background, do not silence — the user must see the report to retain the withdrawal right):

- **Empty `active/`** — if the derived context has no active ADR file, including the lazy-folder case where `docs/adr/active/` has not been created yet, **skip the scan**: do not dispatch a scanner and return `status=skipped_no_active`, `candidate_count=0`, `scanner_dispatched=false`.
- **Asymmetric defaults** — bias toward recall on topically-related comparison targets (a missed supersession is silent and worst); when unsure between FULL and PARTIAL, mark PARTIAL; flag low-confidence judgements loudly for priority review.
- **Partial supersession may not be marked directly** — if a new decision only changes part of an old atomic decision, the main agent must first revise the new ADR so it fully restates and replaces the old decision, and only then mark the supersession.
- **Description boundary** — `description` may be extracted for diagnostics or future shadow/advisory ordering, but the baseline operation never removes active candidates, changes mappings, or decides supersession from `description`. The `## Atomic Decisions` section is the decision authority.
- **Structured statuses** — return one of `skipped_no_active`, `completed`, `awaiting_rewrite`, or `awaiting_review`. `awaiting_rewrite` and `awaiting_review` are pending outcomes: surface them to the consumer and stop that operation flow before unrelated questions.
- **Write boundary** — `scan-supersession` writes only reviewed draft-side `supersedes` entries. It never writes active/archived `superseded_by`, never recomputes target status, and never archives targets; those stay in `promote-draft-to-active`.

When `revise` is orchestrating (including as the delivery-completion step `produce` delegates to via write → revise), the ordinary-path scan still runs after the draft ADR acceptance check accepts the draft — the post-acceptance tail. When a blocking finding itself requires durable `supersedes` scan evidence (`revise`'s scan-evidence disposition), the scan is that finding's disposition and runs before acceptance as pre-acceptance evidence closure. After an accepted scan rewrite, `revise` calls `write` and then reruns `scan-supersession` before any further quality-review.

- **Input** — a single `draft_adr_path` (the trigger draft to scan); its bounded context — and therefore the `active/` comparison set — is derived internally from this path, so this operation does not take `bounded_context_path`.
- **Output** — a structured object with `status`, `draft_adr_path`, derived `bounded_context_path`, `candidate_count`, `scanner_dispatched`, `description_filtering_used=false`, `decision_authority="## Atomic Decisions"`, `findings`, `rewrite_required`, `low_confidence`, `written_supersedes`, `frontmatter_write_status`, `escalations`, and `diagnostics`. `frontmatter_write_status` is the authority for whether this helper wrote draft frontmatter; `written_supersedes` lists non-empty durable relationships and can be empty when stale `supersedes` metadata was cleared.

### `promote-draft-to-active` — promote one draft into active

Promote a single `draft/` ADR through the **whole** draft→active migration in one call: apply its supersession marks to the targets it supersedes, move the draft itself into `active/`, recompute its own `status`, and return a structured result including an after-report.

The three parts of the promotion:

- **(i) Apply marks to the superseded active targets.** From the draft's `supersedes`, derive each target's `superseded_by` by inversion (swap `ours`/`theirs`, swap the `adr` pointer — use `scripts/supersession_converter.py`), but **only after an LLM re-verifies the target's current state** (still in `active/`, the atomic decision not already superseded by someone else). Recompute each touched target's `status` with `scripts/status_calculator.py`; `supersession_mark_back.py` covers the apply/conflict detection. A target whose **every** atomic decision is now superseded (`status` becomes `fully_superseded`) is moved into `archived/`; a **partially** superseded target (`partially_superseded`) stays in `active/`.
- **(ii) Move the promoted draft itself.** Move it from `draft/` into `active/` and **recompute its own `status` with the same `scripts/status_calculator.py` `compute_status`** (no separate status function) — projected from its new folder and which of its decisions are superseded.
- **(iii) Return structured.** Per target, what was applied; the promoted draft's move and new status; and the after-report.

**Conflict handling is best-effort, never blocking (replaces the old "stop and defer to human judgement").** When the re-verify finds a conflict, the mark is dispositioned per type rather than escalated:

- target **already archived**, or its **atomic decision already superseded by another draft** → skip applying, **remove that entry from the promoted draft's own `supersedes`** (the supersession is now moot), and list it in the after-report;
- target **no longer in `active/`** → skip applying, **keep that `supersedes` entry** (a human may later re-point it), and list it in the after-report.

All three conflict types go into the after-report and are flagged needs-human-review; none of them stops the promotion. Removing a moot entry from the *draft's own* `supersedes` while the draft is still in `draft/` is part of this disposition and is distinct from rollback of already-applied marks.

**The promotion is unconditional.** Any conflict on the target side never aborts it — the draft is always moved into `active/` and gets a `status`, independent of how the marks landed. Every skipped or unresolved item surfaces only in the after-report, never by interrupting the promotion.

- **Input** — a single `draft_adr_path` (the draft being promoted). Its bounded context — and therefore the `active/`/`archived/` folders the marks land in — is **derived internally from this path**; this operation does **not** take `bounded_context_path`.
- **Output** — per target, what was applied (`superseded_by` / `status`) and which targets were archived; the promoted draft's new path and new `status`; and the **after-report**: for each skipped or unresolved item, at least the target ADR, the conflict type, the disposition (skip + cleared entry / skip + kept entry), and whether it needs human review.

### `revise-and-promote-draft-to-active` — pre-promotion delivery completion, then promote

Complete an existing draft ADR's delivery quality under the frozen glossary, then promote it into `active/` only if that completion passes. Its orchestration contract lives in `scripts/revise_and_promote_contract.py`. `revise` and `promote-draft-to-active` are taken by reference; their input, prompt, and output definitions are not restated here.

- **Input** — a single `draft_adr_path`. Its bounded context is derived from this path, the same as `promote-draft-to-active`.
- **Flow** — call `revise` with `quality_review_mode: frozen_glossary_quality_review`. **Only when `revise` reports `passed` does it call `promote-draft-to-active`** with the same `draft_adr_path`. Any non-passed `revise` terminal (`needs_user_ruling`, `blocked_after_review_limit`, or `failed`) is returned as-is, leaving the draft in `draft/`; promotion is not called. `promote-draft-to-active`'s own spec and **unconditional-promotion semantics are unchanged** — the gate is this "promote only on passed" orchestration, not a change to promotion.
- **Output — thin wrapper report** — records only this layer's operation status, the `revise` sub-operation report path, whether it advanced to promotion, the `promote-draft-to-active` report path when it did, and the final handoff status. It does **not** copy the sub-operations' detailed review, scan, or promotion report fields. Direct output is the `draft_adr_path`, `structured_report_path`, `final_status`, and `needs_user_ruling` envelope.

### `extract-active-adr-desc` — retrieve the active-ADR description index

Extract the `{filename → description}` index of a bounded context's `active/` folder, built from each ADR's frontmatter `description`. This is mechanical extraction only — it reuses `scripts/description_index.py`, which is fed the `bounded_context_path` and resolves that context's `active/` itself, reads the `description` field, and never opens the body.

Deciding **which** active ADRs are relevant to the current topic, and loading their full text on demand, is **not** part of this operation — that judgement needs conversation context and stays with the consumer's opening discipline.

- **Input** — `bounded_context_path` (its `active/` folder is derived from this).
- **Output** — the structured `{filename → description}` index table.

## Not in /adr

**Reference-block generation and path-existence checking stay with the consumer.** They are consumer-document content-production logic, so the consumer assembles related-ADR blocks with its own generator and does not route this through `/adr`. Likewise, the **relevance judgement** needs the conversation context and stays in the consumer. `/adr` governs the ADR files and the lifecycle mechanism; CONTEXT.md governance (write authority, term retirement) stays with each consumer.
