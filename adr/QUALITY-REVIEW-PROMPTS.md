# ADR Quality Review Prompts

This file holds the ADR quality-review report schema and dispatch parameters, and specifies how the per-mode reviewer prompt is assembled. The prompt text itself is not stored here — it is assembled mechanically from the single-authority fragments in `QUALITY-REVIEW-PROMPT-BLOCKS.md`. Supersession scanner prompts live in `SCAN-SUPERSESSION-PROMPT.md`.

`quality-review` is an independent ADR operation. It reviews exactly one target ADR at a time; the target may live in `draft/`, `active/`, or `archived/`. It only reports. It never edits files, never asks the user questions, never accepts author intent, never accepts repair history, and never reads hidden expected answers.

`quality-review` always delivers its result as a persisted JSON report file and returns that file's path; there is no inline report form. The report file is generated mechanically from the reviewer's minimal verdict payload by `scripts/review_verdict_report.py` — the reviewer never hand-writes the full report schema.

## Reviewer prompt assembly (per review mode)

The reviewer prompt is not a single verbatim template. Each review mode's prompt is assembled mechanically by `scripts/review_prompt_assembly.py` from four kinds of single-authority fragment in `QUALITY-REVIEW-PROMPT-BLOCKS.md`:

- shared framework blocks;
- one review-gate block per gate — the `@gate:` marker order in the fragment file is the single authority for the formal gate order, and `quality_review_contract.GATE_COVERAGE_IDS` is derived from it;
- mode-specific rule blocks — a gate's duty adjustment under a particular mode (only the modes that need one carry one);
- one assembly manifest per mode.

No fragment content is duplicated anywhere else. A gate that is not on a mode's manifest is **structurally absent** from that mode's assembled prompt — the narrowing is structural, not an instruction the reviewer must choose to obey, so the reviewer cannot run a gate the mode excluded and spends no attention on unrelated gate text. The assembler numbers the gates, instantiates the placeholders, prepends a per-run random integrity marker, and writes the result to the run directory; that written file is the sole authority for the prompt at dispatch time. The agent does no rewriting, adding, or reordering of fragment content.

**Smoke discipline:** each mode's assembled prompt is the smoke unit. Any change to a fragment or an assembly manifest — including rewording — requires re-running the affected mode's reviewer smoke material, through the same delivery channel as real dispatch, before that mode's prompt may be used.

### The three named review modes

There is no caller-chosen gate set or order parameter; narrowing is carried by the mode name.

- `quality_review` — complete ADR quality review: every gate.
- `context_glossary_approval_preflight` — the interview-time preflight: `adr_structural_reviewability_check`, `context_glossary_approval_need_check`, then `adr_necessity_of_existence_check`, and stop. Necessity is conservative here: block only when the target is clearly not worth retaining as an ADR; insufficient confidence must pass to the later full review. It is not complete ADR quality review and must never report `review_status: pass`. Reference closure belongs to the self-sufficiency check, which this mode does not run: the preflight prompt receives no bounded-context ADR store path and instructs no reference resolution; its semantic verdict therefore omits `reference_closure`, while the report script mechanically supplies the fixed value `{"status": "not_evaluated", "checked_references": [], "unresolved_references": []}` to the unchanged report schema.
- `frozen_glossary_review` — the pre-promotion frozen glossary review: the complete ADR quality review minus `context_glossary_approval_need_check`, run with the CONTEXT.md glossary set treated as frozen (no term may be added or changed). It is a narrowed **subset**, not an early-stop preflight, so it does not take the preflight "must not pass" special case: when every gate it covers is evaluated with no blocking finding it may report `review_status: pass`, but the report must make clear that the user-ruling CONTEXT.md glossary approval need check did not run — a pass does not mean glossary approval needs were ever checked. Undefined, term-like wording that cannot be rewritten as ordinary prose without losing decision meaning is routed to `context_glossary_usage_discipline_check` as a writer-fixable finding; this mode raises no user-ruling glossary finding, and any semantic degradation caused by rewriting to resolve a glossary gap is recorded, together with the gap, in the report.

### ADR quality-review dispatch parameters

- **Foreground blocking:** this applies equally to CLI processes and native sub-agents. The main agent must wait for and collect the terminal result before it continues; receiving a dispatch handle is not completion. Parallel calls are allowed only behind a join barrier that collects every terminal result before the next ADR lifecycle step. Do not set a background mode or detach a dispatch.
- **Prompt delivery:** the assembled prompt is written to the run directory by the assembler. A runtime that can pass file content into the sub-agent through a non-LLM channel brings it in directly; otherwise the main agent sends only the mechanically generated runtime bootstrap that acquires it. For the HITL preflight, the runtime-neutral bundle helper specified below freezes and delivers the prompt together with its three required authority inputs. The main agent never transcribes prompt or authority content. The prompt file's head carries the per-run integrity marker, and the reviewer must echo it back so a reviewer that never read the file (or read it incompletely) is caught mechanically and that round is judged invalid. The reviewer-side script validation alone cannot catch a fabricated marker, so after the round the main agent verifies the persisted verdict payload's `integrity_marker` against the assembler-issued marker, and the report's `review_mode` against the dispatched mode; a mismatch on either judges the round invalid. Both checks are carried mechanically by `scripts/review_verdict_report.py`'s reviewer-output resolution when given the expected marker and mode.
- **Dispatch channel (uniform across dispatch points):** the runtime→channel assignment below is one rule shared by every sub-agent dispatch point in this skill — this reviewer dispatch, and every dispatch in the supersession-scan workflow (the parallel inner scanner and ledger dispatches, and outer review stages when they are delegated). No dispatch point gets its own channel assignment. The rule governs only which channel a dispatch uses; which steps dispatch at all, and which the main agent performs itself, stay as each operation's workflow defines them. Claude Code uses the fixed headless CLI adapter below; Codex, Cursor, and every other runtime use their native sub-agent facility. No dispatch point may improvise a different channel or fallback.
- **HITL preflight authority bundle:** for `context_glossary_approval_preflight` only, first run `python3 scripts/preflight_authority_bundle.py prepare --runtime <codex|claude-code|cursor> --target-adr <target_adr_path> --run-dir <run_dir>`. The helper derives `ADR-FORMAT.md` and `CONTEXT.md` from the target path, assembles the reviewer prompt, and freezes the ordered roles `reviewer_prompt`, `adr_format`, `context`, and `target_adr` in one manifest by path, byte count, and SHA-256. Its single `emit` command rechecks the manifest and every authority before emitting one complete role-framed bundle. A changed manifest or authority, non-zero command, missing role marker, truncated bundle, or absent bundle-completion marker makes the review round `tool_failed`; never fall back to serial rereads. Pass the returned runtime adapter fields verbatim and do not add caller-written bootstrap text. After the round, use the returned `integrity_marker` and `review_mode` for the existing mechanical report validation and require the reviewer to echo `AUTHORITY_BUNDLE_COMPLETE: <authority_bundle_nonce>`. This changes only authority delivery: assembled prompt bytes and order, allowed inputs, reviewer duties, model, effort, foreground join, report generation, integrity-marker validation, and every semantic gate remain unchanged. Other review modes retain their ordinary prompt-delivery path.
- **Runtime model:** prompt semantics and judgement rules are shared across runtimes; model assignment and effort are dispatch policy only.
  - **Codex:** use `gpt-5.6-sol` with `xhigh` reasoning effort. Do not enable fast mode. Do not pass a `service_tier` override; record it as omitted/default in run evidence. Dispatch the reviewer through Codex's native sub-agent facility — never through any CLI call, including the codex CLI.
    - For the HITL preflight, pass the helper's `task_name`, `fork_turns`, `model`, `reasoning_effort`, and `message` fields to Codex `spawn_agent` verbatim and do not inherit the parent conversation. After `spawn_agent` returns, the main agent waits for that exact sub-agent to reach a terminal state and collects its result before continuing. The generated message uses one outer `functions.exec` with exactly one nested `tools.exec_command` call to the common bundle emitter; it validates command completion, exact output length, and bundle boundary markers before releasing any authority. Later report-generation commands use direct `exec_command`, not another outer `functions.exec`.
  - **Cursor:** use `cursor-grok-4.5-high` with `high` reasoning effort. Do not enable fast mode. Dispatch the reviewer through Cursor's native `Task` sub-agent facility — never through the Cursor agent CLI.
    - For the HITL preflight, pass the helper's `subagent_type`, `description`, `prompt`, `model`, `run_in_background`, and `readonly` fields to Cursor `Task` verbatim. The helper selects the built-in `generalPurpose` sub-agent, sets `run_in_background: false`, and sets `readonly: false` so it can persist the verdict and run the report command. The main agent waits for `Task` to return its terminal result before continuing. The helper supplies the fixed model in `model`. The generated prompt requires one Terminal call to the common bundle emitter and validates the bundle boundary and four role markers. When Cursor externalizes a large Terminal result, it permits exactly one Read of the runtime-generated spill path returned by that result; this bounded continuation of the Terminal result still forbids authority retries or rereads of the manifest or individual authority files.
  - **Claude Code:** dispatch the reviewer through the CLI using the helper's common bundle emitter as stdin to `claude -p --model opus --effort high`; execute the returned `pipeline_command` verbatim so `pipefail` rejects an emitter failure instead of starting a review with incomplete input. The complete reviewer prompt, ADR-FORMAT.md, CONTEXT.md, and target ADR therefore arrive before the first model turn, and the reviewer must not reread them. This is a **temporary patch**: in-harness Agent (sub-agent) dispatch can set the model but cannot set reasoning effort per invocation, so a plain sub-agent silently inherits the main session's effort tier. Sub-agent dispatch remains the preferred long-term form; the CLI carries only model and effort and never carries review rules invented by the caller — the mechanically assembled prompt inside the frozen bundle stays the sole review authority. **Exit conditions:** (i) when the platform lets in-harness sub-agent dispatch set per-invocation effort (so the skill itself can set effort, with no file outside the skill folder), return to plain sub-agent dispatch and remove this patch; (ii) if `claude -p` is excluded from subscription billing and becomes expensive, this patch is unusable and a replacement must be found.
    - The fixed tier (opus + high) serves all three review modes (`quality_review`, `context_glossary_approval_preflight`, `frozen_glossary_review`); no per-mode tiers.
    - Effort `high` rests on a small-sample preliminary controlled comparison (same material, same dispatch channel): opus at high was clearly faster than opus at xhigh with no observed quality drop. A lower `medium` effort is a future experiment option — not adopted until measured.
    - Foreground-synchronous: the main agent waits for the `claude -p` process to exit and collects its terminal stdout and exit status before continuing. Never enable a background mode or detach the process.
    - Prompt delivery: piping the helper-emitted authority bundle into `claude -p` is the direct non-LLM-channel delivery form, so no reviewer-side acquisition bootstrap runs.
    - Restrict the reviewer's tool set with `--tools Read Write Bash`. Do not reach for `--allowed-tools`/`--disallowed-tools` here: those are prompt-free allow/deny permission rules, not a mechanism that narrows the available tool set.
    - When are in Claude code, run claude cli headless with the auto permission mode (`--permission-mode auto`), whose classifier gates each tool call without prompting. Never use `dontAsk` or `bypassPermissions` here: they strip the approval gate entirely, and a parent session's permission layer may reject the whole dispatch as an unsafe agent spawn. Pass `--allowedTools "Read Write Bash"` alongside it (the same flag as `--allowed-tools` above, in its camelCase spelling — used here in its legitimate role as a permission allow rule, while tool-set narrowing stays with `--tools`) so the reviewer's Read/Write/Bash are covered by an allow rule and never stall on a prompt.
    - Output capture is unchanged: the reviewer's reply still carries the one line `REVIEW_REPORT_PATH: <path>`; the main agent extracts that line mechanically from the CLI stdout and reads the report file. The default `--output-format` (text) is sufficient.
  - **Other runtimes:** use the strongest available instruction-following model that has re-passed reviewer smoke material. Moving tiers or effort levels requires re-running reviewer smoke material and recording the runtime as a model/effort experiment. Dispatch through the runtime's native sub-agent facility — never through any CLI call, including that runtime's own CLI.
- **Timeout:** Timeout budget is runtime dispatch policy, not prompt semantics. Choose a budget from smoke evidence and expected full-review duration for the selected runtime. A timeout returns a structured report with `reviewer_close_status: tool_failed`; it does not silently pass.
- **Evidence retention:** persisted reports are JSON and belong only in an OS tmp structured run directory or equivalent non-bounded-context evidence bundle. Do not write reviewer reports into production ADR folders, prompts, specs, CONTEXT.md, consumer docs, or formal ADRs.
- **Allowed reviewer inputs:** review mode (`review_mode`), target ADR, ADR-FORMAT.md, CONTEXT.md, bounded context ADR references needed for legal reference resolution or self-sufficiency, Source Decision Extract path/content when provided, live atomic decision corpus path/content when provided.
- **Forbidden reviewer inputs:** writer self-check evidence, current user work material, session transcript, author intent, repair history, hidden answer keys, generated implementation reports, tests, smoke artifacts, and any extra artifact not named in the allowed input set.

### Reviewer verdict payload and report delivery

The reviewer never hand-writes the report. Full and frozen glossary review write the shared minimal verdict payload: the integrity marker, per-gate evaluations, findings, reference closure, support-data statuses, terminal result, scope limitations, and close status. The HITL preflight writes a smaller semantic verdict containing only the integrity marker, explicit results for every reached preflight gate, findings, and scope limitations. `scripts/review_verdict_report.py` supplies the preflight's mode, target, fixed reference closure, support-data statuses, close status, non-glossary `action_data: null`, fixed glossary notice, and terminal result; it never defaults a missing gate to clear. The same script validates either mode-appropriate input, mechanically fills the unchanged full report schema, persists the report to the run directory, and prints the report file path.

The reviewer's outward reply need contain only one fixed-format line, `REVIEW_REPORT_PATH: <path>`. The main agent extracts that path mechanically and reads the report file; any other prose in the reply is ignored and is not a contract violation. A reply with no extractable path line, or a path with no valid report file, makes the review round invalid.

### ADR quality-review report schema

The report file is JSON, generated by the mechanical script from the verdict payload:

```json
{
  "target_adr_path": "...",
  "review_mode": "quality_review|context_glossary_approval_preflight|frozen_glossary_review",
  "review_status": "pass|fail|degraded|not_evaluated",
  "terminal_result": null,
  "preflight_status": "not_applicable|passed|failed|blocked",
  "full_quality_review_completed": true,
  "full_quality_review_notice": null,
  "support_data_status": "provided|missing|degraded|not_applicable",
  "source_decision_extract_status": "provided|missing|degraded|not_applicable",
  "live_atomic_decision_corpus_status": "provided|missing|degraded|not_applicable",
  "blocking": [
    {
      "issue": "...",
      "evidence_location": "...",
      "why_it_matters": "...",
      "suggested_fix": "...",
      "gate_id": "<canonical gate id>",
      "action_data": null
    }
  ],
  "non_blocking": [
    {
      "issue": "...",
      "evidence_location": "...",
      "why_it_matters": "...",
      "suggested_fix": "...",
      "gate_id": "<canonical gate id>",
      "action_data": null
    }
  ],
  "gate_coverage": {
    "adr_structural_reviewability_check": "evaluated|degraded|not_evaluated|skipped",
    "context_glossary_approval_need_check": "evaluated|degraded|not_evaluated|skipped",
    "context_glossary_usage_discipline_check": "evaluated|degraded|not_evaluated|skipped",
    "adr_self_sufficiency_check": "evaluated|degraded|not_evaluated|skipped",
    "adr_necessity_of_existence_check": "evaluated|degraded|not_evaluated|skipped",
    "adr_description_check": "evaluated|degraded|not_evaluated|skipped",
    "adr_background_check": "evaluated|degraded|not_evaluated|skipped",
    "adr_atomic_decisions_check": "evaluated|degraded|not_evaluated|skipped",
    "atomic_decision_eligibility_check": "evaluated|degraded|not_evaluated|skipped",
    "adr_rationale_check": "evaluated|degraded|not_evaluated|skipped",
    "source_decision_preservation_check": "evaluated|degraded|not_evaluated|skipped",
    "live_active_atomic_decision_repetition_check": "evaluated|degraded|not_evaluated|skipped",
    "same_file_decision_id_usage_check": "evaluated|degraded|not_evaluated|skipped"
  },
  "reference_closure": {
    "status": "closed|open|degraded|not_evaluated",
    "checked_references": [],
    "unresolved_references": []
  },
  "scope_limitations": [],
  "skipped_gate_reasons": {},
  "reviewer_close_status": "completed|tool_failed|scope_limited"
}
```

Every finding requires `gate_id`. It must be a canonical gate id returned by `review_prompt_assembly.gate_ids()` and must belong to the dispatched mode. Unknown, misspelled, null, or mode-out finding ids invalidate the review round before report generation.

`review_status` is `fail` when any `blocking` finding exists. It is `pass` only when all required axes were evaluated and no blocking finding exists. It is `degraded` when missing or degraded support data prevents a clean evaluation of one or more support-data-dependent axes. It is `not_evaluated` only when the reviewer could not make a scoped judgement at all.

Missing Source Decision Extract or live atomic decision corpus must be reflected in the relevant support-data status and gate coverage. A report must never mark Source Decision Extract preservation or repeated still-live active atomic decisions as cleanly evaluated when the support data was absent.

In `gate_coverage`, the status skipped means the gate was not reached because an earlier gate produced a terminal stop condition, or was excluded because the review mode does not run it (recorded with a mode-specific skipped reason such as `frozen_out_of_scope` or `context_glossary_approval_preflight_complete`). The first gate in a started review cannot be skipped because no earlier gate can stop it and every mode runs it.

In `context_glossary_approval_preflight` mode, `full_quality_review_completed` must be `false`, `full_quality_review_notice` must say that full ADR quality review has not run, and `review_status` must not be `pass` even when the preflight finds no blocking issue. Clean preflight uses `review_status: not_evaluated` to mean full ADR quality review was not evaluated; the preflight outcome is carried by `preflight_status`.

In `frozen_glossary_review` mode, the CONTEXT.md glossary approval need check is not part of the mode: its `gate_coverage` value is `skipped` with skipped reason `frozen_out_of_scope`, recording that the user-ruling glossary approval need was never checked. Unlike preflight, this mode is a narrowed subset of complete review, so `full_quality_review_completed` is `false` while `review_status` may still be `pass` when every covered gate evaluated with no blocking finding; `full_quality_review_notice` states that the frozen glossary review ran the complete gate set except the glossary approval need check. Semantic degradation from rewriting a glossary gap under the frozen glossary is recorded in `scope_limitations` alongside the gap.

When ADR necessity produces the terminal result `not_an_adr_candidate`, later gates must be skipped with reason `skipped_by_adr_necessity_failure`.
