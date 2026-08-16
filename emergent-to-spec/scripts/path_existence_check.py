"""Check the paths of caller-selected related ADR entries for emergent-to-spec.

The public function consumes the same entry mappings as the related ADR block
generator, reads only ``number`` and ``path``, and resolves every relative path
against an explicit repository root. Its scope is existence only: it does not
parse ADR content, infer lifecycle state, judge relevance, drop entries, or
depend on the process working directory.
"""

import os


class PathExistenceResult:
    """Batch verdict containing missing entries and an all-present flag."""

    def __init__(self, missing):
        self.missing = missing

    @property
    def all_present(self):
        return not self.missing


def check_path_existence(entries, repo_root):
    missing = []
    for entry in entries:
        absolute_path = os.path.join(repo_root, entry["path"])
        if not os.path.exists(absolute_path):
            missing.append(
                {
                    "number": entry["number"],
                    "path": entry["path"],
                }
            )
    return PathExistenceResult(missing)
