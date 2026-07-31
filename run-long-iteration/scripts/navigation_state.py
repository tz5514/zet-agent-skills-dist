#!/usr/bin/env python3
"""Validate, read, and CAS-commit a long-iteration campaign checkpoint."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import uuid


SCHEMA_VERSION = 1
CAMPAIGN_ID_PLACEHOLDER = "replace-with-stable-id"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRANSACTION_RE = re.compile(r"^[0-9a-f]{32}$")
STATUSES = {"running", "paused", "blocked", "converged", "cancelled", "exhausted"}
TERMINAL_STATUSES = {"converged", "cancelled", "exhausted"}
ROUND_STATUSES = {"none", "planned", "running", "evaluated", "closed"}
ROUND_TRANSITIONS = {
    "none": {"none", "planned"},
    "planned": {"planned", "running"},
    "running": {"running", "evaluated"},
    "evaluated": {"evaluated", "closed"},
    "closed": {"closed", "planned"},
}
VERDICTS = {None, "promote", "reject", "repeat_same_conditions", "invalid_run"}
ACTION_TYPES = {
    "complete_contract",
    "seal_baseline",
    "plan_round",
    "execute_round",
    "evaluate_round",
    "close_round",
    "repeat_round",
    "evaluate_stop",
    "resume",
    "recover",
    "none",
}


class StateError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StateError(message)


def _load_json(path: Path) -> dict:
    def reject_constant(value: str) -> None:
        raise StateError(f"{path} contains non-finite number {value}")

    def reject_duplicate_members(pairs: list[tuple[str, object]]) -> dict:
        value: dict = {}
        for key, item in pairs:
            _require(key not in value, f"{path} contains duplicate JSON member {key}")
            value[key] = item
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_members,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"cannot read JSON {path}: {exc}") from exc
    _require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise StateError(f"cannot read {path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _absolute_path(value: object, field: str) -> Path:
    _require(isinstance(value, str) and value, f"{field} must be a non-empty string")
    path = Path(value)
    _require(path.is_absolute(), f"{field} must be absolute")
    return path


def _validate_ref(value: object, field: str, *, required: bool = False, verify: bool = False) -> dict | None:
    if value is None:
        _require(not required, f"{field} is required")
        return None
    _require(isinstance(value, dict), f"{field} must be an artifact ref")
    _require(set(value) == {"path", "sha256"}, f"{field} fields are invalid")
    path = _absolute_path(value["path"], f"{field}.path")
    _require(isinstance(value["sha256"], str) and SHA256_RE.fullmatch(value["sha256"]), f"{field}.sha256 is invalid")
    if verify:
        _require(path.is_file(), f"{field}.path does not exist")
        _require(_sha256_file(path) == value["sha256"], f"{field}.sha256 mismatch")
    return value


def _validate_action(value: object) -> dict:
    _require(isinstance(value, dict), "next_action must be an object")
    _require(set(value) == {"type", "description"}, "next_action fields are invalid")
    _require(value["type"] in ACTION_TYPES, "next_action.type is invalid")
    _require(isinstance(value["description"], str) and value["description"].strip(), "next_action.description is required")
    return value


def _validate_contract(value: object) -> None:
    _require(isinstance(value, dict), "contract must be an object")
    required = {
        "complete",
        "objective",
        "final_deliverable",
        "metric_priority",
        "hard_gate",
        "allowed_variable",
        "frozen_surfaces",
        "valid_run_criteria",
        "promotion_criteria",
        "rollback_criteria",
        "audit_policy",
        "retry_limit",
        "search_budget",
        "stop_conditions",
        "execution_mode",
    }
    _require(set(value) == required, "contract fields are invalid")
    _require(isinstance(value["complete"], bool), "contract.complete must be boolean")
    for field in (
        "objective",
        "final_deliverable",
        "hard_gate",
        "allowed_variable",
        "valid_run_criteria",
        "promotion_criteria",
        "rollback_criteria",
        "audit_policy",
    ):
        _require(isinstance(value[field], str), f"contract.{field} must be a string")
        if value["complete"]:
            _require(value[field].strip(), f"contract.{field} is required")
    for field in ("metric_priority", "frozen_surfaces", "stop_conditions"):
        _require(
            isinstance(value[field], list)
            and all(isinstance(item, str) and item.strip() for item in value[field]),
            f"contract.{field} must be a string list",
        )
        if value["complete"]:
            _require(value[field], f"contract.{field} must not be empty")
    _require(type(value["retry_limit"]) is int and value["retry_limit"] >= 0, "retry_limit is invalid")
    budget = value["search_budget"]
    _require(
        isinstance(budget, dict)
        and set(budget) == {"unit", "limit"}
        and isinstance(budget["unit"], str)
        and budget["unit"].strip()
        and type(budget["limit"]) in {int, float}
        and math.isfinite(budget["limit"])
        and budget["limit"] > 0,
        "search_budget is invalid",
    )
    _require(value["execution_mode"] in {"serial", "wave"}, "execution_mode is invalid")


def _validate_promotion(value: object, *, verify: bool) -> None:
    _require(isinstance(value, dict), "promotion_evidence must be an object")
    required = {
        "candidate_sha256",
        "previous_baseline_sha256",
        "regression",
        "audit_event_key",
        "findings_report",
        "all_findings_closed",
    }
    _require(set(value) == required, "promotion_evidence fields are invalid")
    for field in ("candidate_sha256", "previous_baseline_sha256"):
        _require(isinstance(value[field], str) and SHA256_RE.fullmatch(value[field]), f"promotion_evidence.{field} is invalid")
    _validate_ref(value["regression"], "promotion_evidence.regression", required=True, verify=verify)
    _require(
        value["audit_event_key"] is None
        or (isinstance(value["audit_event_key"], str) and value["audit_event_key"].strip()),
        "promotion_evidence.audit_event_key is invalid",
    )
    _validate_ref(value["findings_report"], "promotion_evidence.findings_report", required=value["audit_event_key"] is not None, verify=verify)
    _require(value["all_findings_closed"] is True, "promotion findings are not closed")
    if value["audit_event_key"] is None:
        _require(value["findings_report"] is None, "promotion without an audit event cannot have findings_report")


def _validate_state(state: dict, *, previous: dict | None = None, previous_path: Path | None = None, verify: bool = False) -> None:
    required = {
        "schema_version",
        "campaign_id",
        "revision",
        "transaction_id",
        "previous_state_path",
        "previous_state_sha256",
        "status",
        "contract",
        "contract_sha256",
        "baseline",
        "current_round",
        "progress",
        "next_action",
        "checkpoint",
    }
    _require(set(state) == required, "state fields are invalid")
    _require(
        type(state["schema_version"]) is int and state["schema_version"] == SCHEMA_VERSION,
        "unsupported schema_version",
    )
    _require(isinstance(state["campaign_id"], str) and state["campaign_id"].strip(), "campaign_id is required")
    _require(type(state["revision"]) is int and state["revision"] >= 0, "revision is invalid")
    _require(
        state["transaction_id"] is None
        or (isinstance(state["transaction_id"], str) and TRANSACTION_RE.fullmatch(state["transaction_id"])),
        "transaction_id is invalid",
    )
    if state["revision"] == 0:
        _require(state["previous_state_path"] is None, "initial previous_state_path must be null")
        _require(state["previous_state_sha256"] is None, "initial previous_state_sha256 must be null")
    else:
        _absolute_path(state["previous_state_path"], "previous_state_path")
        _require(
            isinstance(state["previous_state_sha256"], str)
            and SHA256_RE.fullmatch(state["previous_state_sha256"]),
            "previous_state_sha256 is invalid",
        )
    _require(state["status"] in STATUSES, "status is invalid")
    _validate_contract(state["contract"])
    if state["contract"]["complete"]:
        _require(state["contract_sha256"] == _canonical_hash(state["contract"]), "contract_sha256 mismatch")
    else:
        _require(state["contract_sha256"] is None, "incomplete contract must not have contract_sha256")

    baseline = state["baseline"]
    _require(
        isinstance(baseline, dict)
        and set(baseline) == {"id", "artifact", "evidence", "rollback"},
        "baseline fields are invalid",
    )
    if baseline["id"] is None:
        for field in ("artifact", "evidence", "rollback"):
            _require(baseline[field] is None, f"unsealed baseline {field} must be null")
    else:
        _require(isinstance(baseline["id"], str) and baseline["id"].strip(), "baseline.id is invalid")
        for field in ("artifact", "evidence", "rollback"):
            _validate_ref(baseline[field], f"baseline.{field}", required=True, verify=verify)
        _require(state["contract"]["complete"], "sealed baseline requires complete contract")

    round_state = state["current_round"]
    round_fields = {
        "id",
        "status",
        "hypothesis",
        "changed_surface",
        "repeat_of",
        "candidate_artifact",
        "condition_packet",
        "execution_packet",
        "result_packet",
        "verdict",
        "promotion_evidence",
    }
    _require(isinstance(round_state, dict) and set(round_state) == round_fields, "current_round fields are invalid")
    _require(round_state["status"] in ROUND_STATUSES, "current_round.status is invalid")
    _require(round_state["verdict"] in VERDICTS, "current_round.verdict is invalid")
    if round_state["status"] != "none":
        _require(state["contract"]["complete"], "active round requires complete contract")
        _require(baseline["id"] is not None, "active round requires sealed baseline")
    if round_state["status"] == "none":
        for field in round_fields - {"status"}:
            _require(round_state[field] is None, f"inactive round {field} must be null")
    else:
        for field in ("id", "hypothesis", "changed_surface"):
            _require(isinstance(round_state[field], str) and round_state[field].strip(), f"current_round.{field} is required")
        _require(round_state["changed_surface"] == state["contract"]["allowed_variable"], "round changed_surface differs from contract")
        for field in ("candidate_artifact", "condition_packet", "execution_packet"):
            _validate_ref(round_state[field], f"current_round.{field}", required=True, verify=verify)
        repeat_of = round_state["repeat_of"]
        if repeat_of is not None:
            _require(
                isinstance(repeat_of, dict)
                and set(repeat_of) == {"round_id", "execution_sha256", "result_sha256"},
                "current_round.repeat_of fields are invalid",
            )
            _require(
                isinstance(repeat_of["round_id"], str) and repeat_of["round_id"].strip(),
                "current_round.repeat_of.round_id is invalid",
            )
            for field in ("execution_sha256", "result_sha256"):
                _require(
                    isinstance(repeat_of[field], str) and SHA256_RE.fullmatch(repeat_of[field]),
                    f"current_round.repeat_of.{field} is invalid",
                )
            _require(
                round_state["execution_packet"]["sha256"] != repeat_of["execution_sha256"],
                "repeat requires new execution content",
            )
    if round_state["status"] in {"evaluated", "closed"}:
        _validate_ref(round_state["result_packet"], "current_round.result_packet", required=True, verify=verify)
        _require(round_state["verdict"] is not None, "evaluated round requires verdict")
        if round_state["repeat_of"] is not None:
            _require(
                round_state["result_packet"]["sha256"] != round_state["repeat_of"]["result_sha256"],
                "repeat requires new result content",
            )
    else:
        _require(round_state["result_packet"] is None, "unevaluated round result_packet must be null")
        _require(round_state["verdict"] is None, "unevaluated round verdict must be null")
    if round_state["verdict"] == "promote":
        _validate_promotion(round_state["promotion_evidence"], verify=verify)
        _require(
            round_state["promotion_evidence"]["candidate_sha256"]
            == round_state["candidate_artifact"]["sha256"],
            "promotion candidate does not match candidate artifact",
        )
        if round_state["status"] == "evaluated":
            _require(
                round_state["promotion_evidence"]["previous_baseline_sha256"]
                == baseline["artifact"]["sha256"],
                "promotion previous baseline mismatch",
            )
    else:
        _require(round_state["promotion_evidence"] is None, "promotion_evidence is only valid for promote")

    progress = state["progress"]
    _require(
        isinstance(progress, dict)
        and set(progress) == {"completed_rounds", "invalid_runs", "rejected_directions"},
        "progress fields are invalid",
    )
    for field, value in progress.items():
        _require(type(value) is int and value >= 0, f"progress.{field} is invalid")

    action = _validate_action(state["next_action"])
    checkpoint = state["checkpoint"]
    _require(
        isinstance(checkpoint, dict)
        and set(checkpoint)
        == {
            "summary",
            "open_risks",
            "resume_condition",
            "suspended_next_action",
            "active_worker_ids",
            "history_index",
            "completion_evidence",
        },
        "checkpoint fields are invalid",
    )
    _require(isinstance(checkpoint["summary"], str), "checkpoint.summary must be a string")
    _require(isinstance(checkpoint["open_risks"], list), "checkpoint.open_risks must be a list")
    _require(
        isinstance(checkpoint["active_worker_ids"], list)
        and all(isinstance(item, str) and item for item in checkpoint["active_worker_ids"]),
        "active_worker_ids is invalid",
    )
    _require(
        len(checkpoint["active_worker_ids"]) == len(set(checkpoint["active_worker_ids"])),
        "active_worker_ids contains duplicates",
    )
    if checkpoint["active_worker_ids"]:
        _require(
            round_state["status"] in {"planned", "running"},
            "active workers require a current executable round",
        )
    _require(
        all(isinstance(item, str) and item.strip() for item in checkpoint["open_risks"]),
        "checkpoint.open_risks must contain strings",
    )
    _validate_ref(checkpoint["history_index"], "checkpoint.history_index", verify=verify)
    _validate_ref(
        checkpoint["completion_evidence"],
        "checkpoint.completion_evidence",
        required=state["status"] in TERMINAL_STATUSES,
        verify=verify,
    )
    suspended_action = checkpoint["suspended_next_action"]
    if state["status"] in {"paused", "blocked"}:
        suspended_action = _validate_action(suspended_action)
        _require(
            suspended_action["type"] not in {"none", "resume", "recover"},
            "suspended_next_action must be a running action",
        )
    else:
        _require(suspended_action is None, "suspended_next_action is only valid while paused or blocked")
    if state["status"] in {"paused", "blocked"}:
        _require(
            isinstance(checkpoint["resume_condition"], str)
            and checkpoint["resume_condition"].strip(),
            f"{state['status']} requires resume_condition",
        )
    else:
        _require(checkpoint["resume_condition"] is None, "resume_condition is only valid while paused or blocked")
    if state["status"] in TERMINAL_STATUSES:
        _require(action["type"] == "none", "terminal status requires next_action none")
        _require(not checkpoint["active_worker_ids"], "terminal status requires all workers closed")
        if state["status"] in {"converged", "exhausted"}:
            _require(round_state["status"] in {"none", "closed"}, "completed campaign requires no in-flight round")
            _require(state["contract"]["complete"], "completed campaign requires complete contract")
            _require(baseline["id"] is not None, "completed campaign requires sealed baseline")
    elif state["status"] == "paused":
        _require(action["type"] == "resume", "paused status requires resume action")
    elif state["status"] == "blocked":
        _require(action["type"] == "recover", "blocked status requires recover action")
    else:
        _require(action["type"] not in {"none", "resume", "recover"}, "running status requires executable next action")

    if state["status"] == "running":
        if not state["contract"]["complete"]:
            allowed_actions = {"complete_contract"}
        elif baseline["id"] is None:
            allowed_actions = {"seal_baseline"}
        elif round_state["status"] == "none":
            allowed_actions = {"plan_round", "evaluate_stop"}
        elif round_state["status"] == "planned":
            allowed_actions = {"execute_round"}
        elif round_state["status"] == "running":
            allowed_actions = {"evaluate_round"}
        elif round_state["status"] == "evaluated":
            allowed_actions = {"close_round"}
        elif round_state["verdict"] == "repeat_same_conditions":
            allowed_actions = {"repeat_round", "evaluate_stop"}
        else:
            allowed_actions = {"plan_round", "evaluate_stop"}
        _require(action["type"] in allowed_actions, "next_action is incompatible with campaign state")
        if action["type"] == "evaluate_stop":
            _require(round_state["status"] in {"none", "closed"}, "evaluate_stop requires no in-flight round")
            _require(not checkpoint["active_worker_ids"], "evaluate_stop requires all workers closed")
            _require(checkpoint["completion_evidence"] is not None, "evaluate_stop requires completion_evidence")
        else:
            _require(checkpoint["completion_evidence"] is None, "completion_evidence is only valid while evaluating stop")

    if previous is None:
        _require(state["revision"] == 0, "initial revision must be 0")
        _require(state["status"] == "running", "initial status must be running")
        _require(round_state["status"] == "none", "initial state cannot contain a round")
        _require(
            progress == {"completed_rounds": 0, "invalid_runs": 0, "rejected_directions": 0},
            "initial progress must be zero",
        )
        return

    _require(previous_path is not None, "previous_path is required")
    _require(previous["status"] not in TERMINAL_STATUSES, "terminal campaign cannot transition")
    _require(state["campaign_id"] == previous["campaign_id"], "campaign_id cannot change")
    _require(state["revision"] == previous["revision"] + 1, "revision must increase by one")
    _require(state["previous_state_path"] == str(previous_path.resolve()), "previous_state_path mismatch")
    _require(state["previous_state_sha256"] == _sha256_file(previous_path), "previous_state_sha256 mismatch")
    if previous["contract"]["complete"]:
        _require(state["contract"] == previous["contract"], "complete contract cannot drift")
        _require(state["contract_sha256"] == previous["contract_sha256"], "contract hash cannot drift")

    old_round = previous["current_round"]
    _require(round_state["status"] in ROUND_TRANSITIONS[old_round["status"]], f"illegal round transition {old_round['status']}->{round_state['status']}")
    if old_round["status"] in {"planned", "running", "evaluated"}:
        _require(round_state["id"] == old_round["id"], "active round id cannot change")
    if old_round["status"] == "closed" and round_state["status"] == "closed":
        _require(round_state["id"] == old_round["id"], "closed round cannot be replaced")
    if old_round["id"] == round_state["id"] and old_round["status"] != "none":
        for field in (
            "id",
            "hypothesis",
            "changed_surface",
            "repeat_of",
            "candidate_artifact",
            "condition_packet",
            "execution_packet",
        ):
            _require(round_state[field] == old_round[field], f"current_round.{field} cannot drift")
        if old_round["status"] == "closed":
            _require(round_state == old_round, "closed round cannot be rewritten")
        if old_round["status"] == "evaluated":
            for field in ("result_packet", "verdict", "promotion_evidence"):
                _require(round_state[field] == old_round[field], f"evaluated current_round.{field} cannot drift")
    elif round_state["status"] == "planned":
        _require(old_round["status"] in {"none", "closed"}, "new round requires no active round")
        _require(
            not previous["checkpoint"]["active_worker_ids"]
            and not checkpoint["active_worker_ids"],
            "new round requires all previous workers closed",
        )
        if old_round["status"] == "closed" and old_round["verdict"] == "repeat_same_conditions":
            _require(round_state["hypothesis"] == old_round["hypothesis"], "repeat must preserve hypothesis")
            _require(
                round_state["candidate_artifact"] == old_round["candidate_artifact"],
                "repeat must preserve candidate artifact",
            )
            _require(
                round_state["condition_packet"] == old_round["condition_packet"],
                "repeat must preserve condition packet",
            )
            _require(
                round_state["repeat_of"]
                == {
                    "round_id": old_round["id"],
                    "execution_sha256": old_round["execution_packet"]["sha256"],
                    "result_sha256": old_round["result_packet"]["sha256"],
                },
                "repeat provenance does not match source round",
            )
        else:
            _require(round_state["repeat_of"] is None, "non-repeat round cannot have repeat provenance")

    closed_now = old_round["status"] == "evaluated" and round_state["status"] == "closed"
    expected_progress = dict(previous["progress"])
    if closed_now:
        expected_progress["completed_rounds"] += 1
        if round_state["verdict"] == "invalid_run":
            expected_progress["invalid_runs"] += 1
        if round_state["verdict"] == "reject":
            expected_progress["rejected_directions"] += 1
    _require(progress == expected_progress, "progress does not match the round transition")

    old_baseline = previous["baseline"]
    if old_baseline["id"] is None and baseline["id"] is not None:
        _require(state["contract"]["complete"], "initial baseline requires complete contract")
        _require(round_state["status"] == "none", "initial baseline requires no active round")
    elif baseline != old_baseline:
        _require(old_baseline["id"] is not None, "baseline replacement requires existing baseline")
        _require(baseline["id"] is not None, "sealed baseline cannot be removed")
        _require(round_state["status"] == "closed" and round_state["verdict"] == "promote", "baseline replacement requires closed promote round")
        promotion = round_state["promotion_evidence"]
        _require(promotion["previous_baseline_sha256"] == old_baseline["artifact"]["sha256"], "promotion previous baseline mismatch")
        _require(baseline["artifact"]["sha256"] == promotion["candidate_sha256"], "promoted baseline candidate mismatch")
        _require(baseline["evidence"] == promotion["regression"], "baseline evidence must be promotion regression")
        _require(baseline["rollback"] == old_baseline["artifact"], "baseline rollback must be previous artifact")
    if closed_now and round_state["verdict"] == "promote":
        _require(baseline != old_baseline, "closing a promoted round must replace baseline")

    old_status = previous["status"]
    old_completion = previous["checkpoint"]["completion_evidence"]
    new_completion = checkpoint["completion_evidence"]
    if state["status"] == "cancelled":
        _require(new_completion is not None, "cancellation requires completion_evidence")
        if old_completion is not None:
            _require(
                new_completion["sha256"] != old_completion["sha256"],
                "cancellation requires a new cancellation evidence artifact",
            )
    elif old_completion is not None:
        _require(
            new_completion == old_completion,
            "completion_evidence cannot be removed or replaced",
        )
    elif new_completion is not None:
        _require(
            old_status == "running"
            and state["status"] == "running"
            and action["type"] == "evaluate_stop"
            and round_state["status"] in {"none", "closed"}
            and not checkpoint["active_worker_ids"],
            "completion_evidence can only be introduced for stop evaluation or cancellation",
        )
    if old_status in {"paused", "blocked"}:
        _require(
            state["status"] in {old_status, "running", "cancelled"},
            f"{old_status} campaign can only wait, resume, or cancel",
        )
        if state["status"] != "cancelled":
            for field in ("contract", "baseline", "current_round", "progress"):
                _require(state[field] == previous[field], f"{old_status} transition cannot change {field}")
        if state["status"] == old_status:
            _require(
                checkpoint["suspended_next_action"]
                == previous["checkpoint"]["suspended_next_action"],
                "suspended next action cannot drift",
            )
        elif state["status"] == "running":
            _require(
                action == previous["checkpoint"]["suspended_next_action"],
                "resume must restore suspended next action",
            )
            for field in ("active_worker_ids", "history_index", "completion_evidence"):
                _require(
                    checkpoint[field] == previous["checkpoint"][field],
                    f"resume cannot change checkpoint.{field}",
                )
    if state["status"] in {"paused", "blocked"}:
        _require(old_status in {"running", state["status"]}, f"cannot enter {state['status']} from {old_status}")
        for field in ("contract", "baseline", "current_round", "progress"):
            _require(state[field] == previous[field], f"entering {state['status']} cannot change {field}")
        if old_status == "running":
            _require(
                checkpoint["suspended_next_action"] == previous["next_action"],
                "suspension must preserve the committed next action",
            )
            for field in ("history_index", "completion_evidence"):
                _require(
                    checkpoint[field] == previous["checkpoint"][field],
                    f"suspension cannot change checkpoint.{field}",
                )

    if state["status"] == "cancelled":
        for field in ("contract", "baseline", "current_round", "progress"):
            _require(state[field] == previous[field], f"cancellation cannot change {field}")

    if old_status == "running" and state["status"] == "running":
        consumed_actions: list[str] = []
        if not previous["contract"]["complete"] and state["contract"]["complete"]:
            consumed_actions.append("complete_contract")
        if old_baseline["id"] is None and baseline["id"] is not None:
            consumed_actions.append("seal_baseline")
        if old_round["id"] != round_state["id"] and round_state["status"] == "planned":
            consumed_actions.append(
                "repeat_round" if old_round["verdict"] == "repeat_same_conditions" else "plan_round"
            )
        elif old_round["status"] != round_state["status"]:
            consumed_actions.append(
                {
                    ("planned", "running"): "execute_round",
                    ("running", "evaluated"): "evaluate_round",
                    ("evaluated", "closed"): "close_round",
                }[(old_round["status"], round_state["status"])]
            )
        consumed_actions = sorted(set(consumed_actions))
        if consumed_actions:
            _require(len(consumed_actions) == 1, "one commit cannot consume multiple next actions")
            _require(
                previous["next_action"]["type"] == consumed_actions[0],
                "state transition does not consume the committed next_action",
            )
        else:
            prepares_stop = (
                previous["next_action"]["type"] in {"plan_round", "repeat_round"}
                and action["type"] == "evaluate_stop"
                and old_round["status"] in {"none", "closed"}
                and round_state == old_round
                and state["contract"] == previous["contract"]
                and baseline == old_baseline
                and progress == previous["progress"]
                and not previous["checkpoint"]["active_worker_ids"]
                and not checkpoint["active_worker_ids"]
                and previous["checkpoint"]["completion_evidence"] is None
                and checkpoint["completion_evidence"] is not None
                and checkpoint["history_index"] == previous["checkpoint"]["history_index"]
            )
            if not prepares_stop:
                _require(
                    state["next_action"] == previous["next_action"],
                    "next_action cannot change without a corresponding state transition",
                )

    if state["status"] in {"converged", "exhausted"}:
        _require(previous["status"] == "running", "terminal completion requires running predecessor")
        _require(previous["next_action"]["type"] == "evaluate_stop", "terminal completion requires evaluate_stop action")
        _require(round_state == old_round, "terminal completion cannot clear or rewrite current round")
        _require(
            checkpoint["completion_evidence"] == previous["checkpoint"]["completion_evidence"],
            "terminal completion evidence must match evaluate_stop checkpoint",
        )


def _atomic_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp_path, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _exclusive_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        try:
            os.link(temp_path, path)
        except FileExistsError as exc:
            raise StateError(f"immutable revision already exists: {path}") from exc
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _read_locator(path: Path) -> tuple[dict, Path, dict]:
    locator = _load_json(path)
    _require(
        set(locator) == {"schema_version", "campaign_id", "revision", "state_path", "state_sha256"},
        "locator fields are invalid",
    )
    _require(
        type(locator["schema_version"]) is int and locator["schema_version"] == SCHEMA_VERSION,
        "unsupported locator schema",
    )
    _require(
        isinstance(locator["campaign_id"], str) and locator["campaign_id"].strip(),
        "locator campaign_id is invalid",
    )
    _require(type(locator["revision"]) is int and locator["revision"] >= 0, "locator revision is invalid")
    _require(
        isinstance(locator["state_sha256"], str) and SHA256_RE.fullmatch(locator["state_sha256"]),
        "locator state_sha256 is invalid",
    )
    state_path = _absolute_path(locator["state_path"], "locator.state_path")
    _require(state_path.is_file(), "locator state does not exist")
    _require(_sha256_file(state_path) == locator["state_sha256"], "locator state hash mismatch")
    state = _load_json(state_path)
    _require(state["campaign_id"] == locator["campaign_id"], "locator campaign mismatch")
    _require(state["revision"] == locator["revision"], "locator revision mismatch")
    previous = None
    previous_path = None
    if state["revision"] > 0:
        previous_path = _absolute_path(state["previous_state_path"], "previous_state_path")
        _require(previous_path.is_file(), "previous state does not exist")
        previous = _load_json(previous_path)
    _validate_state(state, previous=previous, previous_path=previous_path, verify=True)
    return locator, state_path, state


def command_begin(args: argparse.Namespace) -> None:
    result = {"transaction_id": uuid.uuid4().hex}
    locator_path = Path(args.locator).resolve()
    if locator_path.exists():
        locator, _, _ = _read_locator(locator_path)
        result["expected_revision"] = locator["revision"]
        result["expected_state_sha256"] = locator["state_sha256"]
    else:
        result["expected_revision"] = -1
        result["expected_state_sha256"] = None
    print(json.dumps(result, sort_keys=True))


def command_read(args: argparse.Namespace) -> None:
    locator, state_path, state = _read_locator(Path(args.locator).resolve())
    if args.json:
        print(
            json.dumps(
                {
                    "campaign_id": locator["campaign_id"],
                    "revision": locator["revision"],
                    "state_path": str(state_path),
                    "state_sha256": locator["state_sha256"],
                    "status": state["status"],
                    "next_action": state["next_action"],
                    "resume_condition": state["checkpoint"]["resume_condition"],
                },
                sort_keys=True,
            )
        )
    else:
        print(state_path)


def command_validate(args: argparse.Namespace) -> None:
    state_path = Path(args.state).resolve()
    state = _load_json(state_path)
    previous = None
    previous_path = None
    if args.previous:
        previous_path = Path(args.previous).resolve()
        previous = _load_json(previous_path)
    _validate_state(state, previous=previous, previous_path=previous_path, verify=args.verify_artifacts)
    print(state_path)


def command_artifact_ref(args: argparse.Namespace) -> None:
    path = Path(args.path).resolve()
    _require(path.is_file(), "artifact path does not exist")
    print(json.dumps({"path": str(path), "sha256": _sha256_file(path)}, sort_keys=True))


def command_contract_hash(args: argparse.Namespace) -> None:
    state = _load_json(Path(args.state).resolve())
    _validate_contract(state.get("contract"))
    _require(state["contract"]["complete"], "contract is incomplete")
    print(_canonical_hash(state["contract"]))


def command_publish_receipt(args: argparse.Namespace) -> None:
    value = _load_json(Path(args.source).resolve())
    output = Path(args.out).resolve()
    _exclusive_write(output, value)
    print(json.dumps({"path": str(output), "sha256": _sha256_file(output)}, sort_keys=True))


def command_commit(args: argparse.Namespace) -> None:
    locator_path = Path(args.locator).resolve()
    revisions_dir = Path(args.revisions_dir).resolve()
    expected_hash = None if args.expected_state_sha256 == "none" else args.expected_state_sha256
    _require(
        (args.expected_revision == -1 and expected_hash is None)
        or (
            args.expected_revision >= 0
            and isinstance(expected_hash, str)
            and SHA256_RE.fullmatch(expected_hash)
        ),
        "expected revision and hash are inconsistent",
    )
    _require(TRANSACTION_RE.fullmatch(args.transaction_id) is not None, "transaction_id is invalid")
    locator_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = locator_path.with_name(f".{locator_path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        previous = None
        previous_path = None
        if locator_path.exists():
            locator, previous_path, previous = _read_locator(locator_path)
            _require(locator["revision"] == args.expected_revision, "stale transaction: revision changed")
            _require(locator["state_sha256"] == expected_hash, "stale transaction: state hash changed")
        else:
            _require(args.expected_revision == -1 and expected_hash is None, "stale transaction: locator changed")
        staged = _load_json(Path(args.staged).resolve())
        if previous is None:
            _require(staged["revision"] == 0, "new campaign staged revision must be 0")
            _require(staged["transaction_id"] is None, "new campaign staged transaction_id must be null")
            _require(staged["previous_state_path"] is None, "new campaign staged previous_state_path must be null")
            _require(staged["previous_state_sha256"] is None, "new campaign staged previous_state_sha256 must be null")
            _require(staged["campaign_id"] != CAMPAIGN_ID_PLACEHOLDER, "replace the campaign_id placeholder before commit")
        else:
            for field in (
                "campaign_id",
                "revision",
                "transaction_id",
                "previous_state_path",
                "previous_state_sha256",
            ):
                _require(staged.get(field) == previous[field], f"staged {field} does not match current head")
        state = copy.deepcopy(staged)
        if previous is None:
            state["revision"] = 0
            state["previous_state_path"] = None
            state["previous_state_sha256"] = None
        else:
            state["campaign_id"] = previous["campaign_id"]
            state["revision"] = previous["revision"] + 1
            state["previous_state_path"] = str(previous_path)
            state["previous_state_sha256"] = _sha256_file(previous_path)
        state["transaction_id"] = args.transaction_id
        _validate_state(state, previous=previous, previous_path=previous_path, verify=True)
        revisions_dir.mkdir(parents=True, exist_ok=True)
        state_path = revisions_dir / f"state-{state['revision']:08d}-{args.transaction_id}.json"
        _exclusive_write(state_path, state)
        locator = {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": state["campaign_id"],
            "revision": state["revision"],
            "state_path": str(state_path),
            "state_sha256": _sha256_file(state_path),
        }
        _atomic_write(locator_path, locator)
        print(state_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("begin")
    begin.add_argument("--locator", required=True)
    begin.set_defaults(func=command_begin)
    read = commands.add_parser("read")
    read.add_argument("--locator", required=True)
    read.add_argument("--json", action="store_true")
    read.set_defaults(func=command_read)
    validate = commands.add_parser("validate")
    validate.add_argument("--state", required=True)
    validate.add_argument("--previous")
    validate.add_argument("--verify-artifacts", action="store_true")
    validate.set_defaults(func=command_validate)
    artifact_ref = commands.add_parser("artifact-ref")
    artifact_ref.add_argument("--path", required=True)
    artifact_ref.set_defaults(func=command_artifact_ref)
    contract_hash = commands.add_parser("contract-hash")
    contract_hash.add_argument("--state", required=True)
    contract_hash.set_defaults(func=command_contract_hash)
    publish_receipt = commands.add_parser("publish-receipt")
    publish_receipt.add_argument("--source", required=True)
    publish_receipt.add_argument("--out", required=True)
    publish_receipt.set_defaults(func=command_publish_receipt)
    commit = commands.add_parser("commit")
    commit.add_argument("--staged", required=True)
    commit.add_argument("--locator", required=True)
    commit.add_argument("--revisions-dir", required=True)
    commit.add_argument("--transaction-id", required=True)
    commit.add_argument("--expected-revision", required=True, type=int)
    commit.add_argument("--expected-state-sha256", required=True)
    commit.set_defaults(func=command_commit)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except StateError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
