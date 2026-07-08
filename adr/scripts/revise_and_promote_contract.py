"""Mechanical revise-and-promote wrapper orchestration contract.

`revise-and-promote-draft-to-active` is the pre-promotion delivery-completion
wrapper: it calls `revise` with `frozen_glossary_quality_review`, and only when
`revise` reports `passed` does it call `promote-draft-to-active`. Any non-passed
terminal is returned as-is, leaving the draft in `draft/`. The promotion
operation's own unconditional-promotion contract is untouched — the gate is this
"promote only on passed" orchestration. Sub-operations are injected as callables,
mirroring the produce-for-HITL and revise contract designs. The wrapper keeps
only a thin report (this layer's status, sub-operation report paths, whether it
advanced, and the final handoff status).
"""

import json
from pathlib import Path

from revise_contract import FROZEN_GLOSSARY_QUALITY_REVIEW


OPERATION = "revise-and-promote-draft-to-active"
REPORT_FILENAME = "revise_and_promote_report.json"

FINAL_PROMOTED = "promoted"
HANDOFF_PROMOTED = "promoted_to_active"
HANDOFF_LEFT_IN_DRAFT = "left_in_draft"


def run_revise_and_promote(*, inputs, revise_fn, promote_fn, run_dir):
    draft_adr_path = inputs["draft_adr_path"]

    revise_result = revise_fn({
        "draft_adr_path": draft_adr_path,
        "quality_review_mode": FROZEN_GLOSSARY_QUALITY_REVIEW,
    })
    revise_final_status = revise_result["final_status"]
    revise_report_path = revise_result["structured_report_path"]

    if revise_final_status == "passed":
        promote_result = promote_fn({"draft_adr_path": draft_adr_path})
        return _finalize(
            run_dir,
            draft_adr_path=draft_adr_path,
            final_status=FINAL_PROMOTED,
            needs_user_ruling=False,
            revise_report_path=revise_report_path,
            advanced_to_promotion=True,
            promotion_report_path=promote_result["structured_report_path"],
            handoff_status=HANDOFF_PROMOTED,
        )

    # Any non-passed terminal: do not promote, leave the draft in place, and
    # return revise's terminal as-is.
    return _finalize(
        run_dir,
        draft_adr_path=draft_adr_path,
        final_status=revise_final_status,
        needs_user_ruling=revise_result["needs_user_ruling"],
        revise_report_path=revise_report_path,
        advanced_to_promotion=False,
        promotion_report_path=None,
        handoff_status=HANDOFF_LEFT_IN_DRAFT,
    )


def _finalize(
    run_dir,
    *,
    draft_adr_path,
    final_status,
    needs_user_ruling,
    revise_report_path,
    advanced_to_promotion,
    promotion_report_path,
    handoff_status,
):
    report = {
        "operation": OPERATION,
        "final_status": final_status,
        "draft_adr_path": draft_adr_path,
        "structured_report_path": None,
        "needs_user_ruling": needs_user_ruling,
        "revise_report_path": revise_report_path,
        "advanced_to_promotion": advanced_to_promotion,
        "promotion_report_path": promotion_report_path,
        "handoff_status": handoff_status,
    }
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / REPORT_FILENAME
    report["structured_report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"direct_output": _direct_output(report), "report": report}


def _direct_output(report):
    return {
        "draft_adr_path": report["draft_adr_path"],
        "structured_report_path": report["structured_report_path"],
        "final_status": report["final_status"],
        "needs_user_ruling": report["needs_user_ruling"],
    }
