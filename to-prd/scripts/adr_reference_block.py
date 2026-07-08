"""ADR reference-block generator.

Given a citation list — the draft ADRs this PRD will implement plus an optional
list of related active ADRs — and the PRD's own bounded context, return the
markdown text of up to two PRD sections:

  - `## Related Draft ADRs`   (rendered when the draft list is non-empty)
  - `## Related Active ADRs`  (rendered when the active list is non-empty)

The fixed prose (section headings, the must-read directive, the migration last
task, the reference directive) is NOT held here: it lives in the sibling
template `../templates/related-adrs-blocks.md`, which is its single source. This
module does mechanical assembly only — fill each row, apply the same/cross
bounded-context citation qualifier, drop an empty section — and produces no
semantic content of its own. Each entry's `bounded_context` is supplied by the
caller (the conversation-bound relevance-judgement step), never inferred from
the path, so the module is independent of any repo layout. It is a self-contained
unit that can later move wholesale into an `/adr` skill (carrying its template
and tests) without changing what a PRD receives.

An entry is a dict:
  - `number`           ADR stable id, e.g. "20260620-5udh"
  - `path`             repo-root-relative path of the ADR file
  - `bounded_context`  the ADR's owning context, e.g. "to-prd" (caller-supplied)
  - `relevance_note`   optional, active entries only — one line on why it is relevant
"""

import os
import re

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "templates",
    "related-adrs-blocks.md",
)


def _fragments():
    """Parse the template into its named fragments (`@name` markers)."""
    with open(_TEMPLATE_PATH, encoding="utf-8") as f:
        text = f.read()
    parts = re.split(r"(?m)^<!-- @([\w-]+) -->$\n?", text)
    return {parts[i]: parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}


def _citation(entry, prd_bounded_context):
    """Use a bare ADR id in-context, qualified by bounded context cross-context."""
    number = entry["number"]
    context = entry["bounded_context"]
    if context == prd_bounded_context:
        return f"ADR {number}"
    return f"{context} ADR {number}"


def _row(template, entry, prd_bounded_context, note=""):
    return (
        template.replace("{{CITATION}}", _citation(entry, prd_bounded_context))
        .replace("{{PATH}}", entry["path"])
        .replace("{{NOTE}}", note)
    )


def render_adr_reference_blocks(draft_entries, active_entries, prd_bounded_context):
    frag = _fragments()
    blocks = []
    if draft_entries:
        rows = "\n".join(
            _row(frag["draft-row"], e, prd_bounded_context) for e in draft_entries
        )
        blocks.append(frag["draft-section"].replace("{{ROWS}}", rows))
    if active_entries:
        rows = "\n".join(
            _row(
                frag["active-row"],
                e,
                prd_bounded_context,
                note=f" — {e['relevance_note']}" if e.get("relevance_note") else "",
            )
            for e in active_entries
        )
        blocks.append(frag["active-section"].replace("{{ROWS}}", rows))
    return "\n\n".join(blocks)
