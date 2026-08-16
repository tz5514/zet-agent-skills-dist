"""Live active atomic decision corpus builder.

Builds ADR quality-review support data for still-live active atomic decisions in
one bounded context. Corpus items include the stable source ADR filename needed
to validate durable supersession evidence, but omit source paths and ADR prose
outside the atomic decision text.
"""

import json
import os
import re
import sys
import tempfile

from adr_id import adr_id_from_filename
from adr_subfolder import derive_adr_subfolder
from context_derivation import derive_context_root


def build_live_atomic_decision_corpus(target_adr_path, bounded_context_path=None):
    if bounded_context_path is None:
        bounded_context_path = derive_context_root(target_adr_path)
    active_dir = derive_adr_subfolder(bounded_context_path, "active")
    adr_root = os.path.dirname(active_dir)
    if not os.path.isdir(adr_root):
        raise FileNotFoundError(adr_root)

    target_path = os.path.abspath(target_adr_path)
    active_path = os.path.abspath(active_dir)
    target_active_decisions_excluded = os.path.dirname(target_path) == active_path
    decisions = []
    if os.path.isdir(active_dir):
        for name in sorted(os.listdir(active_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(active_dir, name)
            if target_active_decisions_excluded and os.path.abspath(path) == target_path:
                continue
            text = _read(path)
            status = _frontmatter_value(text, "status")
            if status not in ("fully_ground_truth", "partially_superseded"):
                continue
            superseded_ids = _superseded_own_ids(text)
            for decision in _atomic_decisions(text):
                if decision["atomic_decision_id"] in superseded_ids:
                    continue
                decisions.append(
                    {
                        "id": f"L{len(decisions) + 1}",
                        "active_adr_number": adr_id_from_filename(name),
                        "active_adr": name,
                        "atomic_decision_id": decision["atomic_decision_id"],
                        "text": decision["text"],
                    }
                )

    return {
        "target_adr_path": target_adr_path,
        "bounded_context_path": bounded_context_path,
        "target_active_decisions_excluded": target_active_decisions_excluded,
        "decisions": decisions,
        "status": "ok",
        "errors": [],
    }


def write_live_atomic_decision_corpus(target_adr_path, bounded_context_path=None, output_dir=None):
    corpus = build_live_atomic_decision_corpus(target_adr_path, bounded_context_path)
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="adr-live-atomic-decision-corpus-")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "live-atomic-decision-corpus.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return output_path


def main(argv):
    target_adr_path = argv[0]
    bounded_context_path = argv[1]
    output_path = write_live_atomic_decision_corpus(target_adr_path, bounded_context_path)
    print(json.dumps({"output_path": output_path}, ensure_ascii=False, indent=2))
    return 0


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _frontmatter_value(text, key):
    prefix = f"{key}:"
    for line in _frontmatter_lines(text):
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            return _strip_quotes(value) or None
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


def _superseded_own_ids(text):
    ids = set()
    in_superseded_by = False
    for line in _frontmatter_lines(text):
        stripped = line.strip()
        if stripped == "superseded_by:":
            in_superseded_by = True
            continue
        if line and not line[0].isspace() and stripped.endswith(":"):
            in_superseded_by = False
        if not in_superseded_by:
            continue
        if stripped.startswith("ours:"):
            ids.add(_strip_quotes(stripped[len("ours:"):].strip()))
        elif stripped.startswith("- ours:"):
            ids.add(_strip_quotes(stripped[len("- ours:"):].strip()))
        elif stripped.startswith("- {"):
            match = re.search(r"(?:\{|,)\s*ours:\s*([^,}]+)", stripped)
            if match:
                ids.add(_strip_quotes(match.group(1).strip()))
    return ids


def _atomic_decisions(text):
    lines = text.splitlines()
    in_section = False
    decisions = []
    current = None
    decision_pattern = re.compile(r"^-\s+\*\*([^.*]+)\.\*\*\s+(.+)$")

    for line in lines:
        if line.startswith("## "):
            if line.strip() == "## Atomic Decisions":
                in_section = True
                continue
            if in_section:
                break
        if not in_section:
            continue

        match = decision_pattern.match(line)
        if match:
            if current is not None:
                decisions.append(current)
            current = {
                "atomic_decision_id": match.group(1).strip(),
                "text": match.group(2).strip(),
            }
        elif current is not None and line.strip():
            current["text"] = f"{current['text']} {line.strip()}"

    if current is not None:
        decisions.append(current)
    return decisions


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
