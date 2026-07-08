<!-- This file is the single source of the fixed English prose that the ADR
     reference-block generator injects into a PRD. The generator reads this file
     from a path relative to its own module, and only fills in the rows and the
     same/cross bounded-context citation qualifier; it holds no prose of its own.
     Skeleton stays stable / instance is replaceable: the only part to swap if
     that authoritative spec ever moves is the instance half-sentence in the
     migration last task ("call `/adr revise-and-promote-draft-to-active` ...").
     Fragments are delimited by `<!-- @name -->` markers; `{{ROWS}}`,
     `{{CITATION}}`, `{{PATH}}`, `{{NOTE}}` are the generator's fill points. -->
<!-- @draft-section -->
## Related Draft ADRs

Every draft ADR listed below is an architectural decision this PRD implements; the implementing agent **must read each one's full body before implementing** — they are the authoritative spec and this PRD is only the overview.

{{ROWS}}

**Last task (depends on every other task in this PRD; must run last):** For each draft ADR listed above, call `/adr revise-and-promote-draft-to-active` and pass it that draft's `draft_adr_path`, handling each draft independently (partial promotion is an acceptable end state) — this completes the draft's delivery quality review and promotes it into active when it passes, leaving it unpromoted when it does not.

For each draft the command reports a non-passed terminal, leave it in `draft/` unpromoted and carry its terminal status and structured report path into this build's final report; call out specifically any draft that failed to pass within the review round limit. For each draft that passes but carries a semantic degradation, carry its degradation summary into the final report as well. Do not call `/adr promote-draft-to-active` directly to bypass the delivery-completion gate.
<!-- @active-section -->
## Related Active ADRs

The following are ground-truth references to understand while implementing this PRD — **for reference only; never a migration or supersession-marking target.**

{{ROWS}}
<!-- @draft-row -->
- **{{CITATION}}** (`{{PATH}}`)
<!-- @active-row -->
- **{{CITATION}}** (`{{PATH}}`){{NOTE}}
