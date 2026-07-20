# Related ADR handling

Complete this flow before publishing the spec.

1. **Judge and normalize once.** Create `draft_entries` and `active_entries` once; every entry carries `number`, repository-root-relative `path`, and a caller-supplied `bounded_context` that is never inferred from the path. An active entry may also carry `relevance_note`.
   - Include every draft ADR that this spec will implement, regardless of which session produced it. A draft outside this spec's implementation stays out of both lists.
   - Include only active ADRs whose constraints are not obvious from the codebase and merit explicit navigation. Active entries remain reference-only and zero-write; listing one authorizes no lifecycle mutation.
   - Archived ADRs stay out of both lists.
   Judge relevance from the existing conversation only: keep candidate selection semantic, without interviewing the user or enumerating ADR directories.
   Selection is complete only when every ADR present in the existing conversation has been accounted for under these lifecycle and relevance rules; an empty result is valid only after that accounting.

2. **Validate the same normalized entries.** Set `entries = [*draft_entries, *active_entries]`, determine `repo_root` as the explicit repository root independently of the process working directory, then make the first call to [`check_path_existence(entries, repo_root)`](scripts/path_existence_check.py). Relative paths resolve against that root. The check covers existence only; lifecycle classification and relevance remain the judgement from step 1.
   When the result reports missing entries, retain each selected entry and start its repair at the explicit repository root. For that entry, perform an identity-based targeted lookup across repository paths using only identifying information already present in its `number` and repository-root-relative `path`; use the result only to correct that same normalized entry's number or current path yourself. Repeat the check until `all_present` without interrupting the user; repairing an existing entry does not broaden candidate selection. `all_present` completes path validation and opens general codebase exploration and repository inventory.

3. **Render from those entries.** Pass the same `draft_entries` and `active_entries` to [`render_adr_reference_blocks(draft_entries, active_entries, spec_bounded_context)`](scripts/adr_reference_block.py). The generator assembles the [fixed text](templates/related-adrs-blocks.md); use its output rather than hand-writing related ADR headings, rows, or lifecycle instructions.
   Call both public functions even when both lists are empty. Append a non-empty renderer result at the end of the spec, after every standard section. The generator owns omission: an empty draft list has no draft section or final task, an empty active list has no active section, and two empty lists return the exact empty string.

**Completion criterion:** the path result is `all_present` for the same normalized entries given to the renderer, and the renderer result is either appended at the end of the spec or is the exact empty string.
