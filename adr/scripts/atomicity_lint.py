"""Atomicity structural-smell lint.

Reads one ADR's text and returns the list of decision bullets in its
`## Atomic Decisions` section that carry a *structural* non-atomicity smell. Two
smells are detected, per top-level decision bullet:

1. **Table** — a line inside the bullet that is a markdown table row (≥2 `|`).
2. **Multi-item enumeration** — the bullet contains ≥2 nested list items
   (child bullets `-`/`*`, or inline `N.` ordinals).

The lint only flags *suspects* by a reproducible counting rule; it never judges
whether a decision is truly atomic (that semantic call stays with the author),
never blocks, and never dispatches an LLM. The author re-judges each flagged
bullet with the partial-supersession test in ADR-FORMAT.md.

Dependency-free by design (stdlib only): these scripts run in arbitrary user
environments, so the section and bullets are found with a minimal line scanner,
not a markdown library.
"""

import json
import re
import sys

_PIPE_TABLE_MIN = 2  # a markdown table row carries at least two `|`
_ENUM_MIN = 2        # two-or-more nested items is the multi-item smell

# An inline `N.` ordinal list marker: digits then a dot, at the (possibly
# indented) start of a line, followed by whitespace. Anchored per line via
# re.MULTILINE so it never matches a decimal like "3.5" mid-sentence.
_ORDINAL_RE = re.compile(r"^\s*\d+\.\s", re.MULTILINE)


def lint_atomicity(text):
    """Return a list of suspect decision bullets in `text`'s `## Atomic
    Decisions` section. Each suspect is a dict: {id, smells} where `smells` lists the
    structural smell names ("table", "enumeration") found in that bullet."""
    suspects = []
    for bullet in _decision_bullets(text):
        smells = _smells(bullet["lines"])
        if smells:
            suspects.append({"id": bullet["id"], "smells": smells})
    return suspects


def _decision_bullets(text):
    """Return each top-level decision bullet in the `## Atomic Decisions` section
    as {id, lines}: its id letter (or None) and the bullet's own line plus the
    indented continuation lines that belong to it. A bullet ends at the next
    top-level (column-0) bullet."""
    bullets = []
    current = None
    for line in _decisions_section_lines(text):
        if _is_top_level_bullet(line):
            current = {"id": _bullet_id(line), "lines": [line]}
            bullets.append(current)
        elif current is not None:
            current["lines"].append(line)
    return bullets


def _decisions_section_lines(text):
    """Return the lines under the `## Atomic Decisions` heading, up to the next
    `## ` heading (or end of file)."""
    lines = text.splitlines()
    section = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line.strip() == "## Atomic Decisions"
            continue
        if inside:
            section.append(line)
    return section


def _is_top_level_bullet(line):
    return line[:2] in ("- ", "* ")


def _bullet_id(line):
    # The id is the bolded letter at the bullet head, e.g. "- **a.** ...".
    body = line[2:].lstrip()
    if body.startswith("**") and "." in body:
        label = body[2:body.index(".")].strip()
        if label:
            return label
    return None


def _smells(lines):
    smells = []
    if any(_is_table_row(line) for line in lines):
        smells.append("table")
    if _nested_item_count(lines) >= _ENUM_MIN:
        smells.append("enumeration")
    return smells


def _is_table_row(line):
    return line.count("|") >= _PIPE_TABLE_MIN


def _nested_item_count(lines):
    """Count nested list items inside a bullet — indented child bullets
    (`-`/`*`) and inline `N.` ordinals. The bullet's own head line is not in
    `lines` (only its continuation lines are), so every child bullet here is a
    nested item."""
    count = 0
    for line in lines:
        if _is_nested_bullet(line):
            count += 1
        count += _inline_ordinal_count(line)
    return count


def _is_nested_bullet(line):
    stripped = line.lstrip()
    return line != stripped and stripped[:2] in ("- ", "* ")


def _inline_ordinal_count(line):
    return len(_ORDINAL_RE.findall(line))


def main(argv):
    """CLI: print the suspect list as JSON for the given ADR file. The author
    runs this over their draft as a cheap structural self-check."""
    print(json.dumps(lint_atomicity(_read(argv[0])), ensure_ascii=False, indent=2))
    return 0


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
