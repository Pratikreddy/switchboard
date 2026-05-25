"""Deterministic brick accounting for Switchboard-managed suites.

Agents provide only compact semantic brick rows. This module computes the
repeatable factual fields from git, package metadata, and generated projections.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BRICS_TOOL_VERSION = "2026-05-25"
BRICK_ENTRY_COLUMNS = ("brick_id", "family", "mode", "status", "source_record", "next_action")

BRICK_CONTRACT: dict[str, Any] = {
    "name": "switchboard-brics",
    "contract_version": BRICS_TOOL_VERSION,
    "schema_version": "switchboard-brick-registry-v0",
    "input_format": "brick_id | family | mode | status | source_record | next_action",
    "human_fields": list(BRICK_ENTRY_COLUMNS),
    "computed_fields": [
        "contract_version",
        "serial_number",
        "date_created",
        "generated",
        "commit",
        "commit_subject",
        "version_introduced",
        "files_changed",
        "insertions",
        "deletions",
        "net_lines",
        "active_lines_after",
        "stale_lines_after",
    ],
    "function_contracts": {
        "normalize_brick_lines": {
            "input": "list[str] from `Brick Entries:` ledger lines",
            "output": "list[dict] with only sanitized semantic brick fields",
        },
        "build_brick_registry": {
            "input": "project_root, service_id, parsed task ledger rows, optional foundation projection",
            "output": "`switchboard/evidence/brick-registry.json` payload",
        },
        "switchboard.hooks.build_context_packet": {
            "input": "agent, cwd, task, budget",
            "output": "compact hook-injected prompt context with source refs and no raw prompt text",
        },
        "switchboard.hooks.capture_user_prompt": {
            "input": "exact UserPromptSubmit text, agent, cwd, source metadata",
            "output": "local-private timeline row plus git-safe hash/ref summary",
        },
    },
}

BENCHMARK_KEYWORD_CONTRACT: dict[str, Any] = {
    "name": "benchmark-keywords",
    "role": "expensive_agent_to_small_model_transfer",
    "keyword_id_format": "kw_<slug>_<4_digit_serial>",
    "bucket_id_format": "bucket_<slug>_<4_digit_serial>",
    "human_fields": [
        "keyword_id",
        "label",
        "plain_meaning",
        "bucket_id",
        "similar_bucket_ids",
        "status",
        "human_verified",
    ],
    "computed_fields": [
        "keyword_count",
        "bucket_count",
        "similar_bucket_count",
        "created_at",
        "updated_at",
        "source_benchmark_ids",
    ],
    "workflow": [
        "Expensive Pro agent keywords a benchmark set first.",
        "Human performs quick verification before labels become active.",
        "Smaller model receives only the verified keyword ID map, simple prompt, and examples.",
        "Existing tags are candidate evidence, not automatic truth.",
        "New suggestions stay pending until human verification promotes them.",
    ],
    "pdf_rule": "PDF or human-facing output must be simple, nontechnical, and grouped by verified keyword IDs and bucket counts.",
}

BENCHMARK_KEYWORD_RULES = [
    "Benchmark keywording is a separate semantic brick: expensive Pro agent suggests labels, but stable IDs and counts are managed programmatically.",
    "Each keyword needs a stable ID, bucket ID, count, and similar-bucket relation before it is reused by smaller models.",
    "Existing tags can seed candidates, but they are not dumped blindly into the benchmark. The expensive agent may suggest new pending keywords as the benchmark grows.",
    "Human quick verify is the promotion gate from pending suggestion to active benchmark keyword.",
    "Small models should receive verified IDs, simple meanings, and examples only; do not pass annotation bloat or raw expensive-agent reasoning forward.",
    "PDF summaries for nontechnical users must stay simple: keyword, plain meaning, count, similar buckets, and verification state.",
]

SUITE_BRICK_RULES = [
    "When work is a real build brick, add one compact `Brick Entries:` block to `switchboard/local/tasks-completed.md`.",
    "Brick Entries human fields are only: `brick_id | family | mode | status | source_record | next_action`.",
    "Do not hand-write factual brick fields such as serial number, date created, timestamps, versions, commits, file counts, insertions, deletions, or line totals; Switchboard computes those into `switchboard/evidence/brick-registry.json`.",
    "Agents and managers read `switchboard/evidence/brick-registry.json` for brick facts; use the `switchboard.bricks` package or `switchboard brics registry` tool, and do not create project-brick UI panels, new docs, or side ledgers.",
    "Bricks are suite-wide manager/agent accounting for Agent Ops, Switchboard, Palimpsest, Union Bank, X, meeting, sysdocs, and future lanes; they are not user-facing UI panels.",
    "Benchmark keyword bricks use the separate benchmark keyword contract: expensive-agent suggestions, human quick verification, stable keyword IDs, bucket counts, and small-model reuse.",
    "Repeated facts are programmatic. Agent judgment is only for semantic labels, status, blockers, and next action.",
    "Hook brics capture exact Pratik source text locally once, then inject only compact clean rules into Codex/Claude prompts.",
    "Mistake and memory brics are budgeted prompt context tools; they must not dump raw private text or long Agent Ops records into builder prompts.",
]

SEEDED_SWITCHBOARD_BRICKS: tuple[dict[str, str], ...] = (
    {
        "brick_id": "switchboard-task-ledger-activity",
        "project": "switchboard",
        "family": "work-evidence",
        "mode": "programmatic",
        "status": "done",
        "source_record": "record 116",
        "next_action": "laid",
        "commit": "7e7c7f2ad24ea571b43c9b7e643230e0a74cfd81",
    },
    {
        "brick_id": "switchboard-pass1-foundation",
        "project": "switchboard",
        "family": "foundation-data",
        "mode": "programmatic",
        "status": "done",
        "source_record": "record 131",
        "next_action": "laid",
        "commit": "9c3a96ae81b8ac3e2795299a25cdb6a410e688a6",
    },
    {
        "brick_id": "switchboard-pass2-foundation-compression",
        "project": "switchboard",
        "family": "front-page-proof",
        "mode": "hybrid",
        "status": "done",
        "source_record": "record 136",
        "next_action": "laid",
        "commit": "0020c553567c7cab35aca56cf237226b68f0b14d",
    },
    {
        "brick_id": "switchboard-1127-front-page-cleanup",
        "project": "switchboard",
        "family": "product-cleanup",
        "mode": "hybrid",
        "status": "done",
        "source_record": "record 138",
        "next_action": "release checkpoint",
        "commit": "7d4a4718deb2541eb80b5da18817bd92ba1814ed",
    },
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_brick_text(value: str, *, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    lowered = text.lower()
    sensitive_markers = (
        "@",
        "://",
        "\\",
        "secret",
        "credential",
        "password",
        "token",
        "finance row",
        "transcript",
        "raw private",
        "personal data",
    )
    if any(marker in lowered for marker in sensitive_markers):
        return fallback or "redacted"
    cleaned = re.sub(r"\s+", " ", text)
    return cleaned[:160]


def _safe_brick_slug(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.:+-]+", "-", _safe_brick_text(value, fallback=fallback).lower()).strip("-")
    return cleaned or fallback


def normalize_brick_lines(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    valid_modes = {"programmatic", "agentic", "hybrid"}
    valid_statuses = {"planned", "active", "blocked", "done", "deferred", "parked"}
    for raw in lines:
        payload = raw.strip()
        if payload.startswith("- "):
            payload = payload[2:].strip()
        if not payload or payload.lower().startswith("brick_id |"):
            continue
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < len(BRICK_ENTRY_COLUMNS):
            continue
        brick_id, family, mode, status, source_record, next_action = parts[: len(BRICK_ENTRY_COLUMNS)]
        safe_mode = _safe_brick_slug(mode, fallback="hybrid")
        if safe_mode not in valid_modes:
            safe_mode = "hybrid"
        safe_status = _safe_brick_slug(status, fallback="active")
        if safe_status not in valid_statuses:
            safe_status = "active"
        entries.append(
            {
                "brick_id": _safe_brick_slug(brick_id, fallback="unnamed-brick"),
                "family": _safe_brick_slug(family, fallback="general"),
                "mode": safe_mode,
                "status": safe_status,
                "source_record": _safe_brick_text(source_record, fallback="current task"),
                "next_action": _safe_brick_text(next_action, fallback="review"),
            }
        )
    return entries


def _run_git(project_root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _git_shortstat(project_root: Path, commit: str) -> dict[str, int]:
    stats = _run_git(project_root, ["show", "--shortstat", "--format=", "--no-renames", commit])
    files_changed = insertions = deletions = 0
    if match := re.search(r"(\d+)\s+files?\s+changed", stats):
        files_changed = int(match.group(1))
    if match := re.search(r"(\d+)\s+insertions?\(\+\)", stats):
        insertions = int(match.group(1))
    if match := re.search(r"(\d+)\s+deletions?\(-\)", stats):
        deletions = int(match.group(1))
    return {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
        "net_lines": insertions - deletions,
    }


def _git_commit_subject(project_root: Path, commit: str) -> str:
    return _run_git(project_root, ["log", "-1", "--format=%s", commit])


def _git_commit_date(project_root: Path, commit: str) -> str:
    return _run_git(project_root, ["log", "-1", "--format=%cI", commit])


def _version_from_payload(payload: str, filename: str) -> str:
    if not payload:
        return ""
    if filename == "package.json":
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict) and data.get("version"):
            return str(data["version"])
    if filename == "pyproject.toml":
        if match := re.search(r"^version\s*=\s*\"([^\"]+)\"", payload, flags=re.MULTILINE):
            return match.group(1)
    return ""


def _git_commit_version(project_root: Path, commit: str) -> str:
    for filename in ("package.json", "pyproject.toml"):
        if version := _version_from_payload(_run_git(project_root, ["show", f"{commit}:{filename}"]), filename):
            return version
    return ""


def _worktree_version(project_root: Path) -> str:
    for filename in ("package.json", "pyproject.toml"):
        path = project_root / filename
        if path.exists():
            if version := _version_from_payload(path.read_text(encoding="utf-8"), filename):
                return version
    return ""


def _current_head(project_root: Path) -> str:
    return _run_git(project_root, ["rev-parse", "HEAD"])


def _git_path_dirty(project_root: Path, relative_path: str) -> bool:
    return bool(_run_git(project_root, ["status", "--short", "--", relative_path]))


def _last_commit_for_path(project_root: Path, relative_path: str) -> str:
    return _run_git(project_root, ["log", "-1", "--format=%H", "--", relative_path])


def _brick_line_totals(foundation_projection: dict[str, Any] | None) -> dict[str, int]:
    line_noise = foundation_projection.get("line_noise", {}) if isinstance(foundation_projection, dict) else {}
    return {
        "active_lines_after": int(line_noise.get("active_source_lines", 0) or 0),
        "stale_lines_after": int(line_noise.get("noise_line_count", 0) or 0),
    }


def _computed_brick_fields(project_root: Path, commit: str, date_created: str, line_totals: dict[str, int]) -> dict[str, Any]:
    if not commit:
        return {
            "date_created": date_created,
            "commit": "",
            "commit_subject": "",
            "version_introduced": _worktree_version(project_root),
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
            "net_lines": 0,
            **line_totals,
            "computed_status": "pending_commit",
        }
    shortstat = _git_shortstat(project_root, commit)
    commit_subject = _git_commit_subject(project_root, commit)
    return {
        "date_created": date_created or _git_commit_date(project_root, commit),
        "commit": commit,
        "commit_subject": commit_subject,
        "version_introduced": _git_commit_version(project_root, commit),
        **shortstat,
        **line_totals,
        "computed_status": "ok" if any(shortstat.values()) or commit_subject else "unverified",
    }


def _task_brick_rows(service_id: str, tasks: list[dict[str, Any]], current_commit: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in tasks:
        task_bricks = task.get("brick_entries", [])
        if not isinstance(task_bricks, list):
            continue
        for brick in task_bricks:
            if not isinstance(brick, dict):
                continue
            rows.append(
                {
                    "brick_id": str(brick.get("brick_id", "")),
                    "project": service_id,
                    "family": str(brick.get("family", "")),
                    "mode": str(brick.get("mode", "")),
                    "status": str(brick.get("status", "")),
                    "source_record": str(brick.get("source_record", "")),
                    "next_action": str(brick.get("next_action", "")),
                    "source_task_timestamp": str(task.get("timestamp", "")),
                    "source_task_title": str(task.get("title", "")),
                    "date_created": str(task.get("timestamp", "")),
                    "commit": current_commit,
                    "seeded": False,
                }
            )
    return rows


def _with_serial_numbers(service_id: str, bricks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prefix = _safe_brick_slug(service_id, fallback="project").upper().replace("-", "_")
    sorted_bricks = sorted(
        bricks,
        key=lambda row: (
            str(row.get("date_created", "")),
            str(row.get("project", "")),
            str(row.get("brick_id", "")),
        ),
    )
    for index, brick in enumerate(sorted_bricks, start=1):
        brick["serial_number"] = f"{prefix}-BRICK-{index:04d}"
    return sorted_bricks


def build_brick_registry(project_root: Path, service_id: str, tasks: list[dict[str, Any]], foundation_projection: dict[str, Any] | None) -> dict[str, Any]:
    generated = utc_now_iso()
    line_totals = _brick_line_totals(foundation_projection)
    ledger_path = "switchboard/local/tasks-completed.md"
    task_commit = "" if _git_path_dirty(project_root, ledger_path) else _last_commit_for_path(project_root, ledger_path) or _current_head(project_root)
    rows: list[dict[str, Any]] = []
    if service_id == "switch":
        for seed in SEEDED_SWITCHBOARD_BRICKS:
            rows.append({**seed, "source_task_timestamp": "", "source_task_title": "", "date_created": "", "seeded": True})
    rows.extend(_task_brick_rows(service_id, tasks, task_commit))

    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        brick_id = str(row.get("brick_id", "")).strip()
        if not brick_id:
            continue
        computed = _computed_brick_fields(project_root, str(row.get("commit", "")), str(row.get("date_created", "")), line_totals)
        by_id[brick_id] = {
            "brick_id": brick_id,
            "contract_version": BRICS_TOOL_VERSION,
            "project": str(row.get("project", service_id)),
            "family": str(row.get("family", "")),
            "mode": str(row.get("mode", "")),
            "status": str(row.get("status", "")),
            "source_record": str(row.get("source_record", "")),
            "next_action": str(row.get("next_action", "")),
            "source_task_timestamp": str(row.get("source_task_timestamp", "")),
            "source_task_title": str(row.get("source_task_title", "")),
            "seeded": bool(row.get("seeded", False)),
            "input_format": BRICK_CONTRACT["input_format"],
            "output_schema": BRICK_CONTRACT["schema_version"],
            "evidence_refs": [
                "switchboard/local/tasks-completed.md",
                "switchboard/evidence/brick-registry.json",
            ],
            **computed,
        }
    bricks = _with_serial_numbers(service_id, list(by_id.values()))
    return {
        "generated": generated,
        "schema_version": BRICK_CONTRACT["schema_version"],
        "tool": {
            "name": BRICK_CONTRACT["name"],
            "version": BRICS_TOOL_VERSION,
            "package": "switchboard.bricks",
            "package_alias": "switchboard.brics",
            "type": "programmatic_python_package",
        },
        "role": "agent_manager_evidence_only",
        "ui_surface": "none",
        "source": "switchboard/local/tasks-completed.md + git metadata",
        "contract": BRICK_CONTRACT,
        "benchmark_keyword_contract": BENCHMARK_KEYWORD_CONTRACT,
        "benchmark_keyword_rules": BENCHMARK_KEYWORD_RULES,
        "privacy": {
            "classification": "git_safe_metadata",
            "raw_payloads": "excluded",
            "computed_fields": "programmatic",
            "semantic_fields": "agentic",
        },
        "summary": {
            "brick_count": len(bricks),
            "seeded_count": sum(1 for row in bricks if row.get("seeded")),
            "task_ledger_count": sum(1 for row in bricks if not row.get("seeded")),
            "done_count": sum(1 for row in bricks if row.get("status") == "done"),
            "active_count": sum(1 for row in bricks if row.get("status") == "active"),
            "blocked_count": sum(1 for row in bricks if row.get("status") == "blocked"),
        },
        "bricks": bricks,
        "notes": [
            "No project-brick dashboard panel is generated.",
            "Agents read this evidence file; humans keep the clean Control Center surface.",
        ],
    }
