"""Per-mode reviewer prompt assembly.

The reviewer prompt for each `quality-review` mode is assembled mechanically from
the single-authority fragment file `QUALITY-REVIEW-PROMPT-BLOCKS.md`. That file
holds four kinds of single-source fragments — a shared framework, one block per
review gate, and mode-specific rule blocks — and this module selects and orders
them per mode from a fixed assembly manifest, numbers the gates, instantiates the
placeholders, and writes the result to the run directory. Narrowing is structural:
a gate that is not on a mode's manifest never appears in that mode's prompt, so a
reviewer cannot run a gate the mode excluded. The agent does no rewriting,
adding, or reordering of fragment content — this module is the only assembler.
"""

import secrets
import shlex
from pathlib import Path

import prompt_fragments


_BLOCKS_PATH = Path(__file__).resolve().parent.parent / "QUALITY-REVIEW-PROMPT-BLOCKS.md"

_GATE_MARKER_PREFIX = "gate:"

# Where the mechanically-numbered REVIEW SCOPE gate list is expanded in a layout.
_GATES_STEP = "GATES"

INTEGRITY_MARKER_PREFIX = "REVIEWER PROMPT INTEGRITY MARKER"

# The path/value `{...}` placeholders in the scope-lock and output-contract
# fragments, instantiated at render. The report command is generated separately
# after these substitutions so placeholder-like path text cannot be rewritten
# recursively.
_PLACEHOLDER_KEYS = (
    "review_mode",
    "target_adr_path",
    "adr_format_path",
    "context_path",
    "bounded_context_reference_paths",
    "source_decision_extract_path_or_none",
    "live_atomic_decision_corpus_path_or_none",
    "run_dir",
    "verdict_script_path",
)

_VERDICT_SCRIPT_PATH = Path(__file__).resolve().parent / "review_verdict_report.py"
_VERDICT_COMMAND_PLACEHOLDER = "{verdict_command}"
_VERDICT_PAYLOAD_FILENAME = "verdict_payload.json"


def _fragments():
    """Parse the fragment file into `{marker_name: text}`, preserving order."""
    return prompt_fragments.parse_fragment_file(_BLOCKS_PATH)


def gate_ids():
    """The formal gate order — the single authority is the `@gate:` marker order
    in the fragment file."""
    return [
        name[len(_GATE_MARKER_PREFIX):]
        for name in _fragments()
        if name.startswith(_GATE_MARKER_PREFIX)
    ]


# Per-mode gate selection. The mode name carries the narrowing; there is no
# caller-chosen gate set/order. Selections are expressed against the formal gate
# order so a gate-order change flows through automatically.
def _mode_gate_selection():
    all_gates = gate_ids()
    return {
        "quality_review": list(all_gates),
        "context_glossary_approval_preflight": [
            "adr_structural_reviewability_check",
            "context_glossary_approval_need_check",
        ],
        "frozen_glossary_review": [
            gate_id for gate_id in all_gates if gate_id != "context_glossary_approval_need_check"
        ],
    }


# Per-mode assembly manifest: the ordered fragment layout for each mode. `GATES`
# marks where that mode's numbered REVIEW SCOPE gate list is expanded.
#
# The self-sufficiency framework is stored as two fragments — the closure
# framework (`framework:self-sufficiency-framework`) and the domain-term rules
# (`framework:domain-term-rules`) — because the preflight needs only the
# domain-term rules (they serve its glossary approval need gate) while
# reference-closure work belongs to the self-sufficiency check the preflight
# does not run. Modes running the self-sufficiency check select both fragments
# adjacently, which assembles to the exact pre-split text.
_MODE_LAYOUT = {
    "quality_review": [
        "framework:hard-role",
        "framework:scope-lock",
        "framework:review-scope-intro",
        _GATES_STEP,
        "framework:glossary-split-ownership",
        "framework:blocking-axes",
        "framework:non-blocking-downgrade",
        "framework:gate-inventory",
        "framework:reference-closure",
        "framework:self-sufficiency-framework",
        "framework:domain-term-rules",
        "framework:anti-cheat",
        "framework:output-contract",
    ],
    "context_glossary_approval_preflight": [
        "framework:hard-role",
        "framework:scope-lock",
        "framework:review-scope-intro",
        _GATES_STEP,
        "mode-rule:context-glossary-approval-preflight",
        "framework:blocking-axes",
        "framework:non-blocking-downgrade",
        "framework:gate-inventory",
        "framework:domain-term-rules",
        "framework:anti-cheat",
        "mode-rule:context-glossary-preflight-output-contract",
    ],
    "frozen_glossary_review": [
        "framework:hard-role",
        "framework:scope-lock",
        "framework:review-scope-intro",
        _GATES_STEP,
        "mode-rule:frozen-glossary-finding-routing",
        "framework:blocking-axes",
        "framework:non-blocking-downgrade",
        "framework:gate-inventory",
        "framework:reference-closure",
        "framework:self-sufficiency-framework",
        "framework:domain-term-rules",
        "framework:anti-cheat",
        "framework:output-contract",
    ],
}


def assembly_manifest():
    """The per-mode assembly manifest (mode -> ordered fragment layout)."""
    return {mode: list(layout) for mode, layout in _MODE_LAYOUT.items()}


def mode_gate_ids(review_mode):
    """The gates a mode actually runs, in formal order — the authority the
    mechanical report generator uses to derive which gates are skipped."""
    selection = _mode_gate_selection()
    if review_mode not in selection:
        raise ValueError(f"unsupported review mode: {review_mode}")
    return selection[review_mode]


def assemble_review_prompt_body(review_mode):
    """Assemble the prompt body for a mode: framework and gate fragments in the
    mode's manifest order, gates mechanically numbered. Deterministic — the same
    mode yields the same body. Excludes the integrity marker and leaves
    placeholders unfilled (those are applied by ``render_review_prompt``)."""
    if review_mode not in _MODE_LAYOUT:
        raise ValueError(f"unsupported review mode: {review_mode}")
    frag = _fragments()
    gates = _mode_gate_selection()[review_mode]
    parts = []
    for step in _MODE_LAYOUT[review_mode]:
        if step == _GATES_STEP:
            for number, gate_id in enumerate(gates, start=1):
                parts.append(f"{number}. {frag[_GATE_MARKER_PREFIX + gate_id]}")
        else:
            parts.append(frag[step])
    return "\n\n".join(parts)


def generate_integrity_marker():
    """A per-run random marker the reviewer must echo back; reading it wrong or
    missing it lets the mechanical layer catch a reviewer that never read the
    prompt file."""
    return secrets.token_hex(8)


def _verdict_command(review_mode, placeholders, integrity_marker):
    """Return the shell-safe mechanical report command for the rendered mode."""
    argv = [
        "python3",
        placeholders["verdict_script_path"],
    ]
    if review_mode == "context_glossary_approval_preflight":
        argv.append("preflight")
    argv.extend(
        [
            str(Path(placeholders["run_dir"]) / _VERDICT_PAYLOAD_FILENAME),
            integrity_marker,
        ]
    )
    if review_mode == "context_glossary_approval_preflight":
        argv.append(placeholders["target_adr_path"])
    argv.append(placeholders["run_dir"])
    return shlex.join(argv)


# The preflight runs no reference-resolution work, so its prompt never receives
# the bounded-context ADR store path: that placeholder is instantiated to a fixed
# withdrawn literal, leaving every other mode's inputs untouched.
_PREFLIGHT_WITHDRAWN_REFERENCE_PATHS = "none (this mode takes no bounded-context ADR references)"


def render_review_prompt(review_mode, placeholders, integrity_marker):
    """The dispatch-ready prompt: the integrity marker at the head, then the
    assembled body with every placeholder instantiated."""
    body = assemble_review_prompt_body(review_mode)
    if review_mode == "context_glossary_approval_preflight":
        placeholders = {
            **placeholders,
            "bounded_context_reference_paths": _PREFLIGHT_WITHDRAWN_REFERENCE_PATHS,
        }
    for key in _PLACEHOLDER_KEYS:
        body = body.replace("{" + key + "}", placeholders[key])
    body = body.replace(
        _VERDICT_COMMAND_PLACEHOLDER,
        _verdict_command(review_mode, placeholders, integrity_marker),
    )
    marker_line = f"[{INTEGRITY_MARKER_PREFIX}: {integrity_marker}]"
    return f"{marker_line}\n\n{body}"


def write_review_prompt_file(*, review_mode, placeholders, run_dir, integrity_marker=None):
    """Assemble, instantiate, and write the reviewer prompt to a run-directory
    file — the single authority for the prompt at dispatch time. Returns the
    prompt file path and the integrity marker it carries."""
    if integrity_marker is None:
        integrity_marker = generate_integrity_marker()
    run_dir = Path(run_dir)
    # the run directory and the mechanical script path are owned here, never by
    # the caller-supplied placeholder values
    placeholders = {
        **placeholders,
        "run_dir": str(run_dir),
        "verdict_script_path": str(_VERDICT_SCRIPT_PATH),
    }
    rendered = render_review_prompt(review_mode, placeholders, integrity_marker)
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = run_dir / f"reviewer_prompt_{review_mode}.md"
    prompt_path.write_text(rendered, encoding="utf-8")
    return {"prompt_path": str(prompt_path), "integrity_marker": integrity_marker}
