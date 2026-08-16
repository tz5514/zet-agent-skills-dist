"""Subfolder-derivation helper.

Turn a bounded-context root into the path of a named subfolder under that
context's `docs/adr/`. Given the context root and which subfolder is wanted
(e.g. `active`), it returns `<root>/docs/adr/<subfolder>`.

This is the single place the `docs/adr/<sub>` folder layout is encoded. A
caller that needs such a folder passes only the bounded-context root and the
subfolder name, so it never hand-builds the layout and cannot get it wrong; if
the layout ever changes, this is the one place to update.

Pure path-joining only — it never touches the filesystem.
"""

import os


def derive_adr_subfolder(bounded_context_path, subfolder):
    return os.path.join(bounded_context_path, "docs", "adr", subfolder)
