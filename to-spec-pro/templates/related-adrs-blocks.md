<!-- Fixed prose for the related ADR blocks appended to a spec. The to-spec-pro
     generator only fills the marked rows and citation fields. -->
<!-- @draft-section -->
## Related Draft ADRs

Every draft ADR listed below is an architectural decision this spec implements; the implementing agent **must read each one's full body before implementing** — each ADR is the authoritative spec, and this spec is only the overview.

{{ROWS}}

**Last task (depends on every other task in this spec; must run last):** For each draft ADR listed above, use the adr skill's `revise-and-promote-draft-to-active` operation and pass that draft's current path as `draft_adr_path`. Handle every draft independently; one failure does not stop the others, so all listed drafts are processed. A partial promotion set is a reportable result, not successful completion of the whole build.

When the operation reports a non-passed terminal status, leave it in `draft/` unpromoted and include its terminal status and structured report path in the final build report; specifically call out any draft that did not pass within the review round limit. When a draft passes with semantic degradation, include its degradation summary in the final build report.

Do not use the adr skill's lower-level `promote-draft-to-active` operation to bypass the delivery-completion quality gate.
<!-- @active-section -->
## Related Active ADRs

The following ADRs are ground-truth references to understand while implementing this spec. This block is reference navigation only and does not authorize lifecycle writes.

{{ROWS}}
<!-- @draft-row -->
- **{{CITATION}}** (`{{PATH}}`)
<!-- @active-row -->
- **{{CITATION}}** (`{{PATH}}`){{NOTE}}
