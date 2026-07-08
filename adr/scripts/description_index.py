"""Description-index extractor.

Takes a bounded-context root, resolves that context's `active/` folder, and
returns a {filename -> description} table built from each ADR's frontmatter
`description` key. It never reads the body. An ADR with no `description` is kept
in the table with the value `None` (not an error — whether to warn is the
caller's call). A valid ADR context whose `active/` folder has not been created
yet yields an empty table.

The caller passes only the bounded-context root; the `active/` subfolder is
derived here via the shared subfolder-derivation helper, so the caller never
hand-builds the folder path. A root whose `docs/adr/` does not exist still raises:
only a valid ADR context with a lazily uncreated `active/` folder is treated as
an empty index.

Dependency-free by design (stdlib only): these scripts run in arbitrary user
environments, so frontmatter is parsed with a minimal line parser tuned to the
frozen single-string `description` contract, not a YAML library.
"""

import json
import os
import sys

from adr_subfolder import derive_adr_subfolder


def extract_description_index(bounded_context_path):
    active_dir = derive_adr_subfolder(bounded_context_path, "active")
    adr_root = os.path.dirname(active_dir)
    if not os.path.isdir(adr_root):
        raise FileNotFoundError(adr_root)
    if not os.path.isdir(active_dir):
        return {}
    index = {}
    for name in sorted(os.listdir(active_dir)):
        if not name.endswith(".md"):
            continue
        text = _read(os.path.join(active_dir, name))
        index[name] = _description_from_frontmatter(text)
    return index


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _description_from_frontmatter(text):
    for line in _frontmatter_lines(text):
        if line.startswith("description:"):
            value = line[len("description:"):].strip()
            value = _strip_quotes(value)
            return value or None
    return None


def _frontmatter_lines(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    body = []
    for line in lines[1:]:
        if line.strip() == "---":
            return body
        body.append(line)
    return []


def _strip_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def main(argv):
    """CLI: print the {filename -> description} table as JSON for the given
    bounded-context root, whose `active/` folder is resolved internally."""
    bounded_context_path = argv[0]
    print(json.dumps(extract_description_index(bounded_context_path), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
