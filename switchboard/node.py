"""Node-mode install, upgrade, snapshot, and asset helpers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import ROOT_DIR
from .defaults import DEFAULT_NODE_PORT


NODE_DIR_NAME = "switchboard"
CORE_DIR_NAME = "core"
LOCAL_DIR_NAME = "local"
EVIDENCE_DIR_NAME = "evidence"
ROUTING_TAGS = ("task", "handoff", "runbook", "decision", "scope")
AGENT_CONTRACT_VERSION = "2026-04-29"
AGENT_CONTRACT_MARKER = "switchboard-managed-agent-contract"
DEFAULT_AGENT_ENTRYPOINTS = ("agents",)
VALID_AGENT_ENTRYPOINTS = ("agents", "claude", "gemini", "qwen", "opencode")
MANAGER_MANIFEST_NAME = "manager.manifest.json"
GLOBAL_DESIGN_PRINCIPLES = [
    "Read back Pratik's request before acting.",
    "Ask in simple English when intent is unclear.",
    "Make the smallest useful change.",
    "Touch only files required by the request.",
    "Do not invent future features.",
    "Keep output short and avoid ceremony.",
    "Never delete for cleanup; move or zip instead.",
    "Verify with observable checks.",
]
MANAGED_DOC_DEFAULTS: tuple[tuple[str, str, bool], ...] = (
    ("readme", "README.md", False),
    ("api", "API.md", False),
    ("changelog", "CHANGELOG.md", False),
    ("handoff", "switchboard/local/control-center-handoff.md", True),
    ("runbook", "switchboard/local/runbook.md", True),
    ("approach_history", "switchboard/local/approach-history.md", True),
    ("doc_index_md", "switchboard/local/doc-index.md", True),
    ("doc_index_json", "switchboard/evidence/doc-index.json", True),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return token or "switchboard-node"


def node_paths(project_root: Path) -> dict[str, Path]:
    root = project_root / NODE_DIR_NAME
    return {
        "project_root": project_root,
        "node_root": root,
        "core": root / CORE_DIR_NAME,
        "local": root / LOCAL_DIR_NAME,
        "evidence": root / EVIDENCE_DIR_NAME,
        "manifest": root / "node.manifest.json",
        "manager_manifest": root / MANAGER_MANIFEST_NAME,
        "core_readme": root / CORE_DIR_NAME / "README.md",
        "playbook": root / CORE_DIR_NAME / "playbook.md",
        "design_principles": root / CORE_DIR_NAME / "design-principles.md",
        "doc_structure_rules": root / CORE_DIR_NAME / "doc-structure-rules.md",
        "agent_instructions": root / CORE_DIR_NAME / "agent-instructions.md",
        "bootstrap_prompt": root / CORE_DIR_NAME / "bootstrap-standardize-prompt.md",
        "runtime_prompt": root / CORE_DIR_NAME / "runtime-update-prompt.md",
        "agent_contract_md": root / CORE_DIR_NAME / "agent-contract.md",
        "agent_contract_json": root / CORE_DIR_NAME / "agent-contract.json",
        "tasks_completed": root / LOCAL_DIR_NAME / "tasks-completed.md",
        "handoff": root / LOCAL_DIR_NAME / "control-center-handoff.md",
        "runbook": root / LOCAL_DIR_NAME / "runbook.md",
        "approach_history": root / LOCAL_DIR_NAME / "approach-history.md",
        "doc_index_md": root / LOCAL_DIR_NAME / "doc-index.md",
        "completed_tasks_json": root / EVIDENCE_DIR_NAME / "completed-tasks.json",
        "doc_index_json": root / EVIDENCE_DIR_NAME / "doc-index.json",
        "repo_safety_history": root / EVIDENCE_DIR_NAME / "repo-safety-history.json",
        "pull_bundle_history": root / EVIDENCE_DIR_NAME / "pull-bundle-history.json",
        "scope_snapshot": root / EVIDENCE_DIR_NAME / "scope.snapshot.json",
        "update_gate": root / EVIDENCE_DIR_NAME / "update-gate.json",
        "runtime": root / "runtime",
        "start_script": root / "start.sh",
        "run_script": root / "run.sh",
        "agents_md": project_root / "AGENTS.md",
        "claude_md": project_root / "CLAUDE.md",
        "gemini_md": project_root / "GEMINI.md",
        "qwen_md": project_root / "QWEN.md",
        "gemini_settings": project_root / ".gemini" / "settings.json",
        "qwen_settings": project_root / ".qwen" / "settings.json",
        "opencode_config": project_root / "opencode.json",
        "opencode_agent": project_root / ".opencode" / "agents" / "switchboard.md",
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_executable(path: Path, content: str) -> None:
    _write_text(path, content)
    path.chmod(0o755)


def load_node_manifest(project_root: str | Path) -> dict[str, Any]:
    paths = node_paths(Path(project_root).resolve())
    if not paths["manifest"].exists():
        raise FileNotFoundError(f"Node manifest not found: {paths['manifest']}")
    return _read_json(paths["manifest"], {})


def load_manager_manifest(manager_root: str | Path) -> dict[str, Any]:
    paths = node_paths(Path(manager_root).resolve())
    if not paths["manager_manifest"].exists():
        raise FileNotFoundError(f"Manager manifest not found: {paths['manager_manifest']}")
    return _read_json(paths["manager_manifest"], {})


def _default_display_name(service_id: str) -> str:
    return service_id.replace("-", " ").replace("_", " ").title()


def _node_id(service_id: str, project_root: Path) -> str:
    digest = hashlib.sha1(str(project_root).encode("utf-8")).hexdigest()[:10]
    return f"{service_id}-{digest}"


def _managed_doc_defaults() -> list[dict[str, Any]]:
    return [
        {
            "doc_id": doc_id,
            "path": path,
            "enabled": enabled,
            "generated_from": "switchboard/local/tasks-completed.md",
            "last_generated_at": None,
        }
        for doc_id, path, enabled in MANAGED_DOC_DEFAULTS
    ]


def _normalize_managed_docs(existing: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    defaults = {entry["doc_id"]: entry for entry in _managed_doc_defaults()}
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for entry in existing or []:
        doc_id = str(entry.get("doc_id", "")).strip()
        if not doc_id or doc_id in seen:
            continue
        default = defaults.get(doc_id, {})
        seen.add(doc_id)
        normalized.append(
            {
                "doc_id": doc_id,
                "path": str(entry.get("path") or default.get("path") or "").strip(),
                "enabled": bool(entry.get("enabled", default.get("enabled", False))),
                "generated_from": str(entry.get("generated_from") or "switchboard/local/tasks-completed.md"),
                "last_generated_at": entry.get("last_generated_at"),
            }
        )
    for doc_id, default in defaults.items():
        if doc_id in seen:
            continue
        normalized.append(default)
    return normalized


def _managed_doc_by_id(managed_docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(entry["doc_id"]): entry for entry in managed_docs}


def _managed_doc_path(project_root: Path, entry: dict[str, Any]) -> Path:
    return project_root / str(entry["path"])


def _is_switchboard_internal_path(path: str, project_root: Path) -> bool:
    try:
        relative = Path(path).resolve().relative_to(project_root.resolve())
    except (OSError, ValueError):
        return False
    parts = relative.parts
    return len(parts) >= 2 and parts[0] == NODE_DIR_NAME and parts[1] in {
        CORE_DIR_NAME,
        LOCAL_DIR_NAME,
        EVIDENCE_DIR_NAME,
        "runtime",
        "manager",
        "static",
    }


def _filter_inherited_scope_entries(scope_entries: list[dict[str, Any]], project_root: Path) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for entry in scope_entries:
        kind = str(entry.get("kind", ""))
        path = str(entry.get("path", ""))
        if kind != "exclude" and _is_switchboard_internal_path(path, project_root):
            continue
        filtered.append(entry)
    return filtered


def _managed_doc_label(doc_id: str) -> str:
    labels = {
        "readme": "README",
        "api": "API",
        "changelog": "CHANGELOG",
        "handoff": "Control Center Handoff",
        "runbook": "Runbook",
        "approach_history": "Approach History",
        "doc_index_md": "Doc Index Markdown",
        "doc_index_json": "Doc Index JSON",
    }
    return labels.get(doc_id, doc_id)


def _core_templates(service_id: str, display_name: str) -> dict[str, str]:
    return {
        "README.md": (
            f"# {display_name} Switchboard Node\n\n"
            "- This folder is owned by the Switchboard package.\n"
            "- Core files in `switchboard/core/` are standardized and may be replaced on upgrade.\n"
            "- Agents should read `switchboard/core/playbook.md` first.\n"
            "- Agents should maintain project-specific updates through `switchboard/local/tasks-completed.md`.\n"
            "- Snapshot regeneration rebuilds derived docs and evidence deterministically from the canonical file.\n"
            "- Node sync is manual and initiated from the control center.\n"
            f"- Service id: `{service_id}`\n"
        ),
        "playbook.md": (
            f"# {display_name} Switchboard Playbook\n\n"
            "This is the only primary instruction file agents should rely on for normal work in this project.\n\n"
            "## Ownership Rules\n\n"
            "- `switchboard/core/` is framework-owned and replaced by Switchboard upgrades.\n"
            "- `switchboard/local/tasks-completed.md` is the single canonical file agents should edit during normal work.\n"
            "- Derived docs and evidence are generated from that canonical file on `switchboard node snapshot`.\n"
            "- Root project docs such as `README.md`, `API.md`, and `CHANGELOG.md` are only rewritten when they are enabled in `switchboard/node.manifest.json` under `managed_docs`.\n"
            "- If a root doc is not enabled there, Switchboard must not edit it.\n\n"
            "## Required Entry Shape\n\n"
            "- Heading: `## <ISO timestamp> | <title>`\n"
            "- `Tags:` with only `task`, `handoff`, `runbook`, `decision`, `scope`\n"
            "- `Summary:` one concise sentence\n"
            "- `Changed Paths:` comma-separated paths\n\n"
            "- `Agent:` the agent or CLI that made the update\n"
            "- `Tool:` the tool surface used, such as `codex-cli` or `claude-code`\n"
            "- `Read Back:` one short sentence proving requirements were restated before work\n"
            "- `Scope Check:` one short sentence saying scope changed and was updated, or did not change\n\n"
            "## Hard Gate\n\n"
            "- An update is incomplete until `switchboard node verify-update --project-root <path>` returns `ok`.\n"
            "- `update Switchboard` means task ledger, scope/excludes check, snapshot, manifest/scope verification, and Control Center verification.\n"
            "- Never delete for cleanup. Move or zip instead.\n"
            "- Keep output short and do not add ceremony.\n\n"
            "## Optional Blocks\n\n"
            "- `Version:` single version string that becomes the canonical version source across derived docs\n"
            "- `Readme:` markdown block for project overview/state\n"
            "- `API:` markdown block for API-facing updates\n"
            "- `Changelog:` markdown block for release-style deltas\n"
            "- `Notes:` general details that do not belong in the other routed blocks\n"
            "- `Scope Entries:` lines in `kind | path_type | path | enabled` format\n"
            "- `Runtime:` lines for `expected_ports`, `healthcheck_command`, `run_command_hint`, `monitoring_mode`, and `notes`\n\n"
            "## Canonical Workflow\n\n"
            "1. Read this playbook.\n"
            "2. Read back the request before changing files.\n"
            "3. Edit only `switchboard/local/tasks-completed.md` for normal Switchboard updates.\n"
            "4. Include `Read Back`, `Scope Check`, `Agent`, and `Tool` in the latest task entry.\n"
            "5. Run `switchboard node snapshot --project-root <path>`.\n"
            "6. Run `switchboard node verify-update --project-root <path>`.\n"
            "7. Do not hand-edit derived docs unless explicitly instructed.\n\n"
            "## Sync Rules\n\n"
            "- Nodes do not call back into the control center.\n"
            "- Nodes do not SSH into the control-center machine.\n"
            "- Sync is always initiated from the control center.\n"
            "- Control center may mirror scope, runtime, managed-doc configuration, and pull-bundle history into the node.\n"
        ),
        "design-principles.md": (
            "# Switchboard Node Design Principles\n\n"
            "This file is a compatibility stub.\n\n"
            "Read `switchboard/core/playbook.md` for the authoritative rules.\n"
        ),
        "doc-structure-rules.md": (
            "# Switchboard Node Doc Structure Rules\n\n"
            "This file is a compatibility stub.\n\n"
            "Read `switchboard/core/playbook.md` for the authoritative rules.\n"
        ),
        "agent-instructions.md": (
            "# Agent Instructions\n\n"
            "This file is a compatibility stub.\n\n"
            "Read `switchboard/core/playbook.md` first. It is the only primary rulebook.\n"
        ),
        "bootstrap-standardize-prompt.md": (
            "# Bootstrap Standardize Prompt\n\n"
            "Use everything you can safely inspect in the available project directories to standardize this project into the Switchboard format.\n\n"
            "Requirements:\n"
            "- Read `switchboard/core/playbook.md` first.\n"
            "- Inspect the project root and known subpaths.\n"
            "- Find existing readmes, changelogs, runbooks, handoff notes, agent instructions, and operational docs.\n"
            "- Preserve useful information, but rewrite it into the Switchboard standard files under `switchboard/`.\n"
            "- Do not overwrite unrelated project docs outside `switchboard/` unless explicitly asked.\n"
            "- Put the actual structured update in `switchboard/local/tasks-completed.md`, not directly into derived docs.\n"
            "- If the project has known ports, health checks, or run command hints, include them in the latest `tasks-completed.md` entry under a `Runtime:` block.\n"
            "- If project root docs should be framework-owned, record the needed `Readme`, `API`, `Changelog`, and `Version` blocks in `tasks-completed.md` and enable those docs through the node managed-doc config.\n"
            "- Record the standardization work in `switchboard/local/tasks-completed.md` using the required entry format.\n"
            "- Finish by running `switchboard node snapshot --project-root <path>`.\n"
        ),
        "runtime-update-prompt.md": (
            "# Runtime Update Prompt\n\n"
            "For regular maintenance work:\n"
            "- Read `switchboard/core/playbook.md` first.\n"
            "- Inspect system docs for dependencies and record agent/tool used.\n"
            "- Update only `switchboard/local/tasks-completed.md`.\n"
            "- Use one entry per meaningful update.\n"
            "- Include timestamp, title, summary, changed paths, and routing tags.\n"
            "- Include `Agent`, `Tool`, `Read Back`, and `Scope Check`.\n"
            "- Use only these routing tags: `task`, `handoff`, `runbook`, `decision`, `scope`.\n"
            "- If project-facing docs changed, add `Version`, `Readme`, `API`, and `Changelog` blocks as needed.\n"
            "- If scope changed, include a `Scope Entries` block in the entry.\n"
            "- If runtime config changed, include a `Runtime:` block in the entry.\n"
            "- Finish by running `switchboard node snapshot --project-root <path>` and `switchboard node verify-update --project-root <path>`.\n\n"
            "Entry format:\n"
            "## 2026-04-01T12:00:00+00:00 | Example title\n"
            "- Tags: task, handoff\n"
            "- Summary: Short summary.\n"
            "- Changed Paths: src/app.py, switchboard/local/tasks-completed.md\n"
            "- Agent: Codex\n"
            "- Tool: codex-cli\n"
            "- Read Back: Restated the request before editing.\n"
            "- Scope Check: Project shape did not change; existing scope remains valid.\n"
            "- Version: 1.1\n"
            "- Readme:\n"
            "  ## Overview\n"
            "  Updated high-level project notes.\n"
            "- API:\n"
            "  ## Endpoints\n"
            "  Added `/health`.\n"
            "- Changelog:\n"
            "  - Added health endpoint.\n"
            "- Notes:\n"
            "  - Optional detail line.\n"
            "- Scope Entries:\n"
            "  - doc | file | /abs/path/to/file.md\n"
            "  - exclude | glob | venv\n"
            "- Runtime:\n"
            f"  - expected_ports: {DEFAULT_NODE_PORT}, 8000\n"
            f"  - healthcheck_command: curl http://127.0.0.1:{DEFAULT_NODE_PORT}/api/health\n"
            f"  - run_command_hint: uvicorn main:app --port {DEFAULT_NODE_PORT}\n"
            "  - monitoring_mode: manual\n"
        ),
    }


def _normalize_principles(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("project", [])
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _effective_principles(project_principles: list[str] | None = None) -> dict[str, list[str]]:
    project = _normalize_principles(project_principles or [])
    effective = [*GLOBAL_DESIGN_PRINCIPLES]
    for item in project:
        if item not in effective:
            effective.append(item)
    return {
        "global": list(GLOBAL_DESIGN_PRINCIPLES),
        "project": project,
        "effective": effective,
    }


def _normalize_agent_entrypoints(value: Any) -> list[str]:
    raw_values = value if isinstance(value, list) else list(DEFAULT_AGENT_ENTRYPOINTS)
    normalized: list[str] = []
    aliases = {
        "agent": "agents",
        "agents.md": "agents",
        "claude-code": "claude",
        "gemini-cli": "gemini",
        "qwen-code": "qwen",
        "open-code": "opencode",
    }
    for item in raw_values:
        token = aliases.get(str(item).strip().lower(), str(item).strip().lower())
        if token in VALID_AGENT_ENTRYPOINTS and token not in normalized:
            normalized.append(token)
    return normalized or list(DEFAULT_AGENT_ENTRYPOINTS)


def _agent_contract_payload(
    service_id: str,
    display_name: str,
    project_principles: list[str] | None = None,
    enabled_entrypoints: list[str] | None = None,
    inherited_from: str = "",
) -> dict[str, Any]:
    principles = _effective_principles(project_principles)
    enabled = _normalize_agent_entrypoints(enabled_entrypoints)
    return {
        "version": AGENT_CONTRACT_VERSION,
        "service_id": service_id,
        "display_name": display_name,
        "mode": "manager_inherited" if inherited_from else "local",
        "inherited_from": inherited_from,
        "enabled_entrypoints": enabled,
        "supported_agents": [
            "codex",
            "claude-code",
            "gemini-cli",
            "qwen-code",
            "opencode",
            "generic",
        ],
        "principles": principles["effective"],
        "principle_layers": principles,
        "canonical_update_gate": [
            "Record one entry in switchboard/local/tasks-completed.md.",
            "Include Agent, Tool, Read Back, and Scope Check.",
            "Update Scope Entries when project shape changed.",
            "Run switchboard node snapshot --project-root <path>.",
            "Run switchboard node verify-update --project-root <path>.",
            "Verify manifest, scope snapshot, and Control Center view.",
        ],
        "pull_scope": {
            "include": ["source", "config", "docs", "ui", "backend"],
            "exclude": ["secrets", "virtualenvs", "logs", "runtime files", "caches", "removed tech"],
        },
    }


def _agent_contract_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Switchboard Agent Contract",
        "",
        f"<!-- {AGENT_CONTRACT_MARKER}: {payload['version']} -->",
        "",
        "This file is generated by Switchboard and is the shared contract for enabled agent tools.",
        "",
        f"- Mode: `{payload.get('mode', 'local')}`",
        f"- Enabled entrypoints: `{', '.join(payload.get('enabled_entrypoints', []))}`",
        f"- Inherited from: `{payload.get('inherited_from') or 'local node'}`",
        "",
        "## Principles",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["principles"])
    lines.extend(["", "## Canonical Update Gate", ""])
    lines.extend(f"- {item}" for item in payload["canonical_update_gate"])
    lines.extend(
        [
            "",
            "## Tool Files",
            "",
            "- Codex and generic agents read `AGENTS.md` when the `agents` entrypoint is enabled.",
            "- Claude Code reads `CLAUDE.md` only when the `claude` entrypoint is enabled.",
            "- Gemini CLI reads `GEMINI.md` only when the `gemini` entrypoint is enabled.",
            "- Qwen Code reads `QWEN.md` only when the `qwen` entrypoint is enabled.",
            "- opencode reads `opencode.json` only when the `opencode` entrypoint is enabled.",
            "",
        ]
    )
    return "\n".join(lines)


def _agent_entrypoint_text(tool_name: str, contract_path: str = "switchboard/core/agent-contract.md") -> str:
    return (
        f"# Switchboard {tool_name} Instructions\n\n"
        f"<!-- {AGENT_CONTRACT_MARKER}: {AGENT_CONTRACT_VERSION} -->\n\n"
        f"Read `{contract_path}` before acting.\n\n"
        "Hard rules:\n"
        "- Read back Pratik's request before acting.\n"
        "- Ask in simple English if intent is unclear.\n"
        "- Make the smallest useful change and touch only required files.\n"
        "- Keep output short; no ceremony.\n"
        "- Never delete for cleanup; move or zip instead.\n"
        "- A Switchboard update is incomplete until task ledger, scope check, snapshot, and `verify-update` are done.\n"
    )


def _claude_entrypoint_text(contract_path: str = "switchboard/core/agent-contract.md") -> str:
    return (
        "# Switchboard Claude Code Instructions\n\n"
        f"<!-- {AGENT_CONTRACT_MARKER}: {AGENT_CONTRACT_VERSION} -->\n\n"
        f"@{contract_path}\n\n"
        "Claude-specific rule: do not create extra handoff markdown files such as `NOTE_FOR_GPT.md`; use `switchboard/local/tasks-completed.md`.\n"
    )


def _opencode_agent_text() -> str:
    return (
        "---\n"
        "description: Switchboard contract gate for project updates\n"
        "mode: subagent\n"
        "permission:\n"
        "  edit: ask\n"
        "  bash: ask\n"
        "---\n\n"
        f"<!-- {AGENT_CONTRACT_MARKER}: {AGENT_CONTRACT_VERSION} -->\n\n"
        "Read `switchboard/core/agent-contract.md`. Validate that the latest Switchboard update includes the task ledger entry, scope check, snapshot, and verify-update result.\n"
    )


def _write_managed_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="replace")
        if AGENT_CONTRACT_MARKER not in existing:
            return "preserved_unmanaged"
    path.write_text(content, encoding="utf-8")
    return "written"


def _merge_unique_strings(existing: Any, additions: list[str]) -> list[str]:
    values = existing if isinstance(existing, list) else ([existing] if isinstance(existing, str) else [])
    merged = [str(item) for item in values if str(item).strip()]
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


def _merge_context_settings(path: Path, filename: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return "preserved_invalid_json"
        if isinstance(existing, dict):
            payload = existing
    context = payload.get("context")
    if not isinstance(context, dict):
        context = {}
    context["fileName"] = _merge_unique_strings(context.get("fileName"), [filename])
    context["includeDirectories"] = _merge_unique_strings(context.get("includeDirectories"), ["switchboard/core"])
    context["loadFromIncludeDirectories"] = True
    payload["context"] = context
    _write_json(path, payload)
    return "written"


def _merge_opencode_config(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return "preserved_invalid_json"
        if isinstance(existing, dict):
            payload = existing
    payload.setdefault("$schema", "https://opencode.ai/config.json")
    payload["instructions"] = _merge_unique_strings(payload.get("instructions"), ["./switchboard/core/agent-contract.md"])
    permission = payload.get("permission")
    if not isinstance(permission, dict):
        permission = {}
    existing_bash = permission.get("bash", "ask")
    bash_rules = existing_bash if isinstance(existing_bash, dict) else {"*": existing_bash}
    bash_rules = {
        **bash_rules,
        "rm *": "deny",
        "rm -rf *": "deny",
        "git reset --hard *": "deny",
        "git checkout -- *": "deny",
    }
    permission["bash"] = bash_rules
    payload["permission"] = permission
    _write_json(path, payload)
    return "written"


def _write_agent_contract_files(
    project_root: Path,
    service_id: str,
    display_name: str,
    project_principles: list[str] | None = None,
    enabled_entrypoints: list[str] | None = None,
    inherited_from: Path | None = None,
) -> dict[str, str]:
    paths = node_paths(project_root)
    enabled = _normalize_agent_entrypoints(enabled_entrypoints)
    inherited_path = ""
    contract_path = "switchboard/core/agent-contract.md"
    if inherited_from is not None and inherited_from.resolve() != project_root.resolve():
        inherited_path = str(inherited_from / NODE_DIR_NAME / CORE_DIR_NAME / "agent-contract.md")
        contract_path = inherited_path
    payload = _agent_contract_payload(service_id, display_name, project_principles, enabled, inherited_path)
    results: dict[str, str] = {}
    if inherited_path:
        results["agent_contract_md"] = "manager_inherited"
        results["agent_contract_json"] = "manager_inherited"
    else:
        results["agent_contract_md"] = _write_managed_text(paths["agent_contract_md"], _agent_contract_markdown(payload))
        results["agent_contract_json"] = "written"
        _write_json(paths["agent_contract_json"], payload)
    if "agents" in enabled:
        results["AGENTS.md"] = _write_managed_text(paths["agents_md"], _agent_entrypoint_text("Agent", contract_path))
    if "claude" in enabled:
        results["CLAUDE.md"] = _write_managed_text(paths["claude_md"], _claude_entrypoint_text(contract_path))
    if "gemini" in enabled:
        results["GEMINI.md"] = _write_managed_text(paths["gemini_md"], _agent_entrypoint_text("Gemini CLI", contract_path))
        results[".gemini/settings.json"] = _merge_context_settings(paths["gemini_settings"], "GEMINI.md")
    if "qwen" in enabled:
        results["QWEN.md"] = _write_managed_text(paths["qwen_md"], _agent_entrypoint_text("Qwen Code", contract_path))
        results[".qwen/settings.json"] = _merge_context_settings(paths["qwen_settings"], "QWEN.md")
    if "opencode" in enabled:
        results[".opencode/agents/switchboard.md"] = _write_managed_text(paths["opencode_agent"], _opencode_agent_text())
        results["opencode.json"] = _merge_opencode_config(paths["opencode_config"])
    return results


def _tasks_completed_template() -> str:
    return (
        "# Tasks Completed\n\n"
        "Use one entry per meaningful update.\n\n"
        "Required fields:\n"
        "- heading: `## <ISO timestamp> | <title>`\n"
        "- `Tags:` using only `task`, `handoff`, `runbook`, `decision`, `scope`\n"
        "- `Summary:`\n"
        "- `Changed Paths:` comma-separated\n"
        "- `Agent:`\n"
        "- `Tool:`\n"
        "- `Read Back:` one short sentence\n"
        "- `Scope Check:` one short sentence\n"
        "- optional `Version:`\n"
        "- optional `Readme:` markdown block\n"
        "- optional `API:` markdown block\n"
        "- optional `Changelog:` markdown block\n"
        "- optional `Notes:` lines\n"
        "- optional `Scope Entries:` lines in `kind | path_type | path` format\n"
        "- optional `Runtime:` lines for ports, health check, and run command hint\n\n"
        "Example format:\n\n"
        "```md\n"
        "    ## 2026-04-01T12:00:00+00:00 | Example update\n"
        "    - Tags: task, handoff\n"
        "    - Summary: Standardized the project docs.\n"
        "    - Changed Paths: switchboard/core/README.md, switchboard/local/tasks-completed.md\n"
        "    - Agent: Codex\n"
        "    - Tool: codex-cli\n"
        "    - Read Back: Restated the request before editing.\n"
        "    - Scope Check: Project shape did not change; existing scope remains valid.\n"
        "    - Version: 1.1\n"
        "    - Readme:\n"
        "      ## Overview\n"
        "      Standardized the project docs.\n"
        "    - API:\n"
        "      ## Surface\n"
        "      Added `/health`.\n"
        "    - Changelog:\n"
        "      - Standardized the project docs.\n"
        "    - Notes:\n"
        "      - Added the first standard handoff.\n"
        "    - Runtime:\n"
        f"      - expected_ports: {DEFAULT_NODE_PORT}\n"
        f"      - healthcheck_command: curl http://127.0.0.1:{DEFAULT_NODE_PORT}/api/health\n"
        "```\n"
    )


def _node_start_script(project_root: Path) -> str:
    return f"""#!/bin/bash
set -euo pipefail

PROJECT_ROOT="{project_root}"
DEFAULT_HOST="127.0.0.1"
DEFAULT_PORT="$(python3 - <<'PY'
import json
from pathlib import Path

manifest_path = Path(r"{project_root}") / "switchboard" / "node.manifest.json"
default_port = {DEFAULT_NODE_PORT}
try:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    value = payload.get("runtime_port", default_port)
    print(int(value))
except Exception:
    print(default_port)
PY
)"

echo "Switchboard Node"
echo "Project root: $PROJECT_ROOT"
printf "Port [$DEFAULT_PORT]: "
read -r PORT_INPUT
PORT="${{PORT_INPUT:-$DEFAULT_PORT}}"
printf "Host [$DEFAULT_HOST]: "
read -r HOST_INPUT
HOST="${{HOST_INPUT:-$DEFAULT_HOST}}"

switchboard node start --project-root "$PROJECT_ROOT" --host "$HOST" --port "$PORT"
switchboard node status --project-root "$PROJECT_ROOT" --port "$PORT"
echo "Logs: $PROJECT_ROOT/switchboard/runtime/node.log"
"""


def _scope_entry_defaults(path: str, kind: str) -> dict[str, Any]:
    candidate = Path(path)
    path_type = "glob" if any(token in path for token in ("*", "?", "[")) else ("dir" if candidate.suffix == "" else "file")
    return {
        "kind": kind,
        "path": path,
        "path_type": path_type,
        "source": "node_manifest",
        "enabled": True,
    }


def _evidence_defaults(service_id: str, project_root: Path, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest or {}
    repo_paths = manifest.get("repo_paths", [str(project_root)])
    docs_paths = manifest.get("docs_paths", [])
    log_paths = manifest.get("log_paths", [])
    exclude_patterns = manifest.get("exclude_patterns", [])

    scope_entries = [_scope_entry_defaults(path, "repo") for path in repo_paths]
    scope_entries.extend(_scope_entry_defaults(path, "doc") for path in docs_paths)
    scope_entries.extend(_scope_entry_defaults(path, "log") for path in log_paths)
    scope_entries.extend(
        {
            "kind": "exclude",
            "path": path,
            "path_type": "glob",
            "source": "node_manifest",
            "enabled": True,
        }
        for path in exclude_patterns
    )
    return {
        "generated": utc_now_iso(),
        "service_id": manifest.get("service_id", service_id),
        "project_root": str(project_root),
        "scope_entries": scope_entries,
        "scope_updates": [],
    }


def load_pull_bundle_history(project_root: str | Path) -> dict[str, Any]:
    paths = node_paths(Path(project_root).resolve())
    return _read_json(paths["pull_bundle_history"], {"generated": "", "bundles": []})


def _manager_id(manager_root: Path) -> str:
    digest = hashlib.sha1(str(manager_root).encode("utf-8")).hexdigest()[:10]
    return f"manager-{digest}"


def _manager_base_manifest(manager_root: Path, existing: dict[str, Any] | None = None, runtime_port: int = DEFAULT_NODE_PORT) -> dict[str, Any]:
    existing = existing or {}
    return {
        "mode": "manager",
        "manager_id": existing.get("manager_id", _manager_id(manager_root)),
        "manager_root": str(manager_root),
        "runtime_port": int(existing.get("runtime_port", runtime_port) or runtime_port),
        "managed_roots": existing.get("managed_roots", []),
        "design_principles": _effective_principles(_normalize_principles(existing.get("design_principles", {}))),
        "updated_at": utc_now_iso(),
    }


def _read_update_gate_status(project_root: Path) -> str:
    paths = node_paths(project_root)
    payload = _read_json(paths["update_gate"], {}) if paths["update_gate"].exists() else {}
    return str(payload.get("status", "not_run") or "not_run")


def _manager_root_record(project_root: Path, root_id: str | None = None, role: str = "minion", snapshot: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    if snapshot:
        snapshot_node(project_root)
    manifest = load_node_manifest(project_root)
    service_id = str(manifest.get("service_id") or slugify(project_root.name))
    return {
        "root_id": root_id or service_id,
        "project_root": str(project_root),
        "service_id": service_id,
        "display_name": str(manifest.get("display_name") or _default_display_name(service_id)),
        "role": role,
        "enabled": True,
        "last_seen_version": str(manifest.get("installed_version", "")),
        "manifest_updated_at": str(manifest.get("updated_at", "")),
        "verify_status": _read_update_gate_status(project_root),
        "design_principles": manifest.get("design_principles", _effective_principles()),
        "registered_at": utc_now_iso(),
    }


def _unique_root_id(existing_roots: list[dict[str, Any]], requested_root_id: str, project_root: Path) -> str:
    used = {str(item.get("root_id", "")) for item in existing_roots}
    if requested_root_id not in used:
        return requested_root_id
    for item in existing_roots:
        if str(item.get("root_id", "")) == requested_root_id and Path(str(item.get("project_root", ""))).resolve() == project_root.resolve():
            return requested_root_id
    digest = hashlib.sha1(str(project_root.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{requested_root_id}-{digest}"


def init_manager_node(manager_root: str | Path, project_roots: list[str | Path] | None = None, runtime_port: int = DEFAULT_NODE_PORT, snapshot: bool = False) -> dict[str, Any]:
    manager_root = Path(manager_root).resolve()
    manager_root.mkdir(parents=True, exist_ok=True)
    paths = node_paths(manager_root)
    paths["node_root"].mkdir(parents=True, exist_ok=True)
    if not paths["agent_contract_md"].exists() or not paths["manifest"].exists():
        install_node(manager_root, service_id=slugify(manager_root.name), display_name=_default_display_name(slugify(manager_root.name)))
    existing = _read_json(paths["manager_manifest"], {}) if paths["manager_manifest"].exists() else {}
    manifest = _manager_base_manifest(manager_root, existing, runtime_port=runtime_port)
    _write_json(paths["manager_manifest"], manifest)
    for root in project_roots or []:
        manifest = register_manager_root(manager_root, root, snapshot=snapshot)["manifest"]
    return {"manager_root": str(manager_root), "manifest_path": str(paths["manager_manifest"]), "manifest": manifest}


def register_manager_root(
    manager_root: str | Path,
    project_root: str | Path,
    root_id: str | None = None,
    role: str = "minion",
    snapshot: bool = True,
) -> dict[str, Any]:
    manager_root = Path(manager_root).resolve()
    project_root = Path(project_root).resolve()
    paths = node_paths(manager_root)
    if not paths["manager_manifest"].exists():
        init_manager_node(manager_root)
    manifest = load_manager_manifest(manager_root)
    roots = [dict(item) for item in manifest.get("managed_roots", []) if isinstance(item, dict)]
    record = _manager_root_record(project_root, root_id=root_id, role=role, snapshot=snapshot)
    record["root_id"] = _unique_root_id(roots, str(record["root_id"]), project_root)
    roots = [item for item in roots if Path(str(item.get("project_root", ""))).resolve() != project_root]
    roots.append(record)
    roots.sort(key=lambda item: str(item.get("root_id", "")))
    manifest["managed_roots"] = roots
    manifest["updated_at"] = utc_now_iso()
    _write_json(paths["manager_manifest"], manifest)
    return {"status": "ok", "record": record, "manifest": manifest}


def list_manager_roots(manager_root: str | Path) -> dict[str, Any]:
    manifest = load_manager_manifest(manager_root)
    return {"manager": manifest, "roots": manifest.get("managed_roots", [])}


def _manager_record_by_id(manager_root: str | Path, root_id: str) -> dict[str, Any]:
    manifest = load_manager_manifest(manager_root)
    for record in manifest.get("managed_roots", []):
        if isinstance(record, dict) and str(record.get("root_id", "")) == root_id:
            return record
    raise KeyError(f"Manager root not found: {root_id}")


def _manager_record_by_project_root(manager_root: str | Path, project_root: str | Path) -> dict[str, Any] | None:
    target = Path(project_root).resolve()
    manifest = load_manager_manifest(manager_root)
    for record in manifest.get("managed_roots", []):
        if not isinstance(record, dict):
            continue
        try:
            if Path(str(record.get("project_root", ""))).resolve() == target:
                return record
        except OSError:
            continue
    return None


def manager_root_manifest(manager_root: str | Path, root_id: str) -> dict[str, Any]:
    record = _manager_record_by_id(manager_root, root_id)
    project_root = Path(str(record["project_root"])).resolve()
    return {"root": record, "manifest": load_node_manifest(project_root)}


def manager_root_snapshot(manager_root: str | Path, root_id: str) -> dict[str, Any]:
    record = _manager_record_by_id(manager_root, root_id)
    project_root = Path(str(record["project_root"])).resolve()
    snapshot = snapshot_node(project_root)
    register_manager_root(manager_root, project_root, root_id=root_id, role=str(record.get("role", "minion")), snapshot=False)
    return {"root": _manager_record_by_id(manager_root, root_id), "snapshot": snapshot}


def manager_root_verify_update(manager_root: str | Path, root_id: str) -> dict[str, Any]:
    record = _manager_record_by_id(manager_root, root_id)
    project_root = Path(str(record["project_root"])).resolve()
    result = verify_node_update(project_root)
    register_manager_root(manager_root, project_root, root_id=root_id, role=str(record.get("role", "minion")), snapshot=False)
    return {"root": _manager_record_by_id(manager_root, root_id), "verify_update": result}


def manager_root_health(manager_root: str | Path, root_id: str) -> dict[str, Any]:
    record = _manager_record_by_id(manager_root, root_id)
    project_root = Path(str(record["project_root"])).resolve()
    manifest = load_node_manifest(project_root)
    return {
        "status": "ok",
        "mode": "manager-root",
        "root_id": root_id,
        "service_id": manifest.get("service_id", ""),
        "project_root": str(project_root),
        "version": __version__,
        "verify_status": _read_update_gate_status(project_root),
    }


def manager_all_root_health(manager_root: str | Path) -> dict[str, Any]:
    roots = list_manager_roots(manager_root)["roots"]
    results = []
    for record in roots:
        if not isinstance(record, dict) or not record.get("enabled", True):
            continue
        root_id = str(record.get("root_id", ""))
        try:
            results.append(manager_root_health(manager_root, root_id))
        except Exception as exc:
            results.append({"root_id": root_id, "status": "partial", "message": str(exc)})
    return {"status": "ok" if all(item.get("status") == "ok" for item in results) else "partial", "roots": results}


def manager_all_root_snapshot(manager_root: str | Path) -> dict[str, Any]:
    roots = list_manager_roots(manager_root)["roots"]
    results = []
    for record in roots:
        if not isinstance(record, dict) or not record.get("enabled", True):
            continue
        root_id = str(record.get("root_id", ""))
        try:
            results.append(manager_root_snapshot(manager_root, root_id))
        except Exception as exc:
            results.append({"root": record, "status": "partial", "message": str(exc)})
    return {"status": "ok" if all(item.get("snapshot", {}).get("manifest") for item in results) else "partial", "roots": results}


def manager_install_root(
    manager_root: str | Path,
    project_root: str | Path,
    root_id: str | None = None,
    role: str = "minion",
    service_id: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    installed = install_node(project_root, service_id=service_id, display_name=display_name, manager_root=manager_root)
    registered = register_manager_root(manager_root, project_root, root_id=root_id, role=role, snapshot=False)
    return {"status": "ok", "installed": installed, "registered": registered["record"]}


def normalize_manager_root(
    manager_root: str | Path,
    project_root: str | Path,
    root_id: str | None = None,
    role: str = "minion",
    service_id: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    manager_root = Path(manager_root).resolve()
    project_root = Path(project_root).resolve()
    if not node_paths(manager_root)["manager_manifest"].exists():
        init_manager_node(manager_root)

    existing_record = _manager_record_by_project_root(manager_root, project_root)
    selected_root_id = root_id or (str(existing_record.get("root_id", "")) if existing_record else None)
    selected_role = str(existing_record.get("role", role)) if existing_record else role

    if existing_record is None:
        install_result = manager_install_root(
            manager_root,
            project_root,
            root_id=selected_root_id,
            role=selected_role,
            service_id=service_id,
            display_name=display_name,
        )
    else:
        install_result = manager_upgrade_root(manager_root, selected_root_id or str(existing_record["root_id"]))

    normalized_root_id = str(install_result["registered"]["root_id"])
    snapshot = manager_root_snapshot(manager_root, normalized_root_id)
    verify = manager_root_verify_update(manager_root, normalized_root_id)
    status = str(verify.get("verify_update", {}).get("status") or "partial")
    archive = None
    if status == "ok":
        archive = manager_archive_old_scaffolding(manager_root, root_id=normalized_root_id)
    return {
        "status": status,
        "manager_root": str(manager_root),
        "project_root": str(project_root),
        "root_id": normalized_root_id,
        "install": install_result,
        "snapshot": snapshot,
        "verify_update": verify.get("verify_update", {}),
        "registered": verify.get("root", install_result["registered"]),
        "archive": archive,
    }


def manager_upgrade_root(manager_root: str | Path, root_id: str) -> dict[str, Any]:
    record = _manager_record_by_id(manager_root, root_id)
    project_root = Path(str(record["project_root"])).resolve()
    upgraded = upgrade_node(project_root, manager_root=manager_root)
    registered = register_manager_root(manager_root, project_root, root_id=root_id, role=str(record.get("role", "minion")), snapshot=False)
    return {"status": "ok", "upgraded": upgraded, "registered": registered["record"]}


def manager_all_root_normalize(manager_root: str | Path) -> dict[str, Any]:
    roots = list_manager_roots(manager_root)["roots"]
    results = []
    for record in roots:
        if not isinstance(record, dict) or not record.get("enabled", True):
            continue
        root_id = str(record.get("root_id", ""))
        project_root = str(record.get("project_root", ""))
        try:
            results.append(
                normalize_manager_root(
                    manager_root,
                    project_root,
                    root_id=root_id,
                    role=str(record.get("role", "minion")),
                    service_id=str(record.get("service_id") or "") or None,
                    display_name=str(record.get("display_name") or "") or None,
                )
            )
        except Exception as exc:
            results.append({"status": "partial", "root_id": root_id, "project_root": project_root, "message": str(exc)})
    return {"status": "ok" if all(item.get("status") == "ok" for item in results) else "partial", "roots": results}


def manager_all_root_upgrade(manager_root: str | Path) -> dict[str, Any]:
    roots = list_manager_roots(manager_root)["roots"]
    results = []
    for record in roots:
        if not isinstance(record, dict) or not record.get("enabled", True):
            continue
        root_id = str(record.get("root_id", ""))
        try:
            results.append(manager_upgrade_root(manager_root, root_id))
        except Exception as exc:
            results.append({"status": "partial", "root_id": root_id, "message": str(exc)})
    return {"status": "ok" if all(item.get("status") == "ok" for item in results) else "partial", "roots": results}


def manager_all_root_verify_update(manager_root: str | Path) -> dict[str, Any]:
    roots = list_manager_roots(manager_root)["roots"]
    results = []
    for record in roots:
        if not isinstance(record, dict) or not record.get("enabled", True):
            continue
        root_id = str(record.get("root_id", ""))
        try:
            results.append(manager_root_verify_update(manager_root, root_id))
        except Exception as exc:
            results.append({"root": record, "verify_update": {"status": "partial", "message": str(exc)}})
    ok = all(item.get("verify_update", {}).get("status") == "ok" for item in results)
    return {"status": "ok" if ok else "partial", "roots": results}


def manager_archive_old_scaffolding(manager_root: str | Path, root_id: str | None = None) -> dict[str, Any]:
    manager_root = Path(manager_root).resolve()
    archive_root = manager_root / NODE_DIR_NAME / "manager" / "archives" / f"{utc_now_iso().replace(':', '-')}--old-node-scaffolding"
    roots = list_manager_roots(manager_root)["roots"]
    selected = [
        record for record in roots
        if isinstance(record, dict)
        and record.get("enabled", True)
        and (root_id is None or str(record.get("root_id", "")) == root_id)
    ]
    if root_id is not None and not selected:
        raise KeyError(f"Manager root not found: {root_id}")
    moved: list[dict[str, Any]] = []
    for record in selected:
        project_root = Path(str(record["project_root"])).resolve()
        paths = node_paths(project_root)
        per_root_archive = archive_root / str(record.get("root_id", "root"))
        archive_keys = ["runtime", "start_script", "run_script"]
        if project_root != manager_root and str(record.get("role", "minion")) != "core":
            archive_keys.append("core")
        for key in archive_keys:
            source = paths[key]
            if not source.exists():
                moved.append({"root_id": record.get("root_id", ""), "source": str(source), "status": "missing"})
                continue
            target = per_root_archive / source.relative_to(project_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved.append({"root_id": record.get("root_id", ""), "source": str(source), "target": str(target), "status": "moved"})
    report = {
        "status": "ok",
        "generated": utc_now_iso(),
        "manager_root": str(manager_root),
        "archive_root": str(archive_root),
        "root_id": root_id or "",
        "moved": moved,
        "preserved": [
            "switchboard/core only on the manager/core root",
            "switchboard/local",
            "switchboard/evidence",
            "switchboard/node.manifest.json",
            "enabled root-level agent entrypoint files",
        ],
    }
    _write_json(archive_root / "archive-report.json", report)
    (archive_root / "archive-report.md").write_text(
        "# Switchboard Old Node Scaffolding Archive\n\n"
        f"- Generated: {report['generated']}\n"
        f"- Manager root: `{report['manager_root']}`\n"
        f"- Archive root: `{report['archive_root']}`\n"
        f"- Moved entries: {len([item for item in moved if item['status'] == 'moved'])}\n"
        "- Preserved canonical files: local, evidence, manifest, and enabled agent files. Minion core folders may move to manager archive because common rules are manager-owned.\n",
        encoding="utf-8",
    )
    return report


def manager_safe_action(manager_root: str | Path, action: str, root_id: str | None = None) -> dict[str, Any]:
    if action == "status":
        if root_id:
            return manager_root_health(manager_root, root_id)
        return manager_all_root_health(manager_root)
    if action == "snapshot":
        if root_id:
            return manager_root_snapshot(manager_root, root_id)
        return manager_all_root_snapshot(manager_root)
    if action in {"upgrade", "release-update"}:
        if root_id:
            return manager_upgrade_root(manager_root, root_id)
        return manager_all_root_upgrade(manager_root)
    if action == "verify-update":
        if root_id:
            return manager_root_verify_update(manager_root, root_id)
        return manager_all_root_verify_update(manager_root)
    if action == "archive-old-scaffolding":
        return manager_archive_old_scaffolding(manager_root, root_id=root_id)
    return {
        "status": "permission_limited",
        "message": "Only status, snapshot, upgrade, release-update, verify-update, and archive-old-scaffolding are allowed.",
        "action": action,
    }


def _manifest_payload(
    project_root: Path,
    service_id: str,
    display_name: str,
    existing: dict[str, Any] | None = None,
    manager_root: Path | None = None,
) -> dict[str, Any]:
    existing = existing or {}
    paths = node_paths(project_root)
    inherited_manager = manager_root is not None and manager_root.resolve() != project_root.resolve()
    docs_paths = existing.get(
        "docs_paths",
        [str(paths["local"]), str(paths["evidence"])] if inherited_manager else [str(paths["core"]), str(paths["local"]), str(paths["evidence"])],
    )
    if inherited_manager:
        docs_paths = [str(path) for path in docs_paths if not _is_switchboard_internal_path(str(path), project_root)]
    existing_contract = existing.get("agent_contract", {}) if isinstance(existing.get("agent_contract"), dict) else {}
    enabled_entrypoints = _normalize_agent_entrypoints(existing_contract.get("enabled_entrypoints"))
    return {
        "node_id": existing.get("node_id", _node_id(service_id, project_root)),
        "service_id": service_id,
        "display_name": display_name,
        "project_root": str(project_root),
        "mode": "node",
        "installed_version": __version__,
        "runtime_port": int(existing.get("runtime_port", DEFAULT_NODE_PORT) or DEFAULT_NODE_PORT),
        "repo_paths": existing.get("repo_paths", [str(project_root)]),
        "docs_paths": docs_paths,
        "log_paths": existing.get("log_paths", []),
        "exclude_patterns": existing.get("exclude_patterns", []),
        "runtime": existing.get(
            "runtime",
            {
                "expected_ports": [],
                "healthcheck_command": "",
                "run_command_hint": "",
                "monitoring_mode": "manual",
                "notes": "",
            },
        ),
        "managed_docs": _normalize_managed_docs(existing.get("managed_docs")),
        "bootstrap_version": existing.get("bootstrap_version", ""),
        "runtime_services": existing.get("runtime_services", []),
        "dependencies": existing.get("dependencies", []),
        "cross_dependencies": existing.get("cross_dependencies", []),
        "diagram": existing.get("diagram", ""),
        "design_principles": _effective_principles(_normalize_principles(existing.get("design_principles", {}))),
        "manager_root": str(manager_root) if manager_root is not None else existing.get("manager_root", ""),
        "agent_contract": {
            "version": AGENT_CONTRACT_VERSION,
            "mode": "manager_inherited" if inherited_manager else "local",
            "inherited_from": str(manager_root / NODE_DIR_NAME / CORE_DIR_NAME / "agent-contract.md") if inherited_manager else "",
            "enabled_entrypoints": enabled_entrypoints,
            "files": existing_contract.get("files", {}),
        },
        "installed_release": existing.get("installed_release", {}),
        "doc_index": existing.get("doc_index", {"generated": "", "docs": []}),
        "evidence_paths": {
            "completed_tasks": str(paths["completed_tasks_json"].relative_to(project_root)),
            "doc_index": str(paths["doc_index_json"].relative_to(project_root)),
            "repo_safety_history": str(paths["repo_safety_history"].relative_to(project_root)),
            "pull_bundle_history": str(paths["pull_bundle_history"].relative_to(project_root)),
            "scope_snapshot": str(paths["scope_snapshot"].relative_to(project_root)),
            "update_gate": str(paths["update_gate"].relative_to(project_root)),
        },
        "updated_at": utc_now_iso(),
    }


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _strip_continuation_prefix(raw_line: str) -> str:
    if raw_line.startswith("  "):
        return raw_line[2:]
    return raw_line.strip()


def _join_markdown_lines(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def _normalize_scope_lines(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in lines:
        payload = line.strip()
        if payload.startswith("- "):
            payload = payload[2:].strip()
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 3:
            continue
        kind, path_type, path = parts[:3]
        enabled = True
        if len(parts) >= 4:
            enabled = parts[3].lower() not in {"false", "0", "no", "disabled"}
        entries.append(
            {
                "kind": kind,
                "path_type": path_type,
                "path": path,
                "enabled": enabled,
                "source": "tasks_completed",
            }
        )
    return entries


def _normalize_runtime_lines(lines: list[str]) -> dict[str, Any]:
    runtime = {
        "expected_ports": [],
        "healthcheck_command": "",
        "run_command_hint": "",
        "monitoring_mode": "manual",
        "notes": "",
    }
    notes: list[str] = []
    for raw in lines:
        payload = raw.strip()
        if payload.startswith("- "):
            payload = payload[2:].strip()
        if ":" not in payload:
            if payload:
                notes.append(payload)
            continue
        key, value = payload.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "expected_ports":
            runtime["expected_ports"] = [int(token.strip()) for token in value.split(",") if token.strip().isdigit()]
        elif key == "healthcheck_command":
            runtime["healthcheck_command"] = value
        elif key == "run_command_hint":
            runtime["run_command_hint"] = value
        elif key == "monitoring_mode" and value in {"manual", "detect", "node_managed"}:
            runtime["monitoring_mode"] = value
        elif key == "notes":
            notes.append(value)
    runtime["notes"] = "\n".join(note for note in notes if note).strip()
    return runtime


def _normalize_runtime_service_lines(lines: list[str]) -> list[dict[str, Any]]:
    """Parse pipe-delimited runtime service lines: kind | name | host | port | purpose | health_path"""
    services: list[dict[str, Any]] = []
    for raw in lines:
        payload = raw.strip()
        if payload.startswith("- "):
            payload = payload[2:].strip()
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 2:
            continue
        port_str = parts[3].strip() if len(parts) > 3 else ""
        port = int(port_str) if port_str.isdigit() else None
        services.append({
            "name": parts[1] if len(parts) > 1 else parts[0],
            "host": parts[2] if len(parts) > 2 else "",
            "port": port,
            "purpose": parts[4] if len(parts) > 4 else "",
            "health_path": parts[5] if len(parts) > 5 else "",
            "owner": parts[6] if len(parts) > 6 else "",
        })
    return services


def _normalize_dependency_lines(lines: list[str]) -> list[dict[str, Any]]:
    """Parse pipe-delimited dependency lines: kind | name | host | port | notes"""
    deps: list[dict[str, Any]] = []
    for raw in lines:
        payload = raw.strip()
        if payload.startswith("- "):
            payload = payload[2:].strip()
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 2:
            continue
        port_str = parts[3].strip() if len(parts) > 3 else ""
        port = int(port_str) if port_str.isdigit() else None
        if port_str.lower() in ("null", "none", ""):
            port = None
        deps.append({
            "kind": parts[0] if len(parts) > 0 else "service",
            "name": parts[1] if len(parts) > 1 else "",
            "host": parts[2] if len(parts) > 2 else "",
            "port": port,
            "notes": parts[4] if len(parts) > 4 else "",
        })
    return deps


def parse_tasks_completed(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^##\s+(.+?)\s*\|\s*(.+)$", text, flags=re.MULTILINE))
    entries: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]
        timestamp = match.group(1).strip()
        title = match.group(2).strip()
        tags: list[str] = []
        summary = ""
        version = ""
        changed_paths: list[str] = []
        task_id = ""
        agent = ""
        tool = ""
        read_back = ""
        scope_check = ""
        bootstrap_version = ""
        sections: dict[str, list[str]] = {
            "notes": [],
            "scope": [],
            "runtime": [],
            "readme": [],
            "api": [],
            "changelog": [],
            "runtime_services": [],
            "dependencies": [],
            "cross_dependencies": [],
            "diagram": [],
        }
        current_section: str | None = None

        for raw_line in block.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped and current_section in {"notes", "readme", "api", "changelog", "diagram"}:
                sections[current_section].append("")
                continue
            if not stripped:
                continue

            if line.startswith("- Tags:"):
                tags = [tag for tag in (item.strip().lower() for item in _split_csv(line.split(":", 1)[1])) if tag in ROUTING_TAGS]
                current_section = None
                continue
            if line.startswith("- Summary:"):
                summary = line.split(":", 1)[1].strip()
                current_section = None
                continue
            if line.startswith("- Changed Paths:"):
                changed_paths = _split_csv(line.split(":", 1)[1])
                current_section = None
                continue
            if line.startswith("- Version:"):
                version = line.split(":", 1)[1].strip()
                current_section = None
                continue
            if line.startswith("- Task ID:"):
                task_id = line.split(":", 1)[1].strip()
                current_section = None
                continue
            if line.startswith("- Agent:"):
                agent = line.split(":", 1)[1].strip()
                current_section = None
                continue
            if line.startswith("- Tool:"):
                tool = line.split(":", 1)[1].strip()
                current_section = None
                continue
            if line.startswith("- Read Back:"):
                read_back = line.split(":", 1)[1].strip()
                current_section = None
                continue
            if line.startswith("- Scope Check:"):
                scope_check = line.split(":", 1)[1].strip()
                current_section = None
                continue
            if line.startswith("- Bootstrap Version:"):
                bootstrap_version = line.split(":", 1)[1].strip()
                current_section = None
                continue

            next_section = None
            payload = ""
            if line.startswith("- Notes:"):
                next_section = "notes"
            elif line.startswith("- Scope Entries:"):
                next_section = "scope"
            elif line.startswith("- Runtime:"):
                next_section = "runtime"
            elif line.startswith("- Readme:"):
                next_section = "readme"
            elif line.startswith("- API:"):
                next_section = "api"
            elif line.startswith("- Changelog:"):
                next_section = "changelog"
            elif line.startswith("- Runtime Services:"):
                next_section = "runtime_services"
            elif line.startswith("- Dependencies:"):
                next_section = "dependencies"
            elif line.startswith("- Cross Dependencies:"):
                next_section = "cross_dependencies"
            elif line.startswith("- Diagram:"):
                next_section = "diagram"

            if next_section is not None:
                current_section = next_section
                payload = line.split(":", 1)[1].strip()
                if payload:
                    sections[current_section].append(payload)
                continue

            if current_section in sections:
                sections[current_section].append(_strip_continuation_prefix(raw_line))

        entries.append(
            {
                "timestamp": timestamp,
                "title": title,
                "tags": tags,
                "version": version,
                "summary": summary or title,
                "changed_paths": changed_paths,
                "task_id": task_id or None,
                "agent": agent,
                "tool": tool,
                "read_back": read_back,
                "scope_check": scope_check,
                "bootstrap_version": bootstrap_version,
                "notes": [line for line in sections["notes"] if line.strip()],
                "scope_entries": _normalize_scope_lines(sections["scope"]),
                "runtime": _normalize_runtime_lines(sections["runtime"]),
                "runtime_services": _normalize_runtime_service_lines(sections["runtime_services"]),
                "dependencies": _normalize_dependency_lines(sections["dependencies"]),
                "cross_dependencies": _normalize_dependency_lines(sections["cross_dependencies"]),
                "diagram": _join_markdown_lines(sections["diagram"]),
                "readme": _join_markdown_lines(sections["readme"]),
                "api": _join_markdown_lines(sections["api"]),
                "changelog": _join_markdown_lines(sections["changelog"]),
            }
        )
    return entries


def _render_multiline_block(label: str, content: str) -> list[str]:
    if not content.strip():
        return []
    lines = [f"- {label}:"]
    lines.extend(f"  {line}" if line else "" for line in content.splitlines())
    return lines


def _render_entry(entry: dict[str, Any]) -> str:
    lines = [
        f"## {entry['timestamp']} | {entry['title']}",
    ]
    if entry.get("task_id"):
        lines.append(f"- Task ID: {entry['task_id']}")
    lines.append(f"- Tags: {', '.join(entry['tags'])}" if entry.get("tags") else "- Tags: task")
    lines.append(f"- Summary: {entry['summary']}")
    lines.append(f"- Changed Paths: {', '.join(entry['changed_paths'])}" if entry.get("changed_paths") else "- Changed Paths:")
    if entry.get("agent"):
        lines.append(f"- Agent: {entry['agent']}")
    if entry.get("tool"):
        lines.append(f"- Tool: {entry['tool']}")
    if entry.get("read_back"):
        lines.append(f"- Read Back: {entry['read_back']}")
    if entry.get("scope_check"):
        lines.append(f"- Scope Check: {entry['scope_check']}")
    if entry.get("version"):
        lines.append(f"- Version: {entry['version']}")
    if entry.get("bootstrap_version"):
        lines.append(f"- Bootstrap Version: {entry['bootstrap_version']}")
    lines.extend(_render_multiline_block("Readme", entry.get("readme", "")))
    lines.extend(_render_multiline_block("API", entry.get("api", "")))
    lines.extend(_render_multiline_block("Changelog", entry.get("changelog", "")))
    if entry.get("notes"):
        lines.append("- Notes:")
        for note in entry["notes"]:
            lines.append(f"  - {note}")
    if entry.get("scope_entries"):
        lines.append("- Scope Entries:")
        for scope_entry in entry["scope_entries"]:
            enabled = "true" if scope_entry.get("enabled", True) else "false"
            lines.append(
                f"  - {scope_entry['kind']} | {scope_entry['path_type']} | {scope_entry['path']} | {enabled}"
            )
    runtime = entry.get("runtime") or {}
    if any(runtime.get(key) for key in ("expected_ports", "healthcheck_command", "run_command_hint", "notes")):
        lines.append("- Runtime:")
        if runtime.get("expected_ports"):
            lines.append(f"  - expected_ports: {', '.join(str(port) for port in runtime['expected_ports'])}")
        if runtime.get("healthcheck_command"):
            lines.append(f"  - healthcheck_command: {runtime['healthcheck_command']}")
        if runtime.get("run_command_hint"):
            lines.append(f"  - run_command_hint: {runtime['run_command_hint']}")
        lines.append(f"  - monitoring_mode: {runtime.get('monitoring_mode', 'manual')}")
        if runtime.get("notes"):
            lines.append(f"  - notes: {runtime['notes']}")
    if entry.get("runtime_services"):
        lines.append("- Runtime Services:")
        for svc in entry["runtime_services"]:
            port_str = str(svc.get("port", "")) if svc.get("port") is not None else ""
            lines.append(f"  - service | {svc['name']} | {svc.get('host', '')} | {port_str} | {svc.get('purpose', '')} | {svc.get('health_path', '')}")
    if entry.get("dependencies"):
        lines.append("- Dependencies:")
        for dep in entry["dependencies"]:
            port_str = str(dep.get("port", "")) if dep.get("port") is not None else "null"
            lines.append(f"  - {dep.get('kind', 'service')} | {dep['name']} | {dep.get('host', '')} | {port_str} | {dep.get('notes', '')}")
    if entry.get("cross_dependencies"):
        lines.append("- Cross Dependencies:")
        for dep in entry["cross_dependencies"]:
            port_str = str(dep.get("port", "")) if dep.get("port") is not None else "null"
            lines.append(f"  - {dep.get('kind', 'service')} | {dep['name']} | {dep.get('host', '')} | {port_str} | {dep.get('notes', '')}")
    if entry.get("diagram"):
        lines.append("- Diagram:")
        for diagram_line in entry["diagram"].splitlines():
            lines.append(f"  {diagram_line}" if diagram_line else "")
    return "\n".join(lines)


def _render_section(title: str, entries: list[dict[str, Any]], empty_message: str) -> str:
    if not entries:
        return f"# {title}\n\n{empty_message}\n"
    body = "\n\n".join(_render_entry(entry) for entry in entries)
    return f"# {title}\n\n{body}\n"


def _latest_version(tasks: list[dict[str, Any]]) -> str:
    for entry in reversed(tasks):
        if entry.get("version"):
            return str(entry["version"])
    return ""


def _render_root_readme(manifest: dict[str, Any], runtime: dict[str, Any], tasks: list[dict[str, Any]]) -> str:
    version = _latest_version(tasks)
    latest_blocks = [entry for entry in tasks if entry.get("readme")]
    latest_block = latest_blocks[-1]["readme"] if latest_blocks else ""
    ports = ", ".join(str(port) for port in runtime.get("expected_ports", [])) or "none"
    health = runtime.get("healthcheck_command") or "Not configured"
    run_command = runtime.get("run_command_hint") or "Not configured"
    title = manifest.get("display_name") or manifest.get("service_id") or "Project"
    return (
        f"# {title}\n\n"
        "This file is framework-managed by Switchboard.\n\n"
        "## Identity\n\n"
        f"- Service id: `{manifest.get('service_id', '')}`\n"
        f"- Node id: `{manifest.get('node_id', '')}`\n"
        f"- Project root: `{manifest.get('project_root', '')}`\n"
        f"- Version: `{version or 'unversioned'}`\n\n"
        "## Runtime\n\n"
        f"- Monitoring mode: `{runtime.get('monitoring_mode', 'manual')}`\n"
        f"- Expected ports: `{ports}`\n"
        f"- Health check: `{health}`\n"
        f"- Run command hint: `{run_command}`\n\n"
        "## Project Notes\n\n"
        f"{latest_block or 'No `Readme` block has been recorded in `switchboard/local/tasks-completed.md` yet.'}\n"
    )


def _render_root_api(manifest: dict[str, Any], runtime: dict[str, Any], scope_snapshot: dict[str, Any], tasks: list[dict[str, Any]]) -> str:
    version = _latest_version(tasks)
    api_blocks = [entry for entry in tasks if entry.get("api")]
    latest_block = api_blocks[-1]["api"] if api_blocks else ""
    scope_count = len(scope_snapshot.get("scope_entries", []))
    return (
        f"# API\n\n"
        "This file is framework-managed by Switchboard.\n\n"
        "## Metadata\n\n"
        f"- Service id: `{manifest.get('service_id', '')}`\n"
        f"- Version: `{version or 'unversioned'}`\n"
        f"- Scope entries: `{scope_count}`\n"
        f"- Monitoring mode: `{runtime.get('monitoring_mode', 'manual')}`\n"
        f"- Health check: `{runtime.get('healthcheck_command') or 'Not configured'}`\n"
        f"- Run command hint: `{runtime.get('run_command_hint') or 'Not configured'}`\n\n"
        "## API Notes\n\n"
        f"{latest_block or 'No `API` block has been recorded in `switchboard/local/tasks-completed.md` yet.'}\n"
    )


def _render_root_changelog(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "# CHANGELOG\n\nNo entries captured yet.\n"
    lines = ["# CHANGELOG", ""]
    for entry in reversed(tasks):
        heading = entry.get("version") or entry["timestamp"]
        lines.append(f"## {heading} | {entry['title']}")
        lines.append("")
        lines.append(f"- Timestamp: {entry['timestamp']}")
        lines.append(f"- Summary: {entry['summary']}")
        if entry.get("changed_paths"):
            lines.append(f"- Changed Paths: {', '.join(entry['changed_paths'])}")
        changelog_block = str(entry.get("changelog") or "").strip()
        if changelog_block:
            lines.append("- Details:")
            for line in changelog_block.splitlines():
                lines.append(f"  {line}" if line else "")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _contributors_for_doc(doc_id: str, tasks: list[dict[str, Any]]) -> list[str]:
    contributors: list[str] = []
    for entry in tasks:
        if doc_id == "handoff" and "handoff" in entry.get("tags", []):
            contributors.append(entry["timestamp"])
        elif doc_id == "runbook" and "runbook" in entry.get("tags", []):
            contributors.append(entry["timestamp"])
        elif doc_id == "approach_history" and "decision" in entry.get("tags", []):
            contributors.append(entry["timestamp"])
        elif doc_id == "readme" and entry.get("readme"):
            contributors.append(entry["timestamp"])
        elif doc_id == "api" and entry.get("api"):
            contributors.append(entry["timestamp"])
        elif doc_id == "changelog":
            contributors.append(entry["timestamp"])
        elif doc_id in {"doc_index_md", "doc_index_json"}:
            contributors.append(entry["timestamp"])
    return contributors


def _render_doc_index_markdown(doc_index: dict[str, Any]) -> str:
    lines = [
        "# Doc Index",
        "",
        f"- Generated: `{doc_index.get('generated', '')}`",
        "",
        "| Doc | Path | Enabled | Generated | Contributors |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in doc_index.get("docs", []):
        contributors = ", ".join(entry.get("contributor_timestamps", [])) or "none"
        lines.append(
            f"| `{entry.get('doc_id', '')}` | `{entry.get('path', '')}` | "
            f"{'yes' if entry.get('enabled') else 'no'} | "
            f"`{entry.get('generated_at') or ''}` | {contributors} |"
        )
    lines.append("")
    return "\n".join(lines)


def install_node(
    project_root: str | Path,
    service_id: str | None = None,
    display_name: str | None = None,
    manager_root: str | Path | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    manager_root_path = Path(manager_root).resolve() if manager_root is not None else None
    project_root.mkdir(parents=True, exist_ok=True)
    paths = node_paths(project_root)
    existing = _read_json(paths["manifest"], {}) if paths["manifest"].exists() else {}
    service_id = service_id or existing.get("service_id") or slugify(project_root.name)
    display_name = display_name or existing.get("display_name") or _default_display_name(service_id)

    for key in ("node_root", "core", "local", "evidence"):
        paths[key].mkdir(parents=True, exist_ok=True)

    manifest = _manifest_payload(project_root, service_id, display_name, existing, manager_root=manager_root_path)
    _write_json(paths["manifest"], manifest)

    inherited_contract = manager_root_path is not None and manager_root_path.resolve() != project_root.resolve()
    if not inherited_contract:
        for filename, content in _core_templates(service_id, display_name).items():
            _write_text(paths["core"] / filename, content)
    principle_layers = manifest.get("design_principles", _effective_principles())
    agent_contract = manifest.get("agent_contract", {}) if isinstance(manifest.get("agent_contract"), dict) else {}
    agent_contract_files = _write_agent_contract_files(
        project_root,
        service_id,
        display_name,
        principle_layers.get("project", []),
        agent_contract.get("enabled_entrypoints"),
        manager_root_path,
    )
    manifest["agent_contract"] = {
        "version": AGENT_CONTRACT_VERSION,
        "mode": "manager_inherited" if inherited_contract else "local",
        "inherited_from": str(manager_root_path / NODE_DIR_NAME / CORE_DIR_NAME / "agent-contract.md") if inherited_contract and manager_root_path else "",
        "enabled_entrypoints": _normalize_agent_entrypoints(agent_contract.get("enabled_entrypoints")),
        "files": agent_contract_files,
    }
    _write_json(paths["manifest"], manifest)

    _write_executable(paths["start_script"], _node_start_script(project_root))
    _write_executable(paths["run_script"], _node_start_script(project_root))

    _write_text_if_missing(paths["tasks_completed"], _tasks_completed_template())
    _write_text_if_missing(paths["handoff"], "# Control Center Handoff\n\nNo handoff entries yet.\n")
    _write_text_if_missing(paths["runbook"], "# Runbook\n\nNo runbook entries yet.\n")
    _write_text_if_missing(paths["approach_history"], "# Approach History\n\nNo decision entries yet.\n")
    _write_text_if_missing(paths["doc_index_md"], "# Doc Index\n\nNo managed-doc index generated yet.\n")

    if not paths["completed_tasks_json"].exists():
        _write_json(paths["completed_tasks_json"], {"generated": "", "service_id": service_id, "project_root": str(project_root), "tasks": []})
    if not paths["doc_index_json"].exists():
        _write_json(paths["doc_index_json"], {"generated": "", "service_id": service_id, "project_root": str(project_root), "docs": []})
    if not paths["repo_safety_history"].exists():
        _write_json(paths["repo_safety_history"], {"generated": "", "checks": []})
    if not paths["pull_bundle_history"].exists():
        _write_json(paths["pull_bundle_history"], {"generated": "", "bundles": []})
    if not paths["scope_snapshot"].exists():
        _write_json(paths["scope_snapshot"], _evidence_defaults(service_id, project_root, manifest))
    if not paths["update_gate"].exists():
        _write_json(paths["update_gate"], {"generated": "", "status": "not_run", "checks": []})

    snapshot = snapshot_node(project_root)
    return {"project_root": str(project_root), "node_root": str(paths["node_root"]), "manifest": snapshot["manifest"]}


def upgrade_node(project_root: str | Path, manager_root: str | Path | None = None) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    paths = node_paths(project_root)
    existing = _read_json(paths["manifest"], {})
    if not existing:
        return install_node(project_root)
    selected_manager_root = manager_root if manager_root is not None else (existing.get("manager_root") or None)
    return install_node(project_root, existing.get("service_id"), existing.get("display_name"), manager_root=selected_manager_root)


def snapshot_node(project_root: str | Path) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    paths = node_paths(project_root)
    if not paths["manifest"].exists():
        install_node(project_root)

    manifest = load_node_manifest(project_root)
    service_id = str(manifest.get("service_id") or slugify(project_root.name))
    display_name = str(manifest.get("display_name") or _default_display_name(service_id))
    manifest["installed_version"] = __version__
    principle_layers = _effective_principles(_normalize_principles(manifest.get("design_principles", {})))
    manifest["design_principles"] = principle_layers
    agent_contract = manifest.get("agent_contract", {}) if isinstance(manifest.get("agent_contract"), dict) else {}
    inherited_from = str(agent_contract.get("inherited_from") or "").strip()
    inherited_manager_root = Path(str(manifest.get("manager_root", ""))).resolve() if manifest.get("manager_root") else None
    if inherited_from and inherited_manager_root and inherited_manager_root != project_root:
        agent_contract_files = _write_agent_contract_files(
            project_root,
            service_id,
            display_name,
            principle_layers.get("project", []),
            agent_contract.get("enabled_entrypoints"),
            inherited_manager_root,
        )
    else:
        agent_contract_files = _write_agent_contract_files(
            project_root,
            service_id,
            display_name,
            principle_layers.get("project", []),
            agent_contract.get("enabled_entrypoints"),
            None,
        )
    manifest["agent_contract"] = {
        "version": AGENT_CONTRACT_VERSION,
        "mode": "manager_inherited" if inherited_from else "local",
        "inherited_from": inherited_from,
        "enabled_entrypoints": _normalize_agent_entrypoints(agent_contract.get("enabled_entrypoints")),
        "files": agent_contract_files,
    }
    evidence_paths = manifest.setdefault("evidence_paths", {})
    evidence_paths.update(
        {
            "completed_tasks": str(paths["completed_tasks_json"].relative_to(project_root)),
            "doc_index": str(paths["doc_index_json"].relative_to(project_root)),
            "repo_safety_history": str(paths["repo_safety_history"].relative_to(project_root)),
            "pull_bundle_history": str(paths["pull_bundle_history"].relative_to(project_root)),
            "scope_snapshot": str(paths["scope_snapshot"].relative_to(project_root)),
            "update_gate": str(paths["update_gate"].relative_to(project_root)),
        }
    )
    tasks = parse_tasks_completed(paths["tasks_completed"])
    tasks_json = {
        "generated": utc_now_iso(),
        "service_id": manifest["service_id"],
        "project_root": str(project_root),
        "tasks": tasks,
    }
    _write_json(paths["completed_tasks_json"], tasks_json)

    managed_docs = _normalize_managed_docs(manifest.get("managed_docs"))
    managed_docs_by_id = _managed_doc_by_id(managed_docs)
    handoff_entries = [entry for entry in tasks if "handoff" in entry.get("tags", [])]
    runbook_entries = [entry for entry in tasks if "runbook" in entry.get("tags", [])]
    decision_entries = [entry for entry in tasks if "decision" in entry.get("tags", [])]
    scope_entries_from_tasks = [entry for entry in tasks if entry.get("scope_entries")]
    runtime_entries_from_tasks = [
        entry for entry in tasks if any(entry.get("runtime", {}).get(key) for key in ("expected_ports", "healthcheck_command", "run_command_hint", "notes"))
    ]

    _write_text(
        paths["handoff"],
        _render_section(
            "Control Center Handoff",
            handoff_entries,
            "No handoff-tagged entries yet. Add entries to `tasks-completed.md` with the `handoff` tag and rerun snapshot.",
        ),
    )
    _write_text(
        paths["runbook"],
        _render_section(
            "Runbook",
            runbook_entries,
            "No runbook-tagged entries yet. Add entries to `tasks-completed.md` with the `runbook` tag and rerun snapshot.",
        ),
    )
    _write_text(
        paths["approach_history"],
        _render_section(
            "Approach History",
            decision_entries,
            "No decision-tagged entries yet. Add entries to `tasks-completed.md` with the `decision` tag and rerun snapshot.",
        ),
    )

    scope_snapshot = _read_json(paths["scope_snapshot"], _evidence_defaults(manifest["service_id"], project_root, manifest))
    scope_snapshot["generated"] = utc_now_iso()
    scope_snapshot["service_id"] = manifest["service_id"]
    scope_snapshot["project_root"] = str(project_root)
    inherited_contract = str(manifest.get("agent_contract", {}).get("mode", "") if isinstance(manifest.get("agent_contract"), dict) else "") == "manager_inherited"
    if scope_entries_from_tasks:
        latest_scope_entries = scope_entries_from_tasks[-1]["scope_entries"]
        scope_snapshot["scope_entries"] = _filter_inherited_scope_entries(latest_scope_entries, project_root) if inherited_contract else latest_scope_entries
    elif not scope_snapshot.get("scope_entries"):
        scope_snapshot = _evidence_defaults(manifest["service_id"], project_root, manifest)
    scope_snapshot["scope_updates"] = [
        {
            "timestamp": entry["timestamp"],
            "title": entry["title"],
            "summary": entry["summary"],
            "changed_paths": entry["changed_paths"],
            "scope_entries": entry["scope_entries"],
        }
        for entry in scope_entries_from_tasks
    ]
    _write_json(paths["scope_snapshot"], scope_snapshot)

    if runtime_entries_from_tasks:
        manifest["runtime"] = runtime_entries_from_tasks[-1]["runtime"]

    # Extract new 0.1.8 fields from latest task entries
    runtime_services_entries = [entry for entry in tasks if entry.get("runtime_services")]
    if runtime_services_entries:
        manifest["runtime_services"] = runtime_services_entries[-1]["runtime_services"]

    dependency_entries = [entry for entry in tasks if entry.get("dependencies")]
    if dependency_entries:
        manifest["dependencies"] = dependency_entries[-1]["dependencies"]

    cross_dep_entries = [entry for entry in tasks if entry.get("cross_dependencies")]
    if cross_dep_entries:
        manifest["cross_dependencies"] = cross_dep_entries[-1]["cross_dependencies"]

    bootstrap_version_entries = [entry for entry in tasks if entry.get("bootstrap_version")]
    if bootstrap_version_entries:
        manifest["bootstrap_version"] = bootstrap_version_entries[-1]["bootstrap_version"]

    diagram_entries = [entry for entry in tasks if entry.get("diagram")]
    if diagram_entries:
        manifest["diagram"] = diagram_entries[-1]["diagram"]

    generated_at = utc_now_iso()
    if managed_docs_by_id.get("doc_index_md", {}).get("enabled", False):
        _write_text(paths["doc_index_md"], "# Doc Index\n\nGenerating...\n")

    derived_outputs: dict[str, str] = {
        "handoff": paths["handoff"].read_text(encoding="utf-8"),
        "runbook": paths["runbook"].read_text(encoding="utf-8"),
        "approach_history": paths["approach_history"].read_text(encoding="utf-8"),
        "readme": _render_root_readme(manifest, manifest.get("runtime", {}), tasks),
        "api": _render_root_api(manifest, manifest.get("runtime", {}), scope_snapshot, tasks),
        "changelog": _render_root_changelog(tasks),
    }

    for entry in managed_docs:
        doc_id = str(entry["doc_id"])
        target_path = _managed_doc_path(project_root, entry)
        if entry.get("enabled"):
            if doc_id in derived_outputs:
                _write_text(target_path, derived_outputs[doc_id])
            elif doc_id == "doc_index_json":
                # filled after the first doc-index pass
                pass
            elif doc_id == "doc_index_md":
                # filled after the first doc-index pass
                pass
            entry["last_generated_at"] = generated_at
    def _current_doc_index() -> dict[str, Any]:
        return {
            "generated": generated_at,
            "service_id": manifest["service_id"],
            "project_root": str(project_root),
            "docs": [
                {
                    "doc_id": str(item["doc_id"]),
                    "label": _managed_doc_label(str(item["doc_id"])),
                    "path": item["path"],
                    "enabled": bool(item.get("enabled")),
                    "generated_at": item.get("last_generated_at"),
                    "generated_from": item.get("generated_from", "switchboard/local/tasks-completed.md"),
                    "contributor_timestamps": _contributors_for_doc(str(item["doc_id"]), tasks),
                }
                for item in managed_docs
            ],
        }

    doc_index = _current_doc_index()

    if managed_docs_by_id.get("doc_index_json", {}).get("enabled", False):
        _write_json(paths["doc_index_json"], doc_index)
        managed_docs_by_id["doc_index_json"]["last_generated_at"] = generated_at
    elif not paths["doc_index_json"].exists():
        _write_json(paths["doc_index_json"], doc_index)

    if managed_docs_by_id.get("doc_index_md", {}).get("enabled", False):
        _write_text(paths["doc_index_md"], _render_doc_index_markdown(doc_index))
        managed_docs_by_id["doc_index_md"]["last_generated_at"] = generated_at
    elif not paths["doc_index_md"].exists():
        _write_text(paths["doc_index_md"], _render_doc_index_markdown(doc_index))

    doc_index = _current_doc_index()
    if managed_docs_by_id.get("doc_index_json", {}).get("enabled", False):
        _write_json(paths["doc_index_json"], doc_index)
    if managed_docs_by_id.get("doc_index_md", {}).get("enabled", False):
        _write_text(paths["doc_index_md"], _render_doc_index_markdown(doc_index))

    manifest["managed_docs"] = managed_docs
    manifest["doc_index"] = doc_index
    manifest["updated_at"] = utc_now_iso()
    _write_json(paths["manifest"], manifest)
    return {
        "manifest": manifest,
        "tasks": tasks,
        "scope_snapshot": scope_snapshot,
        "doc_index": doc_index,
    }


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _scope_path_is_suspicious(path: str) -> bool:
    token = str(path).replace("\\", "/").lower().rstrip("/")
    parts = [part for part in token.split("/") if part]
    basename = parts[-1] if parts else token
    if basename == ".env":
        return True
    if basename.startswith(".env.") and basename not in {".env.example", ".env.sample", ".env.template"}:
        return True
    suspicious_tokens = (
        "/venv",
        "/.venv",
        "node_modules",
        "/logs",
        "logs/",
        "switchboard/runtime",
        "/runtime",
        "__pycache__",
        ".pytest_cache",
        ".npm-cache",
        "/build",
        "/dist",
        "/cache",
    )
    return any(item in token for item in suspicious_tokens)


def verify_node_update(project_root: str | Path, write: bool = True) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    paths = node_paths(project_root)
    checks: list[dict[str, Any]] = []

    def add_check(check_id: str, ok: bool, message: str) -> None:
        checks.append({"check_id": check_id, "status": "ok" if ok else "failed", "message": message})

    manifest = _read_json(paths["manifest"], {}) if paths["manifest"].exists() else {}
    tasks = parse_tasks_completed(paths["tasks_completed"])
    latest = tasks[-1] if tasks else None
    latest_timestamp = str(latest.get("timestamp", "")) if latest else ""
    latest_dt = _parse_iso_datetime(latest_timestamp)

    add_check("tasks_completed_exists", paths["tasks_completed"].exists(), "Canonical task ledger exists.")
    add_check("latest_task_exists", latest is not None, "At least one task entry exists.")

    if latest:
        missing = [
            label
            for label, present in (
                ("Tags", bool(latest.get("tags"))),
                ("Summary", bool(latest.get("summary"))),
                ("Changed Paths", bool(latest.get("changed_paths"))),
                ("Agent", bool(latest.get("agent"))),
                ("Tool", bool(latest.get("tool"))),
                ("Read Back", bool(latest.get("read_back"))),
                ("Scope Check", bool(latest.get("scope_check"))),
            )
            if not present
        ]
        add_check(
            "latest_task_required_fields",
            not missing,
            "Latest task has required fields." if not missing else f"Latest task is missing: {', '.join(missing)}.",
        )
        changed_paths = [str(item).replace("\\", "/") for item in latest.get("changed_paths", [])]
        ledger_changed = any(path == "switchboard/local/tasks-completed.md" or path.endswith("/switchboard/local/tasks-completed.md") for path in changed_paths)
        add_check("ledger_recorded_as_changed", ledger_changed, "Latest task records the canonical ledger as changed.")
        if "scope" in latest.get("tags", []):
            add_check("scope_tag_has_entries", bool(latest.get("scope_entries")), "Scope-tagged tasks include Scope Entries.")
    else:
        add_check("latest_task_required_fields", False, "No latest task to validate.")
        add_check("ledger_recorded_as_changed", False, "No latest task to validate.")

    for check_id, path in (
        ("manifest_exists", paths["manifest"]),
        ("completed_tasks_json_exists", paths["completed_tasks_json"]),
        ("scope_snapshot_exists", paths["scope_snapshot"]),
    ):
        add_check(check_id, path.exists(), f"{path.relative_to(project_root)} exists.")

    if latest_dt is None:
        add_check("latest_timestamp_parseable", False, "Latest task timestamp is not parseable ISO datetime.")
    else:
        add_check("latest_timestamp_parseable", True, "Latest task timestamp is parseable.")
        freshness_sources = (
            ("manifest_fresh", paths["manifest"], "updated_at"),
            ("completed_tasks_json_fresh", paths["completed_tasks_json"], "generated"),
            ("scope_snapshot_fresh", paths["scope_snapshot"], "generated"),
        )
        for check_id, path, field in freshness_sources:
            payload = _read_json(path, {}) if path.exists() else {}
            generated_dt = _parse_iso_datetime(str(payload.get(field, "")))
            add_check(
                check_id,
                bool(generated_dt and generated_dt >= latest_dt),
                f"{path.relative_to(project_root)} is newer than the latest task entry.",
            )

    scope_snapshot = _read_json(paths["scope_snapshot"], {}) if paths["scope_snapshot"].exists() else {}
    scope_entries = scope_snapshot.get("scope_entries", [])
    add_check("scope_entries_present", bool(scope_entries), "Scope snapshot has at least one scope entry.")
    suspicious = [
        str(entry.get("path", ""))
        for entry in scope_entries
        if isinstance(entry, dict)
        and entry.get("enabled", True)
        and str(entry.get("kind", "")) in {"repo", "doc"}
        and _scope_path_is_suspicious(str(entry.get("path", "")))
    ]
    add_check(
        "scope_entries_safe",
        not suspicious,
        "No suspicious enabled pull entries." if not suspicious else f"Suspicious enabled pull entries: {', '.join(suspicious[:8])}.",
    )

    agent_contract = manifest.get("agent_contract", {}) if isinstance(manifest.get("agent_contract"), dict) else {}
    inherited_from = str(agent_contract.get("inherited_from") or "").strip()
    enabled_entrypoints = _normalize_agent_entrypoints(agent_contract.get("enabled_entrypoints"))
    required_agent_paths: list[Path] = []
    if inherited_from:
        required_agent_paths.append(Path(inherited_from))
    else:
        required_agent_paths.extend([paths["agent_contract_md"], paths["agent_contract_json"]])
    if "agents" in enabled_entrypoints:
        required_agent_paths.append(paths["agents_md"])
    if "claude" in enabled_entrypoints:
        required_agent_paths.append(paths["claude_md"])
    if "gemini" in enabled_entrypoints:
        required_agent_paths.extend([paths["gemini_md"], paths["gemini_settings"]])
    if "qwen" in enabled_entrypoints:
        required_agent_paths.extend([paths["qwen_md"], paths["qwen_settings"]])
    if "opencode" in enabled_entrypoints:
        required_agent_paths.extend([paths["opencode_config"], paths["opencode_agent"]])
    missing_agent_files = []
    for path in required_agent_paths:
        if path.exists():
            continue
        try:
            missing_agent_files.append(str(path.relative_to(project_root)))
        except ValueError:
            missing_agent_files.append(str(path))
    add_check(
        "agent_contract_files_present",
        not missing_agent_files,
        "Required Switchboard agent contract files exist." if not missing_agent_files else f"Missing agent contract files: {', '.join(missing_agent_files)}.",
    )

    status = "ok" if all(check["status"] == "ok" for check in checks) else "incomplete"
    result = {
        "generated": utc_now_iso(),
        "status": status,
        "service_id": manifest.get("service_id", ""),
        "project_root": str(project_root),
        "latest_task": {
            "timestamp": latest_timestamp,
            "title": latest.get("title", "") if latest else "",
            "agent": latest.get("agent", "") if latest else "",
            "tool": latest.get("tool", "") if latest else "",
        },
        "checks": checks,
    }
    if write:
        _write_json(paths["update_gate"], result)
    return result


def resolve_static_app_dir() -> Path | None:
    package_static = ROOT_DIR / "switchboard" / "static" / "app"
    if package_static.exists() and (package_static / "index.html").exists():
        return package_static
    dist_static = ROOT_DIR / "dist"
    if dist_static.exists() and (dist_static / "index.html").exists():
        return dist_static
    return None


def list_node_files(project_root: str | Path) -> list[str]:
    project_root = Path(project_root).resolve()
    paths = node_paths(project_root)
    if not paths["node_root"].exists():
        return []
    files: list[str] = []
    for path in sorted(paths["node_root"].rglob("*")):
        if path.is_file():
            files.append(str(path.relative_to(project_root)))
    return files
