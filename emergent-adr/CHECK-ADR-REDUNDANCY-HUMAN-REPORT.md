# check-adr-redundancy human report

Fixed bulleted Markdown shape for one validated evaluation report. Empty
sections are omitted.

Presentation only: the structured evaluation report remains the semantic
authority. This template copies its fields without accepting,
rejecting, or rewriting any evaluation result. It presents ruling context but
does not generate the user-facing ruling question; the main agent writes that
question in the current conversational context.

## ADR conclusion

Present first:

- **ADR path:** `…`
- **ADR evaluation result:** `…`
- **Needs user ruling:** true|false

## Atomic decisions by result

Then group live atomic decisions by `evaluation_result`. Emit a section only
when that group has at least one decision. Fixed section order:

1. Fully redundant
2. Partially redundant
3. Fully retained
4. Ground-truth mismatch
5. Indeterminate

Each decision is a bullet with:

- **Decision `id`**
  - **Result:** `evaluation_result`
  - **Reason:** evaluation_reasoning
  - **Evidence:**
    - `source`: finding

For `atomic_decision_partially_redundant`, also list:

- **Redundant portion:** …
- **Retained portion:** …

## User ruling requests

Present only when `needs_user_ruling` is true and requests exist. One bullet
per request, after the decision groups, before the JSON path. Indeterminate
requests also list missing decisive fact, decision impact (retained if /
redundant if), and resolution path. These bullets are ruling context, not a
mechanically authored question; after presenting them, the main agent asks the
user a concrete question in its own words.

## JSON report

Always end with the evaluation report path:

- `/absolute/path/to/evaluation_report.json`
