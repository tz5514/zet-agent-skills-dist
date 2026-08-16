"""Necessity-conditions authority reader for `read-necessity-conditions`.

Resolves `ADR-NECESSITY-CONDITIONS.md` from this skill's own location,
mechanically validates the required structure — one shared-rules section first,
then one block per condition carrying the four fixed judgment sections in
order — and returns the complete verbatim text with its source path and the
validation status. It validates structure only, never condition semantics, and
it never summarizes: the caller receives the byte-identical document text.

Fail closed: a missing file, unreadable content, or invalid required structure
raises with the exact reason and returns no content. There is deliberately no
fallback path — a partial or reconstructed authority would look normal while
silently detaching every consumer's judgment from the single authority.

Headings are matched line-anchored instead of through a markdown parser: these
scripts are stdlib-only by design, and the authority document is prose-only
(no code fences), so a full parser adds dependency risk without precision.
"""

import json
import sys
from pathlib import Path


AUTHORITY_FILENAME = "ADR-NECESSITY-CONDITIONS.md"
# The one skill-root resolution of the authority file, shared by every caller
# that must point at the authority.
DEFAULT_AUTHORITY_PATH = Path(__file__).resolve().parent.parent / AUTHORITY_FILENAME

SHARED_RULES_HEADING = "## Shared rules"
CONDITION_HEADING_PREFIX = "## Condition:"
REQUIRED_CONDITION_SECTION_HEADINGS = (
    "### Core concept",
    "### Positive evidence required",
    "### Explicitly non-qualifying boundaries",
    "### Judgment requirements",
)


def read_necessity_conditions(authority_path=None):
    """Read and validate the authority; return its verbatim structured form.

    Returns `{"authority_full_text", "source_path", "structure_validation"}`
    where `structure_validation` carries the passed status and the condition
    names found, in document order. Raises on any read or structure failure.
    """
    path = Path(
        authority_path if authority_path is not None else DEFAULT_AUTHORITY_PATH
    )
    text = _read_full_text(path)
    condition_names = _validate_structure(text)
    return {
        "authority_full_text": text,
        "source_path": str(path.resolve()),
        "structure_validation": {
            "status": "passed",
            "condition_names": condition_names,
        },
    }


def _read_full_text(path):
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"authority is not a regular file: {resolved}")
    try:
        text = resolved.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"authority is not valid UTF-8: {resolved}") from error
    if not text.strip():
        raise ValueError(f"authority file is empty: {resolved}")
    return text


def _validate_structure(text):
    """Validate the required structure; return condition names in order."""
    lines = text.splitlines()
    shared_rules_indexes = [
        i for i, line in enumerate(lines) if line.strip() == SHARED_RULES_HEADING
    ]
    if len(shared_rules_indexes) != 1:
        raise ValueError(
            "authority must contain exactly one shared-rules section "
            f"({SHARED_RULES_HEADING!r}); found {len(shared_rules_indexes)}"
        )

    condition_indexes = [
        i
        for i, line in enumerate(lines)
        if line.strip().startswith(CONDITION_HEADING_PREFIX)
    ]
    if not condition_indexes:
        raise ValueError("authority defines no condition section")
    if condition_indexes[0] < shared_rules_indexes[0]:
        raise ValueError(
            "shared rules must come before every condition section"
        )

    names = []
    for position, start in enumerate(condition_indexes):
        name = lines[start].strip()[len(CONDITION_HEADING_PREFIX):].strip()
        if not name:
            raise ValueError("a condition heading carries no condition name")
        if name in names:
            raise ValueError(f"duplicate condition name: {name}")
        names.append(name)
        end = (
            condition_indexes[position + 1]
            if position + 1 < len(condition_indexes)
            else len(lines)
        )
        _validate_condition_block(name, lines[start + 1 : end])
    return names


def _validate_condition_block(name, block_lines):
    """Require exactly the four judgment sections, in order, each non-empty."""
    section_headings = [
        line.strip()
        for line in block_lines
        if line.strip().startswith("### ")
    ]
    if section_headings != list(REQUIRED_CONDITION_SECTION_HEADINGS):
        raise ValueError(
            f"condition {name!r} must carry exactly the sections "
            f"{list(REQUIRED_CONDITION_SECTION_HEADINGS)} in order; "
            f"found {section_headings}"
        )
    for heading, body_lines in _section_bodies(block_lines):
        if not any(line.strip() for line in body_lines):
            raise ValueError(f"condition {name!r} section {heading!r} is empty")


def _section_bodies(block_lines):
    heading_indexes = [
        i for i, line in enumerate(block_lines) if line.strip().startswith("### ")
    ]
    for position, start in enumerate(heading_indexes):
        end = (
            heading_indexes[position + 1]
            if position + 1 < len(heading_indexes)
            else len(block_lines)
        )
        yield block_lines[start].strip(), block_lines[start + 1 : end]


def main(argv):
    """CLI: print the structured return as JSON. Takes no arguments — the
    operation keyword itself is the complete input."""
    if argv:
        raise ValueError("read-necessity-conditions takes no arguments")
    print(json.dumps(read_necessity_conditions(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
