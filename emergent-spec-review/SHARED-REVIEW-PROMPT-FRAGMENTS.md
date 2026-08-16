# Shared reviewer prompt fragments

These fragments are the single authoring source for rules both reviewer axes receive. `prompt_assembly.py` expands each token in both axis templates before dispatch; reviewers receive the complete expanded prompt, never this source file.

<!-- SHARED_AUTHORITY_LOAD_FAILURE:START -->
The load must be your own and complete: the dispatching agent's earlier load, a description, a paraphrase, a summary, or your memory of the philosophy never counts as loaded.

If the load fails — the skill is missing, unreadable, or only a description came back — your entire final reply must be exactly one line, and you must write no report file:

    REVIEW_AUTHORITY_LOAD_FAILURE: <short reason>

A failed load ends the run: never judge from memory instead, because a review made without the loaded philosophy is not a degraded review but no review at all.
<!-- SHARED_AUTHORITY_LOAD_FAILURE:END -->

<!-- SHARED_CANDIDATE_IDENTITY:START -->
- **Candidate identity:** `{{CANDIDATE_DIGEST}}` — copy this verbatim into your report; it is derived from the Candidate's own text, so a report carrying a different value is discarded as a review of some other version.
<!-- SHARED_CANDIDATE_IDENTITY:END -->

<!-- SHARED_NO_REPAIR_ADVICE:START -->
Never write a fix: no suggested wording, no replacement text, no implementation example, no redesign — diagnosing the problem and its failure is the whole of your job, and repair belongs to someone who holds decisions you do not.
<!-- SHARED_NO_REPAIR_ADVICE:END -->

<!-- SHARED_SELF_CHECK_AND_HAND_BACK:START -->
After writing the report, self-check its structure:

    {{SELF_CHECK_COMMAND}}

Fix the report until the command prints `valid`. Then end your reply with exactly one line:

```
REVIEW_REPORT_PATH: {{REPORT_PATH}}
```
<!-- SHARED_SELF_CHECK_AND_HAND_BACK:END -->
