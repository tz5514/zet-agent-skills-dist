"""Prepare one frozen HITL preflight authority bundle for any supported runtime.

The common core freezes the reviewer prompt, the skill's own ADR format spec,
the context's CONTEXT.md, and the target ADR. Runtime adapters only decide how that same bundle reaches the
reviewer: a Codex native tool result, Claude Code stdin, or one Cursor native
sub-agent Terminal acquisition (with one read of Cursor's runtime-generated
spill file when the Terminal externalizes a large result).
"""

import argparse
import hashlib
import json
import secrets
import shlex
import sys
from pathlib import Path

from context_derivation import derive_context_root
from review_prompt_assembly import write_review_prompt_file


REVIEW_MODE = "context_glossary_approval_preflight"
_SCRIPT_PATH = Path(__file__).resolve()
# ADR-FORMAT.md is this skill's own spec file: its sole authoritative copy sits
# beside SKILL.md, so it never resolves from the bounded context and a
# same-named file there is ignored. Only CONTEXT.md belongs to the context.
_ADR_FORMAT_PATH = _SCRIPT_PATH.parent.parent / "ADR-FORMAT.md"
_AUTHORITY_ROLES = ("reviewer_prompt", "adr_format", "context", "target_adr")
_MANIFEST_FILENAME = "preflight_authority_manifest.json"
_RUNTIME_POLICIES = {
    "codex": {
        "model": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
    },
    "claude-code": {
        "model": "opus",
        "reasoning_effort": "high",
    },
    "cursor": {
        "model": "cursor-grok-4.5-high",
        "reasoning_effort": "high",
    },
}


def _resolve_file(path, role):
    resolved = Path(path).resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{role} authority is not a regular file: {resolved}")
    return resolved


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _authority_markers(role, byte_count, sha256):
    identity = f"role={role} bytes={byte_count} sha256={sha256}"
    return (
        f"<<<ADR_AUTHORITY_BEGIN {identity}>>>",
        f"<<<ADR_AUTHORITY_END {identity}>>>",
    )


def _bundle_markers(nonce):
    return (
        f"<<<ADR_AUTHORITY_BUNDLE_BEGIN nonce={nonce}>>>",
        f"<<<ADR_AUTHORITY_BUNDLE_END nonce={nonce}>>>",
    )


def _render_authority(role, data):
    text = data.decode("utf-8")
    begin, end = _authority_markers(role, len(data), _sha256(data))
    separator = "" if text.endswith("\n") else "\n"
    return f"{begin}\n{text}{separator}{end}"


def _utf16_units(text):
    return len(text.encode("utf-16-le")) // 2


def _authority_spec(role, path):
    resolved = _resolve_file(path, role)
    data = resolved.read_bytes()
    return {
        "role": role,
        "path": str(resolved),
        "bytes": len(data),
        "sha256": _sha256(data),
    }


def _verify_prompt_authority_paths(prompt_path, expected_paths):
    prompt = prompt_path.read_text(encoding="utf-8")
    for role, path in expected_paths.items():
        if str(path) not in prompt:
            raise ValueError(f"assembled prompt lost {role} authority path identity")


def _load_manifest(path, expected_sha256):
    manifest_path = _resolve_file(path, "manifest")
    raw = manifest_path.read_bytes()
    if _sha256(raw) != expected_sha256:
        raise ValueError("authority manifest sha256 changed")
    manifest = json.loads(raw)
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported authority manifest schema")
    if manifest.get("review_mode") != REVIEW_MODE:
        raise ValueError("authority manifest review mode changed")
    authorities = manifest.get("authorities")
    if not isinstance(authorities, list):
        raise ValueError("authority manifest authorities must be a list")
    if [item.get("role") for item in authorities] != list(_AUTHORITY_ROLES):
        raise ValueError("authority manifest roles changed")
    if not isinstance(manifest.get("authority_bundle_nonce"), str):
        raise ValueError("authority manifest nonce is missing")
    return manifest


def _render_bundle(manifest, authority_data):
    nonce = manifest["authority_bundle_nonce"]
    begin, end = _bundle_markers(nonce)
    header = (
        f"{begin}\n"
        f"You are the independent ADR reviewer for `{REVIEW_MODE}`.\n"
        "The complete frozen authority bundle is below. Treat the "
        "`reviewer_prompt` role as the sole review instruction and the other "
        "roles as its required inputs. Do not read any of the four authority "
        "files again. Follow the reviewer prompt exactly and include its "
        "`REVIEW_REPORT_PATH` line in your final response.\n"
    )
    bodies = [
        _render_authority(role, authority_data[role])
        for role in _AUTHORITY_ROLES
    ]
    footer = (
        f"{end}\n"
        f"Your final response must also include "
        f"`AUTHORITY_BUNDLE_COMPLETE: {nonce}`."
    )
    return header + "\n".join(bodies) + "\n" + footer


def emit_bundle(*, manifest_path, expected_manifest_sha256):
    """Emit the complete bundle, refusing any changed identity."""
    manifest = _load_manifest(manifest_path, expected_manifest_sha256)
    authority_data = {}
    for item in manifest["authorities"]:
        role = item["role"]
        path = _resolve_file(item["path"], role)
        data = path.read_bytes()
        if len(data) != item["bytes"]:
            raise ValueError(f"{role} authority byte count changed")
        if _sha256(data) != item["sha256"]:
            raise ValueError(f"{role} authority sha256 changed")
        authority_data[role] = data
    return _render_bundle(manifest, authority_data)


def _emit_command(manifest_path, manifest_sha256):
    return shlex.join(
        [
            "python3",
            str(_SCRIPT_PATH),
            "emit",
            "--manifest",
            str(manifest_path),
            "--expected-manifest-sha256",
            manifest_sha256,
        ]
    )


def _codex_message(spec, nonce):
    encoded = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    return f"""You are the independent ADR reviewer for `{REVIEW_MODE}`.

Your first tool call must be exactly one `functions.exec` call containing the raw JavaScript below. Do not call any other tool first. It acquires the complete frozen authority bundle in one nested command. If it emits `AUTHORITY_BUNDLE_FAILED`, stop and report `tool_failed`; do not retry or read any authority separately.

```javascript
const spec = {encoded};
const result = await tools.exec_command({{
  cmd: spec.cmd,
  yield_time_ms: 10000,
  max_output_tokens: spec.maxOutputTokens
}});
if (
  result.exit_code !== 0 ||
  result.session_id != null ||
  typeof result.output !== "string" ||
  result.output.length !== spec.expectedOutputUtf16Units ||
  !result.output.startsWith(spec.beginMarker + "\\n") ||
  !result.output.endsWith(spec.expectedTail)
) {{
  text("AUTHORITY_BUNDLE_FAILED");
  exit();
}}
notify(result.output);
text("AUTHORITY_BUNDLE_COMPLETE nonce=" + spec.nonce);
```

After `AUTHORITY_BUNDLE_COMPLETE`, follow the acquired reviewer prompt exactly. Do not read any authority file again. Report-generation commands must use direct `exec_command`, never another outer `functions.exec`. Your final response must include the prompt-required `REVIEW_REPORT_PATH` line and `AUTHORITY_BUNDLE_COMPLETE: {nonce}`.
"""


def _cursor_prompt(spec, nonce):
    return f"""You are the independent ADR reviewer for `{REVIEW_MODE}`.

Your first authority-acquisition action must be one Terminal call running this exact command:

`{spec["cmd"]}`

If Cursor returns the complete Terminal output inline, inspect it directly. If and only if Cursor externalizes that Terminal result to a runtime-generated tool-output file, your next and only permitted authority-acquisition action is one Read of exactly the spill-file path returned by that Terminal result. Never read the manifest or any individual authority path.

Accept the inline or spill-file result only when the command succeeds, the output starts with `{spec["beginMarker"]}`, contains `{spec["endMarker"]}` after the complete role markers for reviewer_prompt, adr_format, context, and target_adr, and ends with the exact instruction `{spec["expectedTail"]}`. Otherwise stop and report `tool_failed`; do not retry, read another spill file, or read any authority separately.

After the complete bundle arrives, follow its reviewer_prompt exactly. Do not read any authority file again. Your final response must include the prompt-required `REVIEW_REPORT_PATH` line and `AUTHORITY_BUNDLE_COMPLETE: {nonce}`.
"""


def _claude_adapter(emit_command):
    argv = [
        "claude",
        "-p",
        "--model",
        "opus",
        "--effort",
        "high",
        "--permission-mode",
        "auto",
        "--tools",
        "Read",
        "Write",
        "Bash",
        "--allowedTools",
        "Read",
        "Write",
        "Bash",
    ]
    return {
        "command_argv": argv,
        "stdin_command": emit_command,
        "pipeline_command": (
            f"set -o pipefail; {emit_command} | {shlex.join(argv)}"
        ),
    }


def prepare_preflight_dispatch(
    *,
    runtime,
    target_adr_path,
    run_dir,
    integrity_marker=None,
):
    """Write common bundle metadata and return the selected runtime adapter."""
    if runtime not in _RUNTIME_POLICIES:
        raise ValueError(f"unsupported runtime: {runtime}")
    target_path = _resolve_file(target_adr_path, "target_adr")
    context_root = Path(derive_context_root(str(target_path)))
    adr_format_path = _resolve_file(_ADR_FORMAT_PATH, "adr_format")
    context_path = _resolve_file(context_root / "CONTEXT.md", "context")
    run_path = Path(run_dir).resolve()

    prompt_result = write_review_prompt_file(
        review_mode=REVIEW_MODE,
        placeholders={
            "review_mode": REVIEW_MODE,
            "target_adr_path": str(target_path),
            "adr_format_path": str(adr_format_path),
            "context_path": str(context_path),
            "bounded_context_reference_paths": str(context_root / "docs" / "adr"),
            "source_decision_extract_path_or_none": "none",
            "live_atomic_decision_corpus_path_or_none": "none",
        },
        run_dir=run_path,
        integrity_marker=integrity_marker,
    )
    prompt_path = _resolve_file(prompt_result["prompt_path"], "reviewer_prompt")
    _verify_prompt_authority_paths(
        prompt_path,
        {
            "adr_format": adr_format_path,
            "context": context_path,
            "target_adr": target_path,
        },
    )
    paths = {
        "reviewer_prompt": prompt_path,
        "adr_format": adr_format_path,
        "context": context_path,
        "target_adr": target_path,
    }
    authorities = [_authority_spec(role, paths[role]) for role in _AUTHORITY_ROLES]
    nonce = secrets.token_hex(16)
    manifest = {
        "schema_version": 1,
        "review_mode": REVIEW_MODE,
        "authority_bundle_nonce": nonce,
        "authorities": authorities,
    }
    manifest_path = run_path / _MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_sha256 = _sha256(manifest_path.read_bytes())
    emit_command = _emit_command(manifest_path, manifest_sha256)
    rendered = emit_bundle(
        manifest_path=manifest_path,
        expected_manifest_sha256=manifest_sha256,
    )
    begin, end = _bundle_markers(nonce)
    expected_tail = (
        f"{end}\n"
        f"Your final response must also include "
        f"`AUTHORITY_BUNDLE_COMPLETE: {nonce}`."
    )
    spec = {
        "cmd": emit_command,
        "expectedOutputUtf16Units": _utf16_units(rendered),
        "beginMarker": begin,
        "endMarker": end,
        "expectedTail": expected_tail,
        "maxOutputTokens": max(20000, len(rendered.encode("utf-8")) + 2048),
        "nonce": nonce,
    }

    policy = _RUNTIME_POLICIES[runtime]
    dispatch = {
        "runtime": runtime,
        "review_mode": REVIEW_MODE,
        "integrity_marker": prompt_result["integrity_marker"],
        "authority_bundle_nonce": nonce,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "prompt_path": str(prompt_path),
        "authorities": authorities,
        "model": policy["model"],
        "reasoning_effort": policy["reasoning_effort"],
        "fast_mode": False,
    }
    if runtime == "codex":
        dispatch.update(
            {
                "task_name": f"adr_preflight_{nonce[:12]}",
                "fork_turns": "none",
                "message": _codex_message(spec, nonce),
            }
        )
    elif runtime == "cursor":
        dispatch.update(
            {
                "subagent_type": "generalPurpose",
                "description": "Review ADR preflight",
                "prompt": _cursor_prompt(spec, nonce),
                "run_in_background": False,
                "readonly": False,
            }
        )
    else:
        dispatch.update(_claude_adapter(emit_command))

    dispatch_path = run_path / f"{runtime}_preflight_dispatch.json"
    dispatch["dispatch_path"] = str(dispatch_path)
    dispatch_path.write_text(
        json.dumps(dispatch, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dispatch


def _parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--runtime", required=True, choices=sorted(_RUNTIME_POLICIES))
    prepare.add_argument("--target-adr", required=True)
    prepare.add_argument("--run-dir", required=True)

    emit = subparsers.add_parser("emit")
    emit.add_argument("--manifest", required=True)
    emit.add_argument("--expected-manifest-sha256", required=True)
    return parser


def main(argv):
    args = _parser().parse_args(argv)
    if args.command == "prepare":
        result = prepare_preflight_dispatch(
            runtime=args.runtime,
            target_adr_path=args.target_adr,
            run_dir=args.run_dir,
        )
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
    else:
        sys.stdout.write(
            emit_bundle(
                manifest_path=args.manifest,
                expected_manifest_sha256=args.expected_manifest_sha256,
            )
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
