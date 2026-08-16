"""Shared parser for marker-partitioned prompt template files.

`CHECK-SHOULD-WRITE-ADR-PROMPT.md`, `CHECK-ADR-REDUNDANCY-PROMPT.md`, and
`QUALITY-REVIEW-PROMPT-BLOCKS.md` are partitioned into named single-source
fragments by `<!-- @name -->` marker lines. This module is the one parser of
that format, so the prompt assemblers can never carry diverging copies of the
same parsing rule.
"""

import re
from pathlib import Path


# A marker names the fragment that follows it. Only a marker standing alone on
# its own line partitions the file; the same text inline stays fragment content.
_MARKER_LINE_RE = re.compile(r"(?m)^<!-- @([\w:-]+) -->$\n?")


def parse_fragment_file(path):
    """Parse a marker-partitioned file into `{marker_name: text}`, preserving
    document order. Text before the first marker is not a fragment; each
    fragment's surrounding blank lines are stripped, inner content is kept
    verbatim."""
    text = Path(path).read_text(encoding="utf-8")
    parts = _MARKER_LINE_RE.split(text)
    return {parts[i]: parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}
