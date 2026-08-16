"""Context derivation.

A pure, deterministic, dependency-free function: given an owning-draft ADR path,
derive the bounded-context root it belongs to. The context root is the full
prefix before `docs/adr/` (it may span several directory levels). Operations
whose input already carries an owning draft path (`promote-draft-to-active`,
`scan-supersession`) derive the context from that path instead of taking a
`bounded_context_path` — a draft can only supersede actives in its own context,
so the draft path alone determines the context.

A malformed path raises (fail-fast) rather than silently returning a guessed
context: a wrong context would let a later step touch the wrong folder, so it
must blow up early.
"""

import re

_ADR_PATH = re.compile(r"^(?P<context>.+)/docs/adr/(?:draft|active|archived)/[^/]+$")


def derive_context_root(adr_path):
    match = _ADR_PATH.match(adr_path)
    if match is None:
        raise ValueError(
            "ADR path does not match <context-root>/docs/adr/"
            "{draft|active|archived}/<file>: " + repr(adr_path)
        )
    return match.group("context")
