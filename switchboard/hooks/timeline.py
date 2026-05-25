"""Local-private source capture for Codex and Claude prompt hooks."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TIMELINE_SCHEMA_VERSION = "switchboard-hook-timeline-v0"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_timeline_db_path() -> Path:
    configured = os.environ.get("SWITCHBOARD_HOOKS_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".agent-ops" / "private" / "hooks" / "timeline.sqlite"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _short_preview(value: str) -> str:
    safe = " ".join(str(value or "").split())
    return safe[:120]


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or default_timeline_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS hook_events (
          event_id TEXT PRIMARY KEY,
          captured_at TEXT NOT NULL,
          agent TEXT NOT NULL,
          hook_event_name TEXT NOT NULL,
          cwd TEXT NOT NULL,
          source_type TEXT NOT NULL,
          prompt_sha256 TEXT NOT NULL,
          prompt_preview TEXT NOT NULL,
          raw_prompt TEXT NOT NULL,
          related_brics_json TEXT NOT NULL,
          metadata_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS context_packets (
          packet_id TEXT PRIMARY KEY,
          generated_at TEXT NOT NULL,
          agent TEXT NOT NULL,
          cwd TEXT NOT NULL,
          task TEXT NOT NULL,
          budget INTEGER NOT NULL,
          estimated_tokens INTEGER NOT NULL,
          content TEXT NOT NULL,
          source_refs_json TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _json_list(value: list[str] | None) -> str:
    return json.dumps(value or [], separators=(",", ":"))


def capture_user_prompt(
    *,
    prompt: str,
    agent: str,
    cwd: str,
    hook_event_name: str = "UserPromptSubmit",
    source_type: str = "user_prompt",
    related_brics: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Store exact prompt text locally and return only git-safe metadata."""

    captured_at = utc_now_iso()
    digest = _sha256(prompt)
    event_id = f"prompt-{captured_at.replace(':', '').replace('-', '')}-{digest[:12]}"
    connection = _connect(db_path)
    connection.execute(
        """
        INSERT OR REPLACE INTO hook_events (
          event_id,
          captured_at,
          agent,
          hook_event_name,
          cwd,
          source_type,
          prompt_sha256,
          prompt_preview,
          raw_prompt,
          related_brics_json,
          metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            captured_at,
            agent,
            hook_event_name,
            cwd,
            source_type,
            digest,
            _short_preview(prompt),
            prompt,
            _json_list(related_brics),
            json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
        ),
    )
    connection.commit()
    connection.close()
    return {
        "event_id": event_id,
        "captured_at": captured_at,
        "agent": agent,
        "hook_event_name": hook_event_name,
        "cwd": cwd,
        "source_type": source_type,
        "prompt_sha256": digest,
        "related_brics": related_brics or [],
        "privacy": "local_private_raw_git_safe_hash",
        "raw_prompt_included": False,
        "raw_source_ref": f"timeline://prompt/{captured_at[:10]}/{event_id}",
    }


def store_context_packet(
    *,
    agent: str,
    cwd: str,
    task: str,
    budget: int,
    estimated_tokens: int,
    content: str,
    source_refs: list[str],
    db_path: Path | None = None,
) -> dict[str, Any]:
    generated_at = utc_now_iso()
    digest = _sha256(f"{agent}\n{cwd}\n{task}\n{content}")
    packet_id = f"context-{generated_at.replace(':', '').replace('-', '')}-{digest[:12]}"
    connection = _connect(db_path)
    connection.execute(
        """
        INSERT OR REPLACE INTO context_packets (
          packet_id,
          generated_at,
          agent,
          cwd,
          task,
          budget,
          estimated_tokens,
          content,
          source_refs_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            packet_id,
            generated_at,
            agent,
            cwd,
            task,
            int(budget),
            int(estimated_tokens),
            content,
            _json_list(source_refs),
        ),
    )
    connection.commit()
    connection.close()
    return {
        "packet_id": packet_id,
        "generated_at": generated_at,
        "estimated_tokens": estimated_tokens,
        "source_refs": source_refs,
    }


def read_timeline_summary(db_path: Path | None = None) -> dict[str, Any]:
    path = db_path or default_timeline_db_path()
    if not path.exists():
        return {
            "schema_version": TIMELINE_SCHEMA_VERSION,
            "db_exists": False,
            "event_count": 0,
            "context_packet_count": 0,
            "last_event_at": "",
            "last_context_packet_at": "",
        }
    connection = _connect(path)
    event_count = int(connection.execute("SELECT COUNT(*) FROM hook_events").fetchone()[0])
    packet_count = int(connection.execute("SELECT COUNT(*) FROM context_packets").fetchone()[0])
    last_event_at = connection.execute("SELECT MAX(captured_at) FROM hook_events").fetchone()[0] or ""
    last_packet_at = connection.execute("SELECT MAX(generated_at) FROM context_packets").fetchone()[0] or ""
    connection.close()
    return {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "db_exists": True,
        "event_count": event_count,
        "context_packet_count": packet_count,
        "last_event_at": last_event_at,
        "last_context_packet_at": last_packet_at,
    }
