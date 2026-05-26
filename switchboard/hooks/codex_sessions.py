"""Import Codex Desktop/CLI session prompts into the local hook timeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .context import CODEX_SESSION_CAPTURE_BRIC, SOURCE_CAPTURE_BRIC
from .timeline import capture_user_prompt, default_timeline_db_path

CODEX_SESSION_SOURCE_TYPE = "codex_session_user_prompt"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_event_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value).strip("-").lower()


def _codex_home(path: str | Path | None = None) -> Path:
    return Path(path).expanduser() if path else Path.home() / ".codex"


def _session_files(codex_home: Path, session_file: str | Path | None = None) -> list[Path]:
    if session_file:
        return [Path(session_file).expanduser().resolve()]
    sessions_root = codex_home / "sessions"
    if not sessions_root.exists():
        return []
    return sorted(sessions_root.rglob("*.jsonl"), key=lambda path: path.stat().st_mtime)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "input_text":
            parts.append(str(item.get("text") or ""))
    return "\n".join(part for part in parts if part)


def iter_codex_session_user_prompts(session_path: Path) -> Iterable[dict[str, Any]]:
    """Yield user prompts from one Codex session JSONL file."""

    session_meta: dict[str, Any] = {}
    with session_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            row_type = row.get("type")
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            if row_type == "session_meta":
                session_meta = payload
                continue
            if row_type != "response_item":
                continue
            if payload.get("type") != "message" or payload.get("role") != "user":
                continue
            prompt = _content_text(payload.get("content")).strip()
            if not prompt:
                continue
            timestamp = str(row.get("timestamp") or session_meta.get("timestamp") or "")
            session_id = str(session_meta.get("id") or "")
            cwd = str(session_meta.get("cwd") or "")
            originator = str(session_meta.get("originator") or "codex")
            fingerprint = _sha256(f"{session_path}:{line_number}:{timestamp}:{prompt}")
            yield {
                "session_file": str(session_path),
                "session_id": session_id,
                "line_number": line_number,
                "timestamp": timestamp,
                "agent": "codex",
                "originator": originator,
                "cwd": cwd,
                "prompt": prompt,
                "prompt_sha256": _sha256(prompt),
                "event_id": f"codex-session-{_safe_event_id(timestamp)[:32]}-{fingerprint[:12]}",
            }


def import_codex_session_prompts(
    *,
    project_root: str | Path | None = None,
    codex_home: str | Path | None = None,
    session_file: str | Path | None = None,
    limit: int = 0,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Import Codex session prompts into the same local-private timeline used by hooks."""

    home = _codex_home(codex_home)
    db = db_path or default_timeline_db_path()
    files = _session_files(home, session_file)
    imported: list[dict[str, Any]] = []
    scanned_prompts = 0
    for path in files:
        for prompt in iter_codex_session_user_prompts(path):
            scanned_prompts += 1
            captured = capture_user_prompt(
                prompt=prompt["prompt"],
                agent="codex",
                cwd=prompt["cwd"],
                hook_event_name="CodexSessionImport",
                source_type=CODEX_SESSION_SOURCE_TYPE,
                related_brics=[SOURCE_CAPTURE_BRIC, CODEX_SESSION_CAPTURE_BRIC],
                metadata={
                    "session_file": prompt["session_file"],
                    "session_id": prompt["session_id"],
                    "line_number": prompt["line_number"],
                    "originator": prompt["originator"],
                    "prompt_sha256": prompt["prompt_sha256"],
                },
                db_path=db,
                captured_at=prompt["timestamp"],
                event_id=prompt["event_id"],
            )
            imported.append(
                {
                    "event_id": captured["event_id"],
                    "captured_at": captured["captured_at"],
                    "cwd": captured["cwd"],
                    "prompt_sha256": captured["prompt_sha256"],
                    "raw_source_ref": captured["raw_source_ref"],
                    "session_file": prompt["session_file"],
                    "line_number": prompt["line_number"],
                }
            )
            if limit and len(imported) >= limit:
                break
        if limit and len(imported) >= limit:
            break
    return {
        "schema_version": "switchboard-codex-session-import-v0",
        "project_root": str(Path(project_root).expanduser().resolve()) if project_root else "",
        "codex_home": str(home),
        "db_path": str(db),
        "files_scanned": len(files),
        "prompts_scanned": scanned_prompts,
        "imported_count": len(imported),
        "events": imported,
        "privacy": {
            "raw_prompt_output": "excluded",
            "raw_prompt_storage": "local_private_timeline_db",
            "git_safe_summary_only": True,
        },
    }
