"""Supersession-mapping converter.

`supersedes` and `superseded_by` are two views of one relationship, 100%
inter-convertible. A single entry is `{adr, atomic_decisions: [{ours, theirs}, ...]}`,
where `ours`/`theirs` are file-relative (ours = the file this entry lives on;
theirs = the other file). Converting an entry to its mirror is a clean involution:

  - swap `ours` <-> `theirs` in every atomic-decision pair, and
  - point `adr` at `self_adr` — the file the entry currently lives on — because
    the mirror lives on the old `adr` target and must point back here.

No `apply_status` and no aggregate status: the superseded file's `status` is
computed elsewhere (status calculator). Dependency-free (stdlib only).
"""


def convert_entry(entry, self_adr):
    return {
        "adr": self_adr,
        "atomic_decisions": [
            {"ours": a["theirs"], "theirs": a["ours"]} for a in entry["atomic_decisions"]
        ],
    }
