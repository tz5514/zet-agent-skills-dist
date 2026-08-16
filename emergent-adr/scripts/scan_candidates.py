"""Scan-candidate enumerator.

Takes a bounded-context root, resolves that context's `active/` folder, and
lists the supersession scan's comparison targets: every ADR file in `active/`.
`draft/` and `archived/` are not comparison targets (a draft is not yet ground
truth; an archived decision cannot be superseded again) — and because only the
`active/` folder is listed, neither can structurally appear. An empty or not-yet
created `active/` yields an empty list.

The caller passes only the bounded-context root; the `active/` subfolder is
derived here via the shared subfolder-derivation helper, so the caller never
hand-builds the folder path. A root whose `docs/adr/` does not exist still raises:
only a valid ADR context with a lazily uncreated `active/` folder is treated as
zero active candidates.

Dependency-free by design (stdlib only).
"""

import json
import os
import sys

from adr_subfolder import derive_adr_subfolder


def list_scan_candidates(bounded_context_path):
    active_dir = derive_adr_subfolder(bounded_context_path, "active")
    adr_root = os.path.dirname(active_dir)
    if not os.path.isdir(adr_root):
        raise FileNotFoundError(adr_root)
    if not os.path.isdir(active_dir):
        return []
    return [
        os.path.join(active_dir, name)
        for name in sorted(os.listdir(active_dir))
        if name.endswith(".md")
    ]


def main(argv):
    """CLI: print the active/ candidate paths as a JSON list for the given
    bounded-context root, whose `active/` folder is resolved internally."""
    bounded_context_path = argv[0]
    print(json.dumps(list_scan_candidates(bounded_context_path), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
