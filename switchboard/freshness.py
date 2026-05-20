"""Freshness helpers for keeping cached Switchboard data honest."""

from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .defaults import DEFAULT_NODE_PORT


def parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def latest_timestamp(*values: Any) -> str:
    parsed = [item for item in (parse_timestamp(value) for value in values) if item is not None]
    return iso_timestamp(max(parsed)) if parsed else ""


def timestamp_before(left: Any, right: Any) -> bool:
    left_dt = parse_timestamp(left)
    right_dt = parse_timestamp(right)
    return bool(left_dt and right_dt and left_dt < right_dt)


def file_mtime(path: Path) -> str:
    try:
        return iso_timestamp(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
    except OSError:
        return ""


def read_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return fallback


def freshness_envelope(
    *,
    data_as_of: Any = "",
    truth_as_of: Any = "",
    source: str = "",
    stale_reason: str = "",
    refresh_action: str = "",
) -> dict[str, str]:
    data = str(data_as_of or "")
    truth = str(truth_as_of or "")
    reason = stale_reason
    if not data and truth and not reason:
        reason = "missing_live_evidence"
    elif data and truth and timestamp_before(data, truth) and not reason:
        reason = "cache_older_than_truth"

    if reason in {"manager_8020_unreachable", "manager_unreachable"}:
        state = "Manager unreachable"
    elif reason:
        state = "Stale"
    elif data or truth:
        state = "Fresh"
    else:
        state = "Unverified"

    return {
        "data_as_of": data,
        "truth_as_of": truth,
        "freshness_state": state,
        "stale_reason": reason,
        "refresh_action": refresh_action or ("Check 8020" if state == "Manager unreachable" else "Collect" if reason else ""),
        "freshness_source": source,
    }


def port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def manager_manifest_path(manager_root: Path) -> Path:
    return manager_root / "switchboard" / "manager.manifest.json"


def node_manifest_path(project_root: str | Path) -> Path:
    return Path(project_root) / "switchboard" / "node.manifest.json"


def manager_record_for_root(manager_root: Path, project_root: str) -> dict[str, Any] | None:
    manifest = read_json(manager_manifest_path(manager_root), {})
    target = Path(project_root).resolve()
    for record in manifest.get("managed_roots", []):
        if not isinstance(record, dict):
            continue
        try:
            if Path(str(record.get("project_root", ""))).resolve() == target:
                return record
        except OSError:
            continue
    return None


def root_manifest_truth(project_root: str) -> tuple[dict[str, Any], str]:
    path = node_manifest_path(project_root)
    manifest = read_json(path, {})
    as_of = latest_timestamp(manifest.get("updated_at", ""), file_mtime(path))
    return manifest if isinstance(manifest, dict) else {}, as_of


def manager_manifest_truth(manager_root: Path, record: dict[str, Any] | None) -> str:
    return latest_timestamp(
        (record or {}).get("manifest_updated_at", ""),
        file_mtime(manager_manifest_path(manager_root)),
    )


def freshen_node_viewers(
    *,
    manager_root: Path,
    service_payload: dict[str, Any],
    cached_rows: list[dict[str, Any]],
    control_center_version: str,
) -> list[dict[str, Any]]:
    cached_by_location = {str(row.get("location_id", "")): row for row in cached_rows if isinstance(row, dict)}
    rows: list[dict[str, Any]] = []

    for location in service_payload.get("locations", []) or []:
        if not isinstance(location, dict):
            continue
        location_id = str(location.get("location_id", ""))
        root = str(location.get("root", ""))
        server_id = str(location.get("server_id", ""))
        access_mode = str(location.get("access_mode", ""))
        cached = dict(cached_by_location.get(location_id, {}))

        root_manifest: dict[str, Any] = {}
        root_truth = ""
        manager_record: dict[str, Any] | None = None
        manager_truth = ""
        if access_mode == "local" and root:
            root_manifest, root_truth = root_manifest_truth(root)
            manager_record = manager_record_for_root(manager_root, root)
            manager_truth = manager_manifest_truth(manager_root, manager_record)

        truth_as_of = latest_timestamp(root_truth, manager_truth)
        data_as_of = latest_timestamp(
            cached.get("last_inspected_at", ""),
            cached.get("manifest_updated_at", ""),
            cached.get("data_as_of", ""),
        )
        source = "runtime_cache"
        if manager_record:
            source = "manager_manifest"
        elif root_manifest:
            source = "root_manifest"

        manifest_version = str(root_manifest.get("installed_version", ""))
        manager_version = str((manager_record or {}).get("last_seen_version", "") or control_center_version)
        manifest_port = root_manifest.get("runtime_port")
        cached_port = cached.get("runtime_port")
        legacy_port = None
        if isinstance(cached_port, int) and cached_port > 0 and cached_port != DEFAULT_NODE_PORT:
            legacy_port = cached_port
        if isinstance(manifest_port, int) and manifest_port > 0 and manifest_port != DEFAULT_NODE_PORT:
            legacy_port = legacy_port or manifest_port

        stale_reason = ""
        refresh_action = ""
        if manager_record and not port_listening(DEFAULT_NODE_PORT):
            stale_reason = "manager_8020_unreachable"
            refresh_action = "Check 8020"
        elif truth_as_of and (not data_as_of or timestamp_before(data_as_of, truth_as_of)):
            stale_reason = "cache_older_than_truth"
            refresh_action = "Inspect Node"
        elif cached and not truth_as_of:
            stale_reason = "cache_without_truth"
            refresh_action = "Inspect Node"

        freshness = freshness_envelope(
            data_as_of=data_as_of,
            truth_as_of=truth_as_of,
            source=source,
            stale_reason=stale_reason,
            refresh_action=refresh_action,
        )
        manager_managed = manager_record is not None
        manager_live = manager_managed and freshness["freshness_state"] != "Manager unreachable"

        row = {
            **cached,
            "service_id": str(service_payload.get("service_id", cached.get("service_id", ""))),
            "location_id": location_id,
            "server_id": server_id,
            "root": root,
            "node_present": bool(root_manifest or cached.get("node_present")),
            "bootstrap_ready": bool(manager_record or cached.get("bootstrap_ready")),
            "runtime_ready": bool(manager_live),
            "installed_version": manifest_version or str((manager_record or {}).get("last_seen_version", "")) or str(cached.get("installed_version", "")),
            "bootstrap_version": str(root_manifest.get("bootstrap_version", cached.get("bootstrap_version", ""))),
            "manifest_updated_at": root_manifest.get("updated_at", cached.get("manifest_updated_at", "")),
            "runtime_status": "manager_running" if manager_live else "missing" if manager_managed else str(cached.get("runtime_status", "missing")),
            "runtime_pid": cached.get("runtime_pid") if manager_live else None,
            "runtime_port": DEFAULT_NODE_PORT if manager_managed else int(cached.get("runtime_port") or DEFAULT_NODE_PORT),
            "target_manager_port": DEFAULT_NODE_PORT,
            "legacy_runtime_port": legacy_port,
            "legacy_runtime_port_label": f"legacy cached :{legacy_port}" if legacy_port else "",
            "needs_install": bool(cached.get("needs_install", False)) and not root_manifest,
            "needs_upgrade": False,
            "needs_bootstrap": False if manager_record else bool(cached.get("needs_bootstrap", False)),
            "attention_reason": stale_reason or str(cached.get("attention_reason", "")),
            "manifest_path": str(node_manifest_path(root)) if root else str(cached.get("manifest_path", "")),
            "runtime_dir": str(cached.get("runtime_dir", "")),
            "log_file": str(cached.get("log_file", "")),
            "last_error": str(cached.get("last_error", "")),
            "manager_managed": manager_managed,
            "manager_root_id": str((manager_record or {}).get("root_id", cached.get("manager_root_id", ""))),
            "manager_root": str(manager_root) if manager_record else str(cached.get("manager_root", "")),
            "manager_version": manager_version if manager_record else str(cached.get("manager_version", "")),
            **freshness,
        }
        rows.append(row)

    if not rows:
        for cached in cached_rows:
            data_as_of = latest_timestamp(cached.get("last_inspected_at", ""), cached.get("manifest_updated_at", ""))
            rows.append(
                {
                    **cached,
                    **freshness_envelope(
                        data_as_of=data_as_of,
                        truth_as_of="",
                        source="runtime_cache",
                        stale_reason="cache_without_manifest",
                        refresh_action="Inspect Node",
                    ),
                }
            )
    return rows
