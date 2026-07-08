"""One-shot ADR id and supersession-frontmatter migration tool."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime
import difflib
import json
import secrets
import subprocess
import sys
from pathlib import Path


ADR_SCRIPTS = Path(__file__).resolve().parents[2] / "adr" / "scripts"
if str(ADR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ADR_SCRIPTS))

from adr_id import adr_id_from_filename, generate_adr_id, parse_adr_filename  # noqa: E402
from supersession_pairs import compress_atomic_decision_pairs, format_inline_pair, parse_inline_pair  # noqa: E402


MAPPING_FILENAME = "adr-id-migration-map.json"
RELATION_KEYS = {"supersedes", "superseded_by"}
TOP_LEVEL_KEY_RE = r"^[A-Za-z_][A-Za-z0-9_]*:"


@dataclass(frozen=True)
class RenamePlan:
    old_path: Path
    new_path: Path
    old_id: str
    old_filename: str
    old_stem: str
    new_id: str
    new_filename: str


def migrate_adr_tree(root, apply=False, today=None, choose=None, first_commit_date=None):
    today = today or date_type.today()
    choose = choose or secrets.choice
    adr_root = _resolve_adr_root(Path(root))
    first_commit_date = first_commit_date or _git_first_commit_date

    errors = []
    plans = _build_rename_plans(adr_root, today, choose, first_commit_date, errors)
    ref_index = _reference_index(plans)
    mapping_payload = _mapping_payload(plans)
    mapping_path = adr_root / MAPPING_FILENAME

    file_updates = []
    for path in _adr_markdown_files(adr_root):
        if path == mapping_path:
            continue
        plan = next((candidate for candidate in plans if candidate.old_path == path), None)
        old_text = path.read_text(encoding="utf-8")
        new_text = _rewrite_adr_text(old_text, ref_index)
        new_path = plan.new_path if plan else path
        if old_text != new_text or new_path != path:
            file_updates.append((path, new_path, old_text, new_text))

    mapping_text = json.dumps(mapping_payload, ensure_ascii=False, indent=2) + "\n"
    old_mapping_text = mapping_path.read_text(encoding="utf-8") if mapping_path.exists() else ""
    mapping_changed = old_mapping_text != mapping_text

    diff = _build_diff(file_updates, mapping_path, old_mapping_text, mapping_text if mapping_changed else None)

    if apply and not errors:
        _apply_file_updates(file_updates)
        if mapping_changed:
            mapping_path.write_text(mapping_text, encoding="utf-8")

    return {
        "ok": not errors,
        "adr_root": str(adr_root),
        "changed_files": sorted(str(old_path) for old_path, _new_path, _old_text, _new_text in file_updates),
        "renamed_files": [
            {"from": str(plan.old_path), "to": str(plan.new_path)}
            for plan in plans
            if plan.old_path != plan.new_path
        ],
        "mapping_path": str(mapping_path),
        "id_map": {
            plan.old_id: {
                "old_filename": plan.old_filename,
                "new_id": plan.new_id,
                "new_filename": plan.new_filename,
            }
            for plan in plans
        },
        "diff": diff,
        "errors": errors,
    }


def _resolve_adr_root(root):
    if root.name == "adr" and root.parent.name == "docs":
        adr_root = root
    else:
        adr_root = root / "docs" / "adr"
    if not adr_root.exists():
        raise FileNotFoundError(f"ADR root not found: {adr_root}")
    return adr_root


def _adr_markdown_files(adr_root):
    lifecycle_dirs = [adr_root / name for name in ("draft", "active", "archived")]
    files = []
    for directory in lifecycle_dirs:
        if directory.exists():
            files.extend(directory.rglob("*.md"))
    return sorted(files)


def _build_rename_plans(adr_root, today, choose, first_commit_date, errors):
    used_ids = {adr_id_from_filename(path.name) for path in _adr_markdown_files(adr_root)}
    plans = []
    for path in _adr_markdown_files(adr_root):
        try:
            parsed = parse_adr_filename(path.name)
        except ValueError:
            continue
        if parsed["scheme"] != "legacy":
            continue

        created = first_commit_date(path, today)
        if isinstance(created, str):
            created = datetime.strptime(created, "%Y%m%d").date()
        new_id = _generate_unique_id(created, used_ids, choose)
        slug = parsed["slug"]
        new_filename = f"{new_id}-{slug}.md"
        new_path = path.with_name(new_filename)
        if new_path.exists() and new_path != path:
            errors.append(f"target filename already exists: {new_path}")
        plans.append(
            RenamePlan(
                old_path=path,
                new_path=new_path,
                old_id=parsed["id"],
                old_filename=path.name,
                old_stem=path.stem,
                new_id=new_id,
                new_filename=new_filename,
            )
        )
    return plans


def _generate_unique_id(created, used_ids, choose):
    while True:
        new_id = generate_adr_id(today=created, choose=choose)
        if new_id not in used_ids:
            used_ids.add(new_id)
            return new_id


def _git_first_commit_date(path, fallback):
    resolved = path.resolve()
    result = subprocess.run(
        [
            "git",
            "log",
            "--follow",
            "--diff-filter=A",
            "--format=%ad",
            "--date=format:%Y%m%d",
            "--",
            str(resolved),
        ],
        cwd=resolved.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    dates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not dates:
        return fallback
    return datetime.strptime(dates[-1], "%Y%m%d").date()


def _reference_index(plans):
    index = {}
    for plan in plans:
        for key in (plan.old_id, plan.old_stem, plan.old_filename):
            index[key] = plan.new_filename
    return index


def _mapping_payload(plans):
    return {
        "version": 1,
        "mappings": [
            {
                "old_id": plan.old_id,
                "old_filename": plan.old_filename,
                "new_id": plan.new_id,
                "new_filename": plan.new_filename,
            }
            for plan in sorted(plans, key=lambda item: item.old_id)
        ],
    }


def _rewrite_adr_text(text, ref_index):
    frontmatter, body = _split_frontmatter(text)
    if not frontmatter:
        return text
    frontmatter = _rewrite_adr_references(frontmatter, ref_index)
    frontmatter = _compress_supersession_blocks(frontmatter)
    return "".join(frontmatter) + body


def _split_frontmatter(text):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return [], text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[: index + 1], "".join(lines[index + 1 :])
    return [], text


def _rewrite_adr_references(lines, ref_index):
    rewritten = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("- adr:"):
            prefix = line[: len(line) - len(stripped)] + "- adr:"
            value, suffix = _split_value_and_suffix(stripped[len("- adr:") :])
            value = value.strip().strip("'\"")
            replacement = ref_index.get(value, value)
            rewritten.append(f"{prefix} {replacement}{suffix}")
        else:
            rewritten.append(line)
    return rewritten


def _split_value_and_suffix(raw):
    newline = "\n" if raw.endswith("\n") else ""
    content = raw[:-1] if newline else raw
    if "#" in content:
        value, comment = content.split("#", 1)
        return value, " #" + comment + newline
    return content, newline


def _compress_supersession_blocks(lines):
    output = []
    active_relation = None
    index = 0
    while index < len(lines):
        line = lines[index]
        top_key = _top_level_key(line)
        if top_key:
            active_relation = top_key if top_key in RELATION_KEYS else None

        if active_relation and line.strip() == "atomic_decisions:":
            output.append(line)
            pair_indent = None
            pairs = []
            index += 1
            while index < len(lines):
                candidate = lines[index]
                if _ends_pair_block(candidate):
                    break
                try:
                    pair = parse_inline_pair(candidate)
                except ValueError:
                    break
                if pair_indent is None:
                    pair_indent = candidate[: len(candidate) - len(candidate.lstrip())]
                pairs.append(pair)
                index += 1
            if pairs:
                indent = pair_indent or "      "
                for pair in compress_atomic_decision_pairs(pairs, block_key=active_relation):
                    output.append(f"{indent}{format_inline_pair(pair)}\n")
            continue

        output.append(line)
        index += 1
    return output


def _top_level_key(line):
    if line[:1].isspace():
        return None
    if ":" not in line:
        return None
    key = line.split(":", 1)[0]
    if key and key.replace("_", "").isalnum():
        return key
    return None


def _ends_pair_block(line):
    if not line.strip():
        return True
    if _top_level_key(line):
        return True
    stripped = line.lstrip()
    return stripped.startswith("- adr:") or stripped.endswith(":")


def _build_diff(file_updates, mapping_path, old_mapping_text, new_mapping_text):
    chunks = []
    for old_path, new_path, old_text, new_text in file_updates:
        chunks.extend(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=str(old_path),
                tofile=str(new_path),
            )
        )
    if new_mapping_text is not None:
        chunks.extend(
            difflib.unified_diff(
                old_mapping_text.splitlines(keepends=True),
                new_mapping_text.splitlines(keepends=True),
                fromfile=str(mapping_path),
                tofile=str(mapping_path),
            )
        )
    return "".join(chunks)


def _apply_file_updates(file_updates):
    for old_path, new_path, _old_text, new_text in file_updates:
        if old_path == new_path:
            old_path.write_text(new_text, encoding="utf-8")
            continue
        new_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_text(new_text, encoding="utf-8")
        old_path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="bounded context path or its docs/adr directory")
    parser.add_argument("--apply", action="store_true", help="write the migration; default is dry-run")
    args = parser.parse_args(argv)

    report = migrate_adr_tree(args.path, apply=args.apply)
    if args.apply:
        print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    else:
        print(report["diff"], end="")
        print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def _summary(report):
    return {
        "ok": report["ok"],
        "adr_root": report["adr_root"],
        "changed_files": report["changed_files"],
        "renamed_files": report["renamed_files"],
        "mapping_path": report["mapping_path"],
        "errors": report["errors"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
