---
name: adr-format-migration
description: One-shot mechanical migration for a bounded context's ADR files: compress supersession pairs, rename legacy ADR filenames to date-random ids, rewrite frontmatter adr links, and emit an old-id to new-id map.
---

# ADR Format Migration

## Quick Start

Run the deterministic migrator against either a bounded context path or its `docs/adr/` directory:

```bash
python3 /Users/zet/.claude/skills/adr-format-migration/scripts/migrate_adr_format.py /path/to/bounded-context
python3 /Users/zet/.claude/skills/adr-format-migration/scripts/migrate_adr_format.py /path/to/bounded-context/docs/adr
python3 /Users/zet/.claude/skills/adr-format-migration/scripts/migrate_adr_format.py /path/to/bounded-context --apply
```

No flag means dry-run. Dry-run prints a unified diff and does not write files. `--apply` performs the migration.

## What It Migrates

- Legacy ADR filenames `0001-slug.md` to `{YYYYMMDD}-{random4}-slug.md`.
- Frontmatter `adr:` values that point at migrated ADRs, rewritten to the migrated filename.
- Supersession `atomic_decisions` pairs into the standard compressed form, using the same pair expansion/compression helpers as the ADR scripts.
- A temporary `adr-id-migration-map.json` under `docs/adr/`, mapping old ids to new ids and filenames.

## Filename Rules

- The date segment comes from the file's first version-control add date.
- If the file has no committed add date, use the current date.
- The random segment is generated at migration time from the shared ADR id alphabet.
- If a generated id already exists in the context, generate again.
- The slug segment is preserved exactly.

## Boundaries

- The tool processes one bounded context per run.
- It only processes ADR markdown files under that context's `docs/adr/draft/`, `docs/adr/active/`, and `docs/adr/archived/` folders.
- It edits frontmatter and filenames only.
- It does not rewrite body prose citations. Use the emitted map as a temporary lookup aid while prose references are reviewed separately.
- The map is transitional support data, not a permanent source of truth.

## Verification

Run the tool tests after changing this skill or its script:

```bash
cd /Users/zet/.claude/skills/adr-format-migration/scripts
pytest
```
