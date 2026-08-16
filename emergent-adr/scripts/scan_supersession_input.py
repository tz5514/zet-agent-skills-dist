"""Build the mechanical scan-supersession input.

This helper performs only path derivation and active-candidate enumeration. It
does not read ADR bodies, judge relevance, filter by description, or decide any
supersession relationship.
"""

import json
import sys

from context_derivation import derive_context_root
from description_index import extract_description_index
from scan_candidates import list_scan_candidates


def build_scan_input(draft_adr_path):
    bounded_context_path = derive_context_root(draft_adr_path)
    candidate_paths = list_scan_candidates(bounded_context_path)
    descriptions = extract_description_index(bounded_context_path)
    candidate_count = len(candidate_paths)
    return {
        "operation": "scan-supersession",
        "draft_adr_path": draft_adr_path,
        "bounded_context_path": bounded_context_path,
        "candidate_paths": candidate_paths,
        "candidate_count": candidate_count,
        "scanner_dispatched": candidate_count > 0,
        "zero_active": candidate_count == 0,
        "description_index": descriptions,
        "description_filtering_used": False,
        "decision_authority": "## Atomic Decisions",
    }


def main(argv):
    draft_adr_path = argv[0]
    print(json.dumps(build_scan_input(draft_adr_path), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
