"""Pure helpers for ADR supersession atomic-decision pairs."""

import re


ATOMIC_DECISION_ID_RE = re.compile(r"^[A-Za-z]+$")
_INLINE_PAIR_RE = re.compile(
    r"- \{\s*ours:\s*(?P<ours>\[[^\]]+\]|[^,}]+),\s*"
    r"theirs:\s*(?P<theirs>\[[^\]]+\]|[^,}]+)\s*\}"
)


def legal_atomic_decision_id(value):
    return isinstance(value, str) and bool(ATOMIC_DECISION_ID_RE.fullmatch(value))


def parse_inline_pair(line):
    match = _INLINE_PAIR_RE.fullmatch(line.strip())
    if not match:
        raise ValueError(f"malformed supersession pair: {line}")
    return {
        "ours": _parse_value(match.group("ours")),
        "theirs": _parse_value(match.group("theirs")),
    }


def format_inline_pair(pair):
    return f"- {{ ours: {_format_value(pair['ours'])}, theirs: {_format_value(pair['theirs'])} }}"


def expand_atomic_decision_pairs(pairs, *, block_key):
    old_side, new_side = _pair_sides(block_key)
    expanded = []
    for pair in pairs:
        old_value = pair.get(old_side)
        if isinstance(old_value, list):
            raise ValueError(f"{block_key} old decision side must be scalar")
        new_values = pair.get(new_side)
        if not isinstance(new_values, list):
            new_values = [new_values]
        for new_value in new_values:
            expanded.append({old_side: old_value, new_side: new_value})
    return expanded


def compress_atomic_decision_pairs(pairs, *, block_key):
    old_side, new_side = _pair_sides(block_key)
    grouped = {}
    for pair in expand_atomic_decision_pairs(pairs, block_key=block_key):
        grouped.setdefault(pair[old_side], set()).add(pair[new_side])

    compressed = []
    for old_value in sorted(grouped):
        new_values = sorted(grouped[old_value])
        new_value = new_values[0] if len(new_values) == 1 else new_values
        compressed.append({old_side: old_value, new_side: new_value})
    return compressed


def supersession_pairs_are_valid(pairs, *, block_key):
    old_side, new_side = _pair_sides(block_key)
    if not isinstance(pairs, list) or not pairs:
        return False
    for pair in pairs:
        if not isinstance(pair, dict):
            return False
        old_value = pair.get(old_side)
        new_value = pair.get(new_side)
        if not legal_atomic_decision_id(old_value):
            return False
        if isinstance(new_value, list):
            if not new_value or not all(legal_atomic_decision_id(item) for item in new_value):
                return False
        elif not legal_atomic_decision_id(new_value):
            return False
    return True


def _pair_sides(block_key):
    if block_key == "supersedes":
        return "theirs", "ours"
    if block_key == "superseded_by":
        return "ours", "theirs"
    raise ValueError(f"unsupported supersession block: {block_key}")


def _parse_value(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return [item.strip() for item in value[1:-1].split(",") if item.strip()]
    return value


def _format_value(value):
    if isinstance(value, list):
        return "[" + ", ".join(value) + "]"
    return value
