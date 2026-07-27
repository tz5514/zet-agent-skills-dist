# Scan Supersession Prompt

This file is the authoritative prompt and dispatch contract for the `scan-supersession` operation's scanner sub-agents. Copy the prompt exactly and instantiate only the listed `{...}` placeholders. Any rewording — including porting to another language — must re-pass the seeded tests before it may be used.

## Runtime model

Scanner sub-agents use instruction-following models. Prompt semantics, helper scripts, structured schema, chunk policy, and judgement framework are shared across runtimes. Runtime-specific settings are dispatch policy only: model assignment, effort, timeout, retry, parallelism, and dispatch channel. They must not change prompt wording or judgement rules.

- **Codex:** gpt-5.6-terra with low effort for inner scanner and auxiliary ledger stages. Keep bounded outer review stages with the main agent; do not delegate them until a fixed rendered review contract has been independently benchmarked.
- **Claude Code:** Sonnet with medium effort for inner scanner/ledger stages; Sonnet with high effort for target-id review; Opus with medium effort for the remaining bounded outer review stages when those are delegated.
- **Other runtimes:** use an instruction-following model tier that has re-passed the same shared prompt and structural checks; do not fork prompt wording or judgement rules per model.

The dispatch channel is assigned per runtime by the one rule shared by every sub-agent dispatch point in this skill — this scanner dispatch and the quality-review reviewer dispatch alike (the rule's full statement, including the usage-scope premise, lives with the dispatch parameters in `QUALITY-REVIEW-PROMPTS.md`). On every runtime other than Claude Code (Codex included), dispatch through that runtime's native sub-agent facility — never through any CLI call, including that runtime's own CLI. On Claude Code, dispatch each stage through the CLI — a temporary patch — by piping the stage's rendered prompt file into `claude -p --model <model> --effort <effort> --permission-mode auto --allowedTools "Read Write Bash" --tools Read Write Bash < <promptfile>`, with the model and effort values taken verbatim from the stage tiers above; the CLI carries only dispatch and tier settings, never prompt content. Run the CLI headless with `--permission-mode auto` plus the `--allowedTools "Read Write Bash"` allow rule, and narrow the tool set with `--tools Read Write Bash`. Never use `dontAsk` or `bypassPermissions`: they strip the approval gate entirely, and a parent session's permission layer may reject the whole dispatch as an unsafe agent spawn. The coarse-grained allow rule is deliberate — the real write boundary is carried by each dispatch point's prompt constraints and the main agent's review of the output, not by fine-grained CLI permissions. Wait for every CLI call to finish before continuing. Never use `--bg` or any other backgrounding — backgrounding means detaching without waiting for the result; CLI processes started in parallel at the OS level and all joined by the main agent before it continues are compatible with the foreground-blocking semantics and are not backgrounding.

The promptfile source covers both dispatch layers. For the inner scanner and auxiliary ledger stages the promptfile is the chunk prompt file rendered into the run directory by `scripts/scan_supersession_delivery.py` (prompt delivery below); on Claude Code, piping that file into `claude -p` is the direct non-LLM-channel delivery form, so the one-line bootstrap is skipped and the integrity-marker contract is unchanged. The delegated bounded outer review stages have no mechanical assembler: when delegation actually happens, the main agent writes the instructions that would otherwise have gone into the dispatch parameters into a prompt file in the run directory and delivers it through the same pipe form — the content is unchanged, only the carrier changes, and no new prompt-content authority is created. This layer applies only when delegation actually happens; the outer review stages may instead be performed by the main agent itself.

Dispatch is always **foreground-synchronous (blocking)** — never background. On runtimes other than Claude Code, one native sub-agent per scan packet is spawned in parallel as orchestration allows; on Claude Code, one `claude -p` process per scan packet is started in parallel at the OS level. Either way the main agent joins all of them, structurally validates their output, performs final review, and returns structured `/adr` data for the consumer to render. The model tier is a landing parameter; moving it up or down requires re-passing the seeded tests.

## Operational parameters

- **Malformed output:** retry within the same configured slot. Exhausted retry returns `awaiting_review`, never a guessed semantic repair.
- **Supersession scan timeouts:** Codex uses 600 seconds for inner scanner and auxiliary ledger packet calls, 180 seconds for bounded review calls, and 120 seconds for status-only sanity calls. Claude Code uses 600 seconds for inner scanner and auxiliary ledger packet calls, 240 seconds for target-id, row-disagreement, false-unmapped, and mapped-old review calls, and 180 seconds for status-only and rewrite-status sanity calls. These are orchestration defaults, not semantic differences.
- **Cost reference:** a single model packet call normally lands around 20–31k tokens; total operation cost scales with chunk count and retry count. A single packet call far past that band (roughly 60k+) is a signal that the scope lock failed — investigate, don't normalise.

## Supersession scan prompt

On the ordinary path the scan runs after the trigger draft ADR has been accepted — the post-acceptance tail. When the orchestrating `revise` flow dispositions a blocking finding that itself requires durable `supersedes` scan evidence, the scan runs before acceptance as pre-acceptance evidence closure. The scan-rewrite loop rerun scan runs after an accepted rewrite has been applied by `write` and before any further quality-review. The main agent first runs `scripts/scan_supersession_input.py` for the trigger draft. If it returns `candidate_count=0`, the operation returns `status=skipped_no_active` through `scripts/scan_supersession_result.py` and no scanner is dispatched. Otherwise the main agent writes a candidate-list file from that exact active-candidate list, splits it per the chunk policy below, and for each chunk first writes a full packet JSON with `scripts/scan_supersession_packet.py` without `--legacy-json-shape`. Keep that full packet path: it is the validation and result-building packet. The scanner sub-agent prompt below may create its own compact legacy-shape JSON for model reading, but that compact JSON is not a validator packet. Candidate membership is never changed by `description`.

The prompt is used for both the inner scanner and the auxiliary complete ledger.
Instantiate only these placeholders:

- `{decision packet builder}` — absolute path to `scripts/scan_supersession_packet.py`.
- `{trigger ADR}` — absolute path of the one trigger draft.
- `{candidate list}` — path to a newline-separated file containing active candidate ADR paths.
- `{output file}` — the preassigned run-directory output file path for this chunk. The main agent preassigns one non-overlapping path per chunk before dispatch (`scripts/scan_supersession_delivery.py`), so parallel scanners never collide and a garbled path line still leaves a known place to look for the file.

Prompt delivery: a script renders each chunk's prompt file into the run directory (`scripts/scan_supersession_delivery.py`) by instantiating the placeholders above in the verbatim template below; the file head carries a per-dispatch random integrity marker. That written file is the sole authority for the dispatched prompt content — the main agent never transcribes prompt content. A runtime that can bring the file content into the sub-agent through a non-LLM channel brings it in directly; otherwise the main agent sends only the one-line fixed bootstrap instructing the scanner to read that file and execute exactly the instructions in it. The scanner must echo the marker in its output-file ledger JSON (`integrity_marker` field); ledger validation compares the echo against the dispatched marker, and a mismatch or absence fails structural validation — the scanner's mandatory first tool step only proves the tool ran, while the marker echo proves the prompt file itself was read. The path line stays single-duty and never carries the marker. The auxiliary complete ledger shares this same template, so the same delivery and marker contract covers it automatically.

The scanner delivers its judgement by writing the full ledger JSON into `{output file}` and replying with one fixed-format path line, `SCAN_LEDGER_PATH: <path>`. After the model returns, the main agent mechanically extracts that path line (`scripts/scan_supersession_delivery.py`), reads the ledger from the output file, and validates and formats it with `scripts/scan_supersession_ledger.py` using the matching full packet JSON for that chunk and the dispatched integrity marker. Any other prose in the reply is ignored and is not a contract violation. Malformed output — a reply with no extractable path line, a path with no readable output file, or an output file that fails structural validation — is retried within the same configured slot; exhausted retry returns `awaiting_review` through `scripts/scan_supersession_result.py`, never a guessed semantic repair, with no new retry budget and no second error channel. The `PARSER_FAILED` terminal keeps its fixed single-line inline reply and never goes through the output file — it happens before the scanner has any deliverable content, so there is no file to write. The main agent must re-review validated rows before writing. When calling `scripts/scan_supersession_result.py --write-draft-supersedes`, pass `--scanner-output-structural-validation-passed` and `--main-agent-scan-review-passed`; without both flags the helper must not write durable `supersedes` metadata. Rewrite-required rows are withheld from direct `supersedes` writes and return `awaiting_rewrite`.

Chunking is an orchestration policy, not a semantic rule. The default active-count policy is: 1–60 active candidates → 2 inner chunks and 1 ledger chunk; 61–100 → 4 inner chunks and 4 ledger chunks; 101–140 → 4 inner chunks and 3 ledger chunks; 141–200 → 8 inner chunks and 12 ledger chunks; above 200 is outside the expected bounded-context ceiling, so use a defensive fallback of roughly 25 candidates per inner chunk and `ceil(count / 50)` ledger chunks capped at 10. These numbers are based only on candidate count.

```
You are a supersession scanner sub-agent.

Allowed writes: only the decision packet builder's temporary JSON and your preassigned output file `{output file}`. Do not modify project files, create helper scripts, read expected-answer files, test fixtures, development notes, benchmark artifacts, historical run reports, or call agents/workers/LLM/model CLIs.

Mandatory first action:
Run exactly:
`python3 {decision packet builder} --trigger {trigger ADR} --candidate-list {candidate list} --legacy-json-shape`

Then read the JSON path printed as `JSON_FILE: <path>`. Do not inspect ADR files before this succeeds. The JSON is authoritative for candidate ids, atom ids, atom text, and atom counts. If the parser or JSON read fails, retry the same command once. If it still fails, final response must be exactly:
`PARSER_FAILED: decision JSON unavailable`

Input paths:
- Trigger ADR: `{trigger ADR}`
- Candidate list: `{candidate list}`

JSON schema:
`{"trigger":[["<trigger atom id>","<atom text>"]],"candidates":{"<candidate adr id>":[["<old atom id>","<atom text>"]]}}`

Judge only decision atoms from the parser JSON. Ignore description, Background, Rationale, examples, filenames, ADR ids, and prose outside decisions unless a decision atom itself contains normative text.

Do not use keyword search, lexical checklists, filename clues, atom-letter coincidence, topic labels, expected-answer patterns, prior model outputs, or domain vocabulary lists as decision rules. Read each atom for meaning in whatever language it uses.

Supersession means complete successor-regime replacement of an old decision atom by trigger atom(s). A changed value can be a full replacement when the same governed decision and the complete old normative payload are replaced. A partial exception, narrowed scope, changed edge case, or unresolved old obligation is not a markable full replacement unless the trigger also restates, preserves, or explicitly retires the rest of the old atom.

Private decomposition:
For each atom, decompose meaning into:
- governed decision: what choice or rule this atom controls;
- normative force: required, permitted, forbidden, delegated, or conditional;
- action/result;
- scope and condition;
- responsible or deciding party, if any;
- exception or edge branch, if any;
- secondary obligations and constraints;
- required visible artifact/result components, if any.

These are reasoning slots, not keyword categories.

Private fixed procedure:
For each candidate, privately evaluate each old atom independently before forming the aggregate row.

1. Governed-decision match: identify which trigger atom(s), if any, govern the same controlled choice as this old atom. If none do, the old atom is UNMAPPED.
2. Status classification: decide MARKABLE, NEEDS_REWRITE, or UNMAPPED from the old atom's governed decision and old-side normative payload before optimizing the right-side target ids.
3. Target-id selection: after status is decided, choose the minimal trigger ids that justify that status for this old atom. Include ids that replace the old action/value/result/authority/payload. For boundary decisions, include every trigger id needed to reconstruct the successor boundary; for behavior inside an already-selected branch, include only the behavior trigger ids.
4. Sibling isolation: aggregate old atoms only after every old atom has its own ledger status. A mapped sibling never turns an independently governed sibling into NEEDS_REWRITE, and an unmapped sibling never hides a mapped or rewrite-needed sibling.
5. Aggregate row: compute the candidate result only from the per-old-atom ledger.

Normative-vs-explanatory check:
- Treat text as residual payload only when it prescribes, permits, forbids, conditions, delegates, orders, or requires an observable result.
- Do not treat a pure reason, purpose, or consequence as residual payload.
- But do not downgrade a required component or constraint into explanation merely because it also explains why the rule exists.

For every old atom, decide exactly one ledger status:
- MARKABLE: trigger atom(s) fully replace the old atom's governed decision and old-side normative payload.
- NEEDS_REWRITE: trigger atom(s) govern the same decision or directly conflict with it, but some old-side normative payload is omitted, changed, contradicted, or left unresolved.
- UNMAPPED: no trigger atom governs the same decision closely enough to create either full replacement or rewrite pressure.

Core comparison:
1. Same decision gate: compare governed decision, not surface wording. Same broad topic is insufficient; same controlled choice is required.
2. Payload closure gate: before choosing MARKABLE, list all old-required normative payload in that old atom. If one old atom contains a covered core plus another required condition, exception, component, authority, follow-up, ordering constraint, or secondary duty that the trigger does not handle, the atom is NEEDS_REWRITE.
3. Residual direction gate: residual payload is old-side only. Trigger-side additions do not make an old atom rewrite-needed.
4. Value replacement gate: if the trigger replaces the same controlled choice with a different value, treat that value change as replacement, not residual payload. A different value is not a conflict by itself. This gate replaces only the value choice; it does not replace an old companion duty, after-effect, escalation, second action, or ordering constraint attached to that value.
5. Conflict gate: if trigger reverses old behavior under the same condition, classify NEEDS_REWRITE unless the trigger explicitly retires the old behavior.
6. Unmapped sibling gate: if a separate old atom controls an additional decision that the trigger does not govern, classify that old atom UNMAPPED, not NEEDS_REWRITE. NEEDS_REWRITE requires that the trigger governs the same old atom but incompletely.

Branch and regime reasoning:
- Edge-only old atom: if the whole old duty exists only inside one edge branch, map it when the trigger fully replaces that branch.
- Baseline-plus-edge old atom: if the old atom establishes a general duty and also says the duty applies in an edge branch, a trigger that only changes the edge branch is NEEDS_REWRITE because the general duty still needs explicit replacement or preservation.
- Regime replacement: if an old atom grants, denies, or switches behavior across a boundary and the trigger replaces that boundary with a successor regime, map every trigger atom needed to express the successor regime for that same controlled choice. Do not map only the locally closest side.
- Boundary target set: if the old atom's controlled choice is an eligibility, threshold, range, or state boundary, the right-side trigger ids must express the successor boundary for that same controlled choice. Include the complementary side only when it is needed to state that successor boundary; exclude trigger ids that only configure what happens after the boundary has already admitted or selected the behavior.
- Attached condition: if an old regime atom has an attached old-required condition beyond the replaced value itself, and trigger omits that condition, classify NEEDS_REWRITE against the replacement regime.

Required result reasoning:
- A broad old required result can be fully replaced by a more precise successor result when it serves the same required result duty and no old-required extra component remains.
- If an old atom requires an additional standalone component and the trigger does not govern that component, classify it UNMAPPED unless the same old atom also contains a covered result duty; in that combined case classify NEEDS_REWRITE.
- A phrase that only states why a result must be visible, reversible, auditable, safe, or useful is explanatory unless it requires a separate component or action.
- Trigger-side extra components do not create old residual payload.

Authority and permission reasoning:
- Same controlled decision with a different responsible or deciding party is NEEDS_REWRITE unless the trigger explicitly replaces that authority as part of the successor regime and no old authority rule remains.
- If an old atom grants permission or exception and the trigger narrows, forbids, or removes that permission/exception, classify NEEDS_REWRITE unless explicitly retired.
- A limitation on a non-final helper is MARKABLE when the trigger preserves the same helper as non-final and preserves final authority elsewhere. Do not require the old limitation wording to be restated literally.
- Advisory, reporting, or observation mechanics are MARKABLE when the same split of final authority and non-final assistance is preserved in meaning, even if the successor wording changes the concrete observation mechanism.

Negative invariant hard gate:
- If an old atom is solely a prohibition or hazard-prevention rule, do not map it merely because a trigger atom states an affirmative workflow property that might incidentally avoid that outcome.
- Map a negative invariant only when the trigger preserves, restates, or explicitly retires the same forbidden outcome.
- Otherwise it is UNMAPPED, not NEEDS_REWRITE, unless the trigger directly conflicts with it.

Multiple mappings:
- One old atom may map to multiple trigger atoms only when their combined meaning is needed for complete replacement.
- For one old atom mapped to multiple trigger atoms, evaluate old-side payload closure by the combined semantics of the mapped trigger atoms.
- A split across multiple trigger atoms is not a rewrite reason by itself.
- Still request rewrite when the combined trigger atoms omit, contradict, or leave unresolved old-side normative payload, including necessary conditions, exceptions, authority, required results, ordering constraints, or secondary duties.
- Multiple old atoms in one ADR remain independent. A mapped sibling never hides an unmapped or rewrite-needed sibling.

Candidate ledger:
Let ALL be every old atom id for the candidate in source order. Let M = MARKABLE ids, R = NEEDS_REWRITE ids, U = UNMAPPED ids. M, R, U must partition ALL.

Do not silently omit any candidate. A candidate with no replacement or rewrite pressure still needs a ledger entry whose old atoms are all UNMAPPED. This makes non-selection visible to the caller; the formatter will later hide all-UNMAPPED candidates.

Output delivery:
Write exactly one strict JSON object into your preassigned output file `{output file}`:
`{"integrity_marker":"<the integrity marker from the top of this prompt, echoed exactly>","rows":[{"candidate_id":"<candidate id>","ledger":[{"old_atom_id":"<old atom id>","status":"MARKABLE|NEEDS_REWRITE|UNMAPPED","trigger_atom_ids":["<trigger id>", "..."],"confidence":"high|low","basis":"<short basis>"}]}]}`
The file content must be that single JSON object and nothing else. `integrity_marker` echoes the marker from the top of this prompt exactly; the path line carries no marker.

Final response format:
After writing the output file, end your reply with one line in exactly this fixed format:
`SCAN_LEDGER_PATH: {output file}`
Any other sentence in your reply is ignored; only the path line is read.

Ledger rules:
- Include exactly one `rows` entry for every candidate id in parser JSON, in parser JSON candidate order.
- Each candidate ledger includes every old atom id from that candidate in source order.
- MARKABLE and NEEDS_REWRITE entries use actual trigger atom ids from the trigger inventory.
- UNMAPPED entries use an empty `trigger_atom_ids` list.
- Do not include aggregate status, legacy scanner-row text, markdown, code fences, notes, apologies, or pre/post text.
- `basis` is a short reason for that old atom's ledger status. It must not cite filenames, ADR ids, expected answers, or topic labels as evidence.

Confidence:
- `high` when governed decision, target ids, and residual decision are clear.
- `low` when mapping is plausible but the governed decision boundary, target set, or residual payload is ambiguous.

Final self-check before output:
- Every parser candidate id appears exactly once in `rows`.
- Every candidate ledger contains all and only that candidate's old atom ids in source order.
- Every old atom has exactly one ledger status.
- Every `trigger_atom_ids` value uses actual trigger atom ids.
- UNMAPPED entries have no trigger ids.
- The output file content is parseable as a single JSON object.
- The ledger JSON's `integrity_marker` echoes the marker from the top of this prompt exactly.
- The final response contains the `SCAN_LEDGER_PATH:` line with the output file path.
```
