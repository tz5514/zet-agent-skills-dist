"""Related ADR reference-block generator owned by emergent-to-spec.

Given caller-selected draft and active ADR entries plus the spec's bounded
context, return the Markdown text for up to two related ADR sections. The fixed
instruction text lives only in the sibling template; this module performs
mechanical assembly by filling rows, applying same-context or cross-context
citation qualifiers, and omitting empty sections.

Each entry is a mapping with caller-supplied values:

- ``number``: stable ADR identifier.
- ``path``: repository-root-relative current ADR path.
- ``bounded_context``: owning context; never inferred from ``path``.
- ``relevance_note``: optional note for an active ADR.
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
    with open(_TEMPLATE_PATH, encoding="utf-8") as template_file:
        text = template_file.read()
    parts = re.split(r"(?m)^<!-- @([\w-]+) -->$\n?", text)
    return {parts[i]: parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}


def _citation(entry, spec_bounded_context):
    if entry["bounded_context"] == spec_bounded_context:
        return f"ADR {entry['number']}"
    return f"{entry['bounded_context']} ADR {entry['number']}"


def _row(template, entry, spec_bounded_context, note=""):
    return (
        template.replace("{{CITATION}}", _citation(entry, spec_bounded_context))
        .replace("{{PATH}}", entry["path"])
        .replace("{{NOTE}}", note)
    )


def render_adr_reference_blocks(
    draft_entries, active_entries, spec_bounded_context
):
    fragments = _fragments()
    blocks = []
    if draft_entries:
        rows = "\n".join(
            _row(fragments["draft-row"], entry, spec_bounded_context)
            for entry in draft_entries
        )
        blocks.append(fragments["draft-section"].replace("{{ROWS}}", rows))
    if active_entries:
        rows = "\n".join(
            _row(
                fragments["active-row"],
                entry,
                spec_bounded_context,
                note=f" — {entry['relevance_note']}"
                if entry.get("relevance_note")
                else "",
            )
            for entry in active_entries
        )
        blocks.append(fragments["active-section"].replace("{{ROWS}}", rows))
    return "\n\n".join(blocks)
