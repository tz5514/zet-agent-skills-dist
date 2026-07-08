"""ADR path-existence check.

A pure function that, at the moment to-prd writes each ADR citation entry,
mechanically verifies the entry's own `path` actually exists. Each entry is the
same dict the ADR reference-block generator consumes; this module reads only
`number` and `path` (ignoring `bounded_context` / `relevance_note`). The path is
repo-root-relative and already encodes its `draft/` or `active/` folder, so the
path itself is the single check basis — the module does NOT branch on
draft-vs-active.

Resolution uses an EXPLICIT repo root (passed in), never the process cwd, so the
verdict is independent of the working directory and reproducible.

Scope is strictly existence: it does NOT check content relevance (whether a draft
is truly relevant to this PRD is the LLM's judgement and cannot be mechanically
verified — folding it in here would re-introduce "scan the filesystem to decide
relevance" and hollow out that LLM judgement). The module only decides existence
and reports the misses; the act of investigating and self-correcting a miss
belongs to the to-prd SKILL.md flow, not here — this module never interrupts,
silently drops, or escalates.
"""

import os


class PathExistenceResult:
    """Verdict for a batch of entries: which entries are missing, and a
    convenience flag for the all-present case."""

    def __init__(self, missing):
        self.missing = missing

    @property
    def all_present(self):
        return not self.missing


def check_path_existence(entries, repo_root):
    missing = []
    for entry in entries:
        absolute = os.path.join(repo_root, entry["path"])
        if not os.path.exists(absolute):
            missing.append({"number": entry["number"], "path": entry["path"]})
    return PathExistenceResult(missing)
