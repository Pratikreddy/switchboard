"""Compact hook context, mistake rules, and memory query helpers."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from .timeline import (
    TIMELINE_SCHEMA_VERSION,
    capture_user_prompt,
    default_timeline_db_path,
    read_timeline_summary,
    store_context_packet,
    utc_now_iso,
)

HOOKS_TOOL_VERSION = "2026-05-26"
HOOKS_REGISTRY_SCHEMA = "switchboard-hooks-registry-v0"

SOURCE_CAPTURE_BRIC = "SUITE-BRIC-SOURCE-0001"
MISTAKE_PATTERN_BRIC = "SUITE-BRIC-MISTAKE-0001"
MEMORY_BRIC = "SUITE-BRIC-MEMORY-0001"

HOOK_BRICS = (
    {
        "brick_id": SOURCE_CAPTURE_BRIC,
        "name": "source-capture",
        "mode": "programmatic",
        "status": "active",
        "summary": "Capture exact UserPromptSubmit text locally, then expose only timestamp/hash/source refs to git-safe evidence.",
    },
    {
        "brick_id": MISTAKE_PATTERN_BRIC,
        "name": "mistake-patterns",
        "mode": "hybrid",
        "status": "active",
        "summary": "Turn repeated corrections and mistake records into compact task-relevant prompt rules.",
    },
    {
        "brick_id": MEMORY_BRIC,
        "name": "memory-query",
        "mode": "hybrid",
        "status": "active",
        "summary": "Query approved local sources now; keep the interface stable for Palimpsest/RAG later.",
    },
)

SOURCE_TO_RULE_EXAMPLES = (
    {
        "raw_source_ref": "manager-private:pratik-words-need-recording",
        "compact_rule": "Preserve raw source language in a local-private record first.",
        "category": "source_capture",
    },
    {
        "raw_source_ref": "manager-private:timestamp-each-atomic-row",
        "compact_rule": "Generate timestamps and record IDs programmatically.",
        "category": "programmatic_facts",
    },
    {
        "raw_source_ref": "manager-private:repeated-facts-programmatic",
        "compact_rule": "Repeated factual fields are computed by code; agents provide only semantic labels.",
        "category": "programmatic_facts",
    },
    {
        "raw_source_ref": "manager-private:no-project-bric-ui-dump",
        "compact_rule": "Keep brics internal to agents/managers unless explicitly exposed.",
        "category": "ui_boundary",
    },
    {
        "raw_source_ref": "manager-private:no-ui-dumping",
        "compact_rule": "Do not add dashboard UI for project bric dumps.",
        "category": "ui_boundary",
    },
)

BASE_RULES = (
    {
        "category": "source_capture",
        "severity": "high",
        "rule": "Preserve raw source language in local-private capture; send cleaned operational rules to builders.",
        "prompt_snippet": "Source capture first; builder prompt gets compact clean rules only.",
        "keywords": ("agent ops", "manager", "prompt", "source", "raw", "record"),
    },
    {
        "category": "programmatic_facts",
        "severity": "high",
        "rule": "Generate timestamps, record IDs, bric serials, versions, and line stats programmatically.",
        "prompt_snippet": "Do not hand-write computed bric facts; Python computes them.",
        "keywords": ("bric", "brick", "timestamp", "version", "lines", "serial"),
    },
    {
        "category": "side_file_bloat",
        "severity": "high",
        "rule": "Do not create side files unless explicitly requested.",
        "prompt_snippet": "No side files; canonical record only unless requested.",
        "keywords": ("agent ops", "manager", "doc", "ledger", "side file", "notes"),
    },
    {
        "category": "manual_edit_method",
        "severity": "medium",
        "rule": "Use apply_patch for manual edits.",
        "prompt_snippet": "Use apply_patch for manual file edits.",
        "keywords": ("code", "edit", "patch", "file"),
    },
    {
        "category": "fuel_side_task",
        "severity": "high",
        "rule": "Do not treat fuel checks as the main task.",
        "prompt_snippet": "Fuel/usage checks are side monitors; continue the main task.",
        "keywords": ("fuel", "usage", "analytics", "heartbeat"),
    },
    {
        "category": "internal_bric_ui_boundary",
        "severity": "high",
        "rule": "Do not add UI panels for internal brics.",
        "prompt_snippet": "No project-bric UI panels or dashboard dumps.",
        "keywords": ("ui", "dashboard", "front page", "panel", "bric", "brick"),
    },
    {
        "category": "client_server_no_login",
        "severity": "high",
        "rule": "Do not login to .47, .114, or .253; ask Pratik to run commands.",
        "prompt_snippet": "No SSH/SFTP/SCP/rsync to .47, .114, or .253; use public checks or Pratik-run commands.",
        "keywords": ("zapp", ".47", ".114", ".253", "server", "ssh", "sftp", "scp"),
    },
    {
        "category": "template_safety",
        "severity": "medium",
        "rule": "Do not rewrite Zapp docgenerator templates/layout without approval.",
        "prompt_snippet": "Do not rewrite docgenerator templates or layout.",
        "keywords": ("zapp", "docgenerator", "pdf", "docx", "template", "layout"),
    },
    {
        "category": "keyword_benchmark_transfer",
        "severity": "medium",
        "rule": "Existing tags are candidates; expensive model suggests, human verifies, small model gets only verified IDs.",
        "prompt_snippet": "Benchmark keywords need human verification before small-model reuse.",
        "keywords": ("keyword", "benchmark", "small model", "tag", "pdf"),
    },
)

TASK_CONTEXTS = (
    {
        "name": "switchboard-code",
        "keywords": ("switchboard", "dashboard", "code", "bric", "brick"),
        "lines": (
            "Active bric is read from task/context, not guessed.",
            "No UI unless explicitly requested.",
            "Add `Brick Entries:` only for real brics.",
            "Python computes serial/date/version/line stats.",
            "Run snapshot and verify-update before closeout.",
        ),
    },
    {
        "name": "agent-ops-manager",
        "keywords": ("agent ops", "manager", "agent_ops.md", "intake"),
        "lines": (
            "Preserve Pratik's exact words in local-private source capture.",
            "Active file gets one compact intake row only.",
            "No long raw dumps in AGENT_OPS.md.",
            "Update Switchboard ledger and verify after manager-file changes.",
        ),
    },
    {
        "name": "zapp-client-server",
        "keywords": ("zapp", ".114", ".253", ".47", "server"),
        "lines": (
            "No SSH/SFTP/SCP/rsync to .114, .253, or .47.",
            "Public HTTP checks are allowed.",
            "Server truth requires Pratik-run commands.",
            "Do not rewrite docgenerator templates/layout.",
        ),
    },
    {
        "name": "keyword-benchmark",
        "keywords": ("keyword", "benchmark", "small model", "tag"),
        "lines": (
            "Existing tags are candidates, not truth.",
            "Expensive model suggests keywords; human verifies.",
            "Small model receives only verified keyword IDs, plain meanings, examples.",
            "Exclude expensive-agent reasoning and annotation bloat.",
        ),
    },
)

MEMORY_SOURCE_HINTS = (
    {
        "source_ref": "memory://agent-ops",
        "applies_to": ("agent ops", "manager", "source", "prompt"),
        "freshness": "current-local",
        "confidence": "high",
        "snippet": "Agent Ops is manager-private source capture and compact row control, not long raw prompt dumps.",
    },
    {
        "source_ref": "memory://switchboard-brics",
        "applies_to": ("switchboard", "bric", "brick", "ledger"),
        "freshness": "current-local",
        "confidence": "high",
        "snippet": "Switchboard brics are internal evidence generated from task ledgers and git metadata; no UI dump.",
    },
    {
        "source_ref": "memory://zapp-client-servers",
        "applies_to": ("zapp", ".114", ".253", ".47"),
        "freshness": "pinned-rule",
        "confidence": "high",
        "snippet": "Client server truth needs public checks or Pratik-run commands; no agent login attempts.",
    },
    {
        "source_ref": "memory://benchmark-keywords",
        "applies_to": ("keyword", "benchmark", "tag", "small model"),
        "freshness": "current-local",
        "confidence": "medium",
        "snippet": "Keyword benchmarks promote from candidate to active only after human verification.",
    },
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _display_path(path: Path) -> str:
    try:
        return str(path).replace(str(Path.home()), "~", 1)
    except RuntimeError:
        return str(path)


def _command_summary(command: str) -> dict[str, str]:
    text = _clean(command)
    first_token = text.split(" ", 1)[0] if text else ""
    name = Path(first_token).name if first_token else ""
    return {
        "command_name": name or "command",
        "command_hash": _sha256(text),
        "command_display": text.replace(str(Path.home()), "~", 1)[:180],
    }


def _rough_tokens(value: str) -> int:
    return max(1, len(value) // 4)


def _score_terms(text: str, terms: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term and term.lower() in lowered)


def _rank_rules(task: str, cwd: str) -> list[dict[str, Any]]:
    haystack = f"{task} {cwd}".lower()
    ranked = []
    for index, rule in enumerate(BASE_RULES):
        score = _score_terms(haystack, rule["keywords"]) * 10
        if rule["severity"] == "high":
            score += 3
        if score or index < 3:
            ranked.append({**rule, "score": score, "repeat_count": max(1, score // 10)})
    return sorted(ranked, key=lambda item: (-int(item["score"]), str(item["category"])))


def _matching_task_contexts(task: str, cwd: str) -> list[dict[str, Any]]:
    haystack = f"{task} {cwd}".lower()
    matches = []
    for context in TASK_CONTEXTS:
        score = _score_terms(haystack, context["keywords"])
        if score:
            matches.append({**context, "score": score})
    return sorted(matches, key=lambda item: (-int(item["score"]), str(item["name"])))


def _render_packet(agent: str, task: str, cwd: str, rules: list[dict[str, Any]], contexts: list[dict[str, Any]]) -> str:
    lines = [
        "Suite Context:",
        f"- Agent: {agent}",
        f"- CWD: {cwd or 'unknown'}",
    ]
    if task:
        lines.append(f"- Task: {_clean(task)[:160]}")
    lines.extend(
        [
            f"- Source capture bric: {SOURCE_CAPTURE_BRIC}.",
            "- Raw Pratik wording stays local-private; builders get compact rules.",
        ]
    )
    for rule in rules:
        lines.append(f"- {rule['prompt_snippet']}")
    for context in contexts:
        for item in context["lines"]:
            lines.append(f"- {item}")
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if line not in seen:
            deduped.append(line)
            seen.add(line)
    return "\n".join(deduped)


def _trim_to_budget(content: str, budget: int) -> str:
    if _rough_tokens(content) <= budget:
        return content
    kept: list[str] = []
    for line in content.splitlines():
        candidate = "\n".join([*kept, line])
        if _rough_tokens(candidate) > budget:
            break
        kept.append(line)
    return "\n".join(kept).rstrip()


def build_context_packet(
    *,
    agent: str,
    cwd: str,
    task: str = "",
    budget: int = 800,
    persist: bool = False,
) -> dict[str, Any]:
    rules = _rank_rules(task, cwd)[:6]
    contexts = _matching_task_contexts(task, cwd)[:2]
    content = _trim_to_budget(_render_packet(agent, task, cwd, rules, contexts), budget)
    source_refs = [
        "switchboard-hooks://base-rules",
        "switchboard-hooks://source-to-rule-examples",
        "switchboard-hooks://task-contexts",
    ]
    result = {
        "schema_version": "switchboard-hook-context-packet-v0",
        "generated": utc_now_iso(),
        "agent": agent,
        "cwd": cwd,
        "task": task,
        "budget": budget,
        "estimated_tokens": _rough_tokens(content),
        "content": content,
        "rules": [
            {
                "category": item["category"],
                "severity": item["severity"],
                "rule": item["rule"],
                "prompt_snippet": item["prompt_snippet"],
                "score": item["score"],
            }
            for item in rules
        ],
        "task_contexts": [item["name"] for item in contexts],
        "source_refs": source_refs,
        "privacy": {
            "raw_source_language": "excluded",
            "builder_prompt": "clean_operational_rules_only",
        },
    }
    if persist:
        stored = store_context_packet(
            agent=agent,
            cwd=cwd,
            task=task,
            budget=budget,
            estimated_tokens=result["estimated_tokens"],
            content=content,
            source_refs=source_refs,
        )
        result["packet_id"] = stored["packet_id"]
    return result


def build_user_prompt_response(
    *,
    hook_payload: dict[str, Any],
    agent: str,
    budget: int = 800,
    capture: bool = True,
) -> dict[str, Any]:
    prompt = str(hook_payload.get("prompt") or hook_payload.get("user_prompt") or hook_payload.get("transcript") or "")
    cwd = str(hook_payload.get("cwd") or hook_payload.get("project_root") or "")
    task = prompt[:300]
    source_ref = None
    if capture and prompt:
        captured = capture_user_prompt(
            prompt=prompt,
            agent=agent,
            cwd=cwd,
            hook_event_name=str(hook_payload.get("hook_event_name") or hook_payload.get("hookEventName") or "UserPromptSubmit"),
            related_brics=[SOURCE_CAPTURE_BRIC],
            metadata={key: hook_payload.get(key) for key in ("session_id", "turn_id", "transcript_path") if key in hook_payload},
        )
        source_ref = captured["raw_source_ref"]
    packet = build_context_packet(agent=agent, cwd=cwd, task=task, budget=budget, persist=True)
    if source_ref:
        packet["source_refs"] = [source_ref, *packet["source_refs"]]
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": packet["content"],
        },
        "switchboard": {
            "schema_version": "switchboard-hook-response-v0",
            "packet_id": packet.get("packet_id", ""),
            "source_refs": packet.get("source_refs", []),
            "estimated_tokens": packet["estimated_tokens"],
            "raw_prompt_included": False,
        },
    }


def build_memory_query(*, task: str, cwd: str, budget: int = 800) -> dict[str, Any]:
    haystack = f"{task} {cwd}".lower()
    matches = []
    for item in MEMORY_SOURCE_HINTS:
        score = _score_terms(haystack, item["applies_to"])
        if score:
            matches.append({**item, "score": score})
    if not matches:
        matches = [{**MEMORY_SOURCE_HINTS[0], "score": 0}]
    matches = sorted(matches, key=lambda item: (-int(item["score"]), str(item["source_ref"])))
    rules = _rank_rules(task, cwd)[:4]
    lines = ["Memory Context:"]
    for item in matches:
        lines.append(f"- {item['snippet']} ({item['source_ref']}; {item['freshness']}; {item['confidence']})")
    for rule in rules:
        lines.append(f"- Rule: {rule['prompt_snippet']}")
    content = _trim_to_budget("\n".join(lines), budget)
    return {
        "schema_version": "switchboard-memory-query-v0",
        "generated": utc_now_iso(),
        "task": task,
        "cwd": cwd,
        "budget": budget,
        "estimated_tokens": _rough_tokens(content),
        "content": content,
        "source_refs": [item["source_ref"] for item in matches],
        "privacy": {
            "raw_source_language": "excluded",
            "approved_sources_only": True,
            "future_backend": "palimpsest",
        },
    }


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _hook_rows_from_settings(path: Path, agent: str, scope: str) -> list[dict[str, Any]]:
    payload = _read_json_dict(path)
    hooks = payload.get("hooks")
    if not isinstance(hooks, dict):
        return []
    rows: list[dict[str, Any]] = []
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            hook_list = entry.get("hooks")
            if not isinstance(hook_list, list):
                continue
            for hook_index, hook in enumerate(hook_list):
                if not isinstance(hook, dict):
                    continue
                command = str(hook.get("command") or "")
                rows.append(
                    {
                        "agent": agent,
                        "scope": scope,
                        "source_path": _display_path(path),
                        "event": str(event),
                        "matcher": str(entry.get("matcher") or ""),
                        "entry_index": index,
                        "hook_index": hook_index,
                        "hook_type": str(hook.get("type") or ""),
                        "managed_by_switchboard": "switchboard.cli hooks user-prompt-submit" in command,
                        **_command_summary(command),
                    }
                )
    return rows


def discover_existing_hooks(project_root: Path) -> dict[str, Any]:
    sources = [
        ("claude", "global", Path.home() / ".claude" / "settings.json"),
        ("claude", "global-local", Path.home() / ".claude" / "settings.local.json"),
        ("claude", "project", project_root / ".claude" / "settings.local.json"),
        ("codex", "project", project_root / ".codex" / "hooks.json"),
    ]
    rows: list[dict[str, Any]] = []
    for agent, scope, path in sources:
        rows.extend(_hook_rows_from_settings(path, agent, scope))
    return {
        "schema_version": "switchboard-existing-hooks-v0",
        "generated": utc_now_iso(),
        "sources_checked": [_display_path(path) for _, _, path in sources],
        "hook_count": len(rows),
        "claude_hook_count": sum(1 for row in rows if row["agent"] == "claude"),
        "codex_hook_count": sum(1 for row in rows if row["agent"] == "codex"),
        "switchboard_managed_count": sum(1 for row in rows if row["managed_by_switchboard"]),
        "events": sorted(set(str(row["event"]) for row in rows)),
        "hooks": rows,
        "privacy": {
            "raw_history_files": "not_read",
            "prompt_cache_files": "not_read",
            "command_hashes": "included",
            "command_display": "truncated_home_redacted",
        },
    }


def build_hooks_registry(project_root: Path) -> dict[str, Any]:
    timeline = read_timeline_summary()
    existing_hooks = discover_existing_hooks(project_root)
    return {
        "generated": utc_now_iso(),
        "schema_version": HOOKS_REGISTRY_SCHEMA,
        "tool": {
            "name": "switchboard-hooks",
            "version": HOOKS_TOOL_VERSION,
            "package": "switchboard.hooks",
            "type": "programmatic_python_package",
        },
        "role": "agent_prompt_context_and_local_private_source_capture",
        "ui_surface": "none",
        "project_root": str(project_root),
        "timeline": {
            "schema_version": TIMELINE_SCHEMA_VERSION,
            "db_location": "~/.agent-ops/private/hooks/timeline.sqlite",
            "raw_prompt_text": "local_private_only",
            "git_safe_summary_only": True,
            **timeline,
        },
        "brics": list(HOOK_BRICS),
        "existing_hooks": existing_hooks,
        "contracts": {
            "source_capture": {
                "hook_event": "UserPromptSubmit",
                "raw_fields_local_private": ["raw_prompt"],
                "git_safe_fields": ["timestamp", "hash", "cwd", "agent", "source_type", "related_bric_ids"],
            },
            "mistake_patterns": {
                "inputs": ["MISTAKES.md", "Agent Ops intake rows", "hook event tags"],
                "output": "ranked compact prompt snippets",
                "raw_language": "manager_private_refs_only",
            },
            "memory_query": {
                "v1_sources": ["local Agent Ops rules", "Switchboard evidence", "memory hints"],
                "future_backend": "Palimpsest RAG",
                "output": "budgeted rules, source refs, stale/fresh status, confidence",
            },
        },
        "source_to_rule_examples": list(SOURCE_TO_RULE_EXAMPLES),
        "prompt_examples": {
            "switchboard_code_task": build_context_packet(agent="codex", cwd=str(project_root), task="switchboard bric code task", budget=400)["content"],
            "zapp_client_server_task": build_context_packet(agent="codex", cwd="/Users/p/Desktop/work/zapp/docgenerator", task="zapp .114 docgenerator cleanup", budget=400)["content"],
            "keyword_benchmark_task": build_context_packet(agent="codex", cwd=str(project_root), task="keyword benchmark small model", budget=400)["content"],
        },
        "privacy": {
            "classification": "git_safe_metadata",
            "raw_prompts": "excluded",
            "raw_profanity_or_private_text": "excluded",
            "builder_prompt": "clean_operational_rules_only",
        },
    }
