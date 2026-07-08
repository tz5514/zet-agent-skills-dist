"""Build Atomic-Decisions-only packets for scan-supersession.

The packet is structural input for model stages. It contains file identity and
exact atomic decision ids/text, but excludes Background, Rationale, and
description from the decision packet. Description remains advisory metadata in
scan input, never relation evidence.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

from adr_id import adr_id_from_filename


DECISION_RE = re.compile(r"^- \*\*([^*]+)\.\*\*\s*(.*)$")


def adr_identity(path):
    return {"adr": path.name, "path": str(path), "number": adr_id_from_filename(path.name)}


def extract_atomic_decisions(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    atoms = []
    current = None
    in_section = False

    for line in lines:
        stripped = line.strip()
        if stripped == "## Atomic Decisions":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue

        match = DECISION_RE.match(stripped)
        if match:
            if current is not None:
                atoms.append(current)
            current = {"id": match.group(1), "text": match.group(2).strip()}
            continue
        if current is not None and stripped:
            current["text"] = f"{current['text']}\n{stripped}".strip()

    if current is not None:
        atoms.append(current)
    return atoms


def load_candidate_paths(candidate_list):
    return [
        Path(line.strip())
        for line in Path(candidate_list).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_packet(trigger, candidate_list):
    trigger_path = Path(trigger)
    candidate_paths = load_candidate_paths(candidate_list)
    return {
        "operation": "scan-supersession",
        "decision_authority": "## Atomic Decisions",
        "description_filtering_used": False,
        "trigger": {
            **adr_identity(trigger_path),
            "atomic_decisions": extract_atomic_decisions(trigger_path),
        },
        "candidates": [
            {
                **adr_identity(candidate_path),
                "atomic_decisions": extract_atomic_decisions(candidate_path),
            }
            for candidate_path in candidate_paths
        ],
    }


def legacy_json_shape(packet):
    return {
        "trigger": [
            [atom["id"], atom["text"]]
            for atom in packet["trigger"]["atomic_decisions"]
        ],
        "candidates": {
            candidate["number"]: [
                [atom["id"], atom["text"]]
                for atom in candidate["atomic_decisions"]
            ]
            for candidate in packet["candidates"]
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", required=True)
    parser.add_argument("--candidate-list", required=True)
    parser.add_argument("--out")
    parser.add_argument(
        "--legacy-json-shape",
        action="store_true",
        help="write the compact trigger/candidates shape used by scanner prompts",
    )
    args = parser.parse_args(argv)

    packet = build_packet(args.trigger, args.candidate_list)
    payload = legacy_json_shape(packet) if args.legacy_json_shape else packet
    out_path = (
        Path(args.out)
        if args.out
        else Path(tempfile.gettempdir()) / f"adr-scan-packet-{uuid.uuid4().hex}.json"
    )
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON_FILE: {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
