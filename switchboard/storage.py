"""Snapshot and private-state persistence."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .manifests import ManifestStore


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def archive_token(timestamp: str) -> str:
    return timestamp.replace(":", "-")


def iso_plus_seconds(iso_str: str, seconds: int) -> str:
    """Add seconds to an ISO timestamp string and return a new ISO string."""
    try:
        dt = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        dt = datetime.now(timezone.utc).replace(microsecond=0)
    return (dt + timedelta(seconds=seconds)).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=False)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


class SnapshotStore:
    def __init__(self, settings: Settings, manifests: ManifestStore) -> None:
        self.settings = settings
        self.manifests = manifests

    def seed_flat_files(self) -> dict[str, Any]:
        generated = utc_now_iso()
        workspaces = self.manifests.load_workspaces()
        services = self.manifests.load_services()
        servers = self.manifests.load_servers()

        workspace_registry = {
            "generated": generated,
            "workspaces": [
                {
                    **workspace.model_dump(mode="json"),
                    "service_count": len([service for service in services if service.workspace_id == workspace.workspace_id]),
                    "last_status": "unverified",
                }
                for workspace in workspaces
            ],
        }
        server_registry = {
            "generated": generated,
            "servers": [
                {**server.model_dump(mode="json"), "last_status": "unverified"}
                for server in servers
            ],
        }
        service_inventory = {
            "generated": generated,
            "services": [
                self._service_inventory_entry(service, "unverified")
                for service in services
            ],
        }
        repo_inventory = {"generated": generated, "repos": []}
        docs_index = {"generated": generated, "files": []}
        logs_index = {"generated": generated, "files": []}
        run_history = {"generated": generated, "runs": []}
        pull_bundle_history = {"generated": generated, "bundles": []}
        pull_bundle_exposure_reviews = {"generated": generated, "bundles": {}}
        repo_safety_history = {"generated": generated, "checks": []}
        github_backup_history = {"generated": generated, "runs": []}
        secret_index = {"generated": generated, "entries": []}

        write_json(self.settings.evidence_dir / "workspace-registry.json", workspace_registry)
        write_json(self.settings.evidence_dir / "server-registry.json", server_registry)
        write_json(self.settings.evidence_dir / "service-inventory.json", service_inventory)
        write_json(self.settings.evidence_dir / "repo-inventory.json", repo_inventory)
        write_json(self.settings.evidence_dir / "docs-index.json", docs_index)
        write_json(self.settings.evidence_dir / "logs-index.json", logs_index)
        write_json(self.settings.evidence_dir / "run-history.json", run_history)
        write_json(self.settings.evidence_dir / "pull-bundle-history.json", pull_bundle_history)
        write_json(self.settings.evidence_dir / "pull-bundle-exposure-reviews.json", pull_bundle_exposure_reviews)
        write_json(self.settings.evidence_dir / "repo-safety-history.json", repo_safety_history)
        write_json(self.settings.evidence_dir / "github-backup-history.json", github_backup_history)
        write_json(self.settings.private_state_dir / "secret-path-index.json", secret_index)
        write_json(self.settings.private_state_dir / "repo-safety-findings.json", {"generated": generated, "checks": []})
        write_json(
            self.settings.private_state_dir / "runtime-cache.json",
            {
                "generated": generated,
                "runtime_checks": {},
                "node_sync": {},
                "action_locks": {},
                "task_ledger": {},
                "node_viewer": {},
                "environment_runtime_snapshots": {},
                "api_flow_runs": {},
            },
        )
        return {
            "workspace_registry": workspace_registry,
            "server_registry": server_registry,
            "service_inventory": service_inventory,
        }

    def _runtime_cache_path(self) -> Path:
        return self.settings.private_state_dir / "runtime-cache.json"

    def _read_runtime_cache(self) -> dict[str, Any]:
        return read_json(
            self._runtime_cache_path(),
            {
                "generated": utc_now_iso(),
                "runtime_checks": {},
                "node_sync": {},
                "action_locks": {},
                "task_ledger": {},
                "node_viewer": {},
                "environment_runtime_snapshots": {},
                "api_flow_runs": {},
            },
        )

    def _write_runtime_cache(self, cache: dict[str, Any]) -> None:
        cache.setdefault("runtime_checks", {})
        cache.setdefault("node_sync", {})
        cache.setdefault("action_locks", {})
        cache.setdefault("task_ledger", {})
        cache.setdefault("node_viewer", {})
        cache.setdefault("environment_runtime_snapshots", {})
        cache.setdefault("api_flow_runs", {})
        cache["generated"] = cache.get("generated") or utc_now_iso()
        write_json(self._runtime_cache_path(), cache)

    def persist_runtime_check(self, service_id: str, location_id: str, record: dict[str, Any]) -> dict[str, Any]:
        cache = self._read_runtime_cache()
        runtime_checks = cache.setdefault("runtime_checks", {})
        service_checks = runtime_checks.setdefault(service_id, {})
        service_checks[location_id] = record
        cache["generated"] = record.get("checked_at") or utc_now_iso()
        self._write_runtime_cache(cache)
        return record

    def persist_node_sync(self, service_id: str, location_id: str, record: dict[str, Any]) -> dict[str, Any]:
        cache = self._read_runtime_cache()
        sync_state = cache.setdefault("node_sync", {})
        service_sync = sync_state.setdefault(service_id, {})
        service_sync[location_id] = record
        cache["generated"] = record.get("timestamp") or utc_now_iso()
        self._write_runtime_cache(cache)
        return record

    def get_service_runtime_state(self, service_id: str) -> dict[str, Any]:
        cache = self._read_runtime_cache()
        runtime_checks = list(cache.get("runtime_checks", {}).get(service_id, {}).values())
        node_sync = list(cache.get("node_sync", {}).get(service_id, {}).values())
        runtime_checks.sort(key=lambda entry: entry.get("checked_at", ""), reverse=True)
        node_sync.sort(key=lambda entry: entry.get("timestamp", ""), reverse=True)
        return {
            "generated": cache.get("generated"),
            "service_id": service_id,
            "runtime_checks": runtime_checks,
            "node_sync": node_sync,
        }

    # --- Action locks ---

    def _prune_expired_locks(self, cache: dict[str, Any]) -> dict[str, Any]:
        locks = cache.get("action_locks", {})
        now = utc_now_iso()
        expired = [key for key, lock in locks.items() if lock.get("expires_at", "") <= now]
        for key in expired:
            del locks[key]
        return cache

    def acquire_action_lock(self, action_key: str, service_id: str, ttl_seconds: int = 900) -> dict[str, Any] | None:
        cache = self._read_runtime_cache()
        cache = self._prune_expired_locks(cache)
        locks = cache.setdefault("action_locks", {})
        composite_key = f"{action_key}:{service_id}"
        now = utc_now_iso()
        existing = locks.get(composite_key)
        if existing and existing.get("expires_at", "") > now:
            return None  # lock still active
        lock_record = {
            "action_key": action_key,
            "service_id": service_id,
            "started_at": now,
            "expires_at": iso_plus_seconds(now, ttl_seconds),
            "ttl_seconds": ttl_seconds,
            "status": "pending",
        }
        locks[composite_key] = lock_record
        cache["generated"] = now
        self._write_runtime_cache(cache)
        return lock_record

    def release_action_lock(self, action_key: str, service_id: str, status: str = "completed") -> dict[str, Any]:
        cache = self._read_runtime_cache()
        locks = cache.setdefault("action_locks", {})
        composite_key = f"{action_key}:{service_id}"
        now = utc_now_iso()
        lock = locks.pop(composite_key, None)
        record = {
            "action_key": action_key,
            "service_id": service_id,
            "released_at": now,
            "status": status,
        }
        if lock:
            record["started_at"] = lock.get("started_at", "")
        cache["generated"] = now
        self._write_runtime_cache(cache)
        return record

    def get_active_locks(self, service_id: str | None = None) -> list[dict[str, Any]]:
        cache = self._read_runtime_cache()
        cache = self._prune_expired_locks(cache)
        locks = cache.get("action_locks", {})
        results = list(locks.values())
        if service_id:
            results = [lock for lock in results if lock.get("service_id") == service_id]
        return results

    # --- Task ledger ---

    def persist_task_ledger(self, service_id: str, location_id: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        cache = self._read_runtime_cache()
        ledger = cache.setdefault("task_ledger", {})
        service_ledger = ledger.setdefault(service_id, {})
        now = utc_now_iso()
        service_ledger[location_id] = {
            "tasks": tasks,
            "last_synced": now,
        }
        cache["generated"] = now
        self._write_runtime_cache(cache)
        return {"service_id": service_id, "location_id": location_id, "task_count": len(tasks), "last_synced": now}

    def get_service_task_ledger(self, service_id: str) -> dict[str, Any]:
        cache = self._read_runtime_cache()
        ledger = cache.get("task_ledger", {}).get(service_id, {})
        all_tasks: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for location_id, location_data in ledger.items():
            for task in location_data.get("tasks", []):
                dedup_key = f"{task.get('timestamp', '')}|{task.get('title', '')}|{task.get('task_id', '')}"
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    all_tasks.append({**task, "node_id": location_id})
        all_tasks.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
        return {
            "service_id": service_id,
            "tasks": all_tasks,
            "task_count": len(all_tasks),
        }

    def persist_node_viewer(self, service_id: str, location_id: str, record: dict[str, Any]) -> dict[str, Any]:
        cache = self._read_runtime_cache()
        viewer = cache.setdefault("node_viewer", {})
        service_viewer = viewer.setdefault(service_id, {})
        service_viewer[location_id] = record
        cache["generated"] = utc_now_iso()
        self._write_runtime_cache(cache)
        return record

    def invalidate_node_viewer(self, service_id: str, location_id: str | None = None) -> None:
        cache = self._read_runtime_cache()
        viewer = cache.setdefault("node_viewer", {})
        if location_id is None:
            viewer.pop(service_id, None)
        else:
            service_viewer = viewer.get(service_id, {})
            if isinstance(service_viewer, dict):
                service_viewer.pop(location_id, None)
                if not service_viewer:
                    viewer.pop(service_id, None)
        cache["generated"] = utc_now_iso()
        self._write_runtime_cache(cache)

    def get_service_node_viewer(self, service_id: str) -> list[dict[str, Any]]:
        cache = self._read_runtime_cache()
        service_viewer = cache.get("node_viewer", {}).get(service_id, {})
        rows = list(service_viewer.values())
        rows.sort(key=lambda entry: entry.get("location_id", ""))
        return rows

    def persist_environment_runtime_snapshot(self, environment_id: str, record: dict[str, Any]) -> dict[str, Any]:
        cache = self._read_runtime_cache()
        snapshots = cache.setdefault("environment_runtime_snapshots", {})
        snapshots[environment_id] = record
        cache["generated"] = record.get("captured_at") or utc_now_iso()
        self._write_runtime_cache(cache)
        return record

    def get_environment_runtime_snapshot(self, environment_id: str) -> dict[str, Any] | None:
        cache = self._read_runtime_cache()
        return cache.get("environment_runtime_snapshots", {}).get(environment_id)

    def append_api_flow_run(self, environment_id: str, flow_id: str, record: dict[str, Any]) -> dict[str, Any]:
        cache = self._read_runtime_cache()
        runs = cache.setdefault("api_flow_runs", {})
        environment_runs = runs.setdefault(environment_id, {})
        flow_runs = environment_runs.setdefault(flow_id, [])
        flow_runs.insert(0, record)
        environment_runs[flow_id] = flow_runs[:25]
        cache["generated"] = record.get("finished_at") or record.get("started_at") or utc_now_iso()
        self._write_runtime_cache(cache)
        return record

    def get_api_flow_runs(self, environment_id: str, flow_id: str) -> list[dict[str, Any]]:
        cache = self._read_runtime_cache()
        return list(cache.get("api_flow_runs", {}).get(environment_id, {}).get(flow_id, []))

    def persist_collect_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        generated = snapshot["generated"]
        workspace_id = snapshot["workspace"]["workspace_id"]
        token = archive_token(generated)
        archive_root = self.settings.archive_dir / token
        archive_root.mkdir(parents=True, exist_ok=True)

        workspace_snapshot_path = archive_root / f"workspace-{workspace_id}.json"
        write_json(workspace_snapshot_path, snapshot)

        run_history_path = self.settings.evidence_dir / "run-history.json"
        run_history = read_json(run_history_path, {"generated": generated, "runs": []})
        run_history["generated"] = generated
        run_history["runs"].insert(
            0,
            {
                "workspace_id": workspace_id,
                "generated": generated,
                "archive_path": str(workspace_snapshot_path.relative_to(self.settings.evidence_dir.parent)),
                "status": snapshot["summary"]["status"],
                "service_count": snapshot["summary"]["service_count"],
                "server_count": snapshot["summary"]["server_count"],
            },
        )
        write_json(run_history_path, run_history)

        repo_entries = snapshot.get("repo_inventory", [])
        docs_entries = snapshot.get("docs_index", [])
        logs_entries = snapshot.get("logs_index", [])
        secret_entries = snapshot.get("secret_path_index", [])

        write_json(
            self.settings.evidence_dir / "repo-inventory.json",
            {"generated": generated, "repos": repo_entries},
        )
        write_json(
            self.settings.evidence_dir / "docs-index.json",
            {"generated": generated, "files": docs_entries},
        )
        write_json(
            self.settings.evidence_dir / "logs-index.json",
            {"generated": generated, "files": logs_entries},
        )
        write_json(
            self.settings.private_state_dir / "secret-path-index.json",
            {"generated": generated, "entries": secret_entries},
        )

        latest_server_status = {item["server_id"]: item["status"] for item in snapshot["servers"]}
        latest_service_status = {item["service_id"]: item["status"] for item in snapshot["services"]}

        workspaces = self.manifests.load_workspaces()
        services = self.manifests.load_services()
        servers = self.manifests.load_servers()

        write_json(
            self.settings.evidence_dir / "workspace-registry.json",
            {
                "generated": generated,
                "workspaces": [
                    {
                        **workspace.model_dump(mode="json"),
                        "service_count": len(
                            [service for service in services if service.workspace_id == workspace.workspace_id]
                        ),
                        "last_status": snapshot["summary"]["status"]
                        if workspace.workspace_id == workspace_id
                        else "unverified",
                    }
                    for workspace in workspaces
                ],
            },
        )
        write_json(
            self.settings.evidence_dir / "server-registry.json",
            {
                "generated": generated,
                "servers": [
                    {
                        **server.model_dump(mode="json"),
                        "last_status": latest_server_status.get(server.server_id, "unverified"),
                    }
                    for server in servers
                ],
            },
        )
        write_json(
            self.settings.evidence_dir / "service-inventory.json",
            {
                "generated": generated,
                "services": [
                    self._service_inventory_entry(
                        service,
                        latest_service_status.get(service.service_id, "unverified"),
                    )
                    for service in services
                ],
            },
        )
        return snapshot

    def get_workspace_runs(self, workspace_id: str) -> list[dict[str, Any]]:
        history = read_json(self.settings.evidence_dir / "run-history.json", {"runs": []})
        return [entry for entry in history.get("runs", []) if entry.get("workspace_id") == workspace_id]

    def get_workspace_latest(self, workspace_id: str) -> dict[str, Any] | None:
        runs = self.get_workspace_runs(workspace_id)
        if not runs:
            return None
        archive_path = self.settings.evidence_dir.parent / runs[0]["archive_path"]
        snapshot = read_json(archive_path, None)
        if snapshot is None:
            return None
        return snapshot

    def get_service_secret_paths(self, service_id: str) -> dict[str, Any]:
        data = read_json(self.settings.private_state_dir / "secret-path-index.json", {"entries": []})
        entries = [entry for entry in data.get("entries", []) if entry.get("service_id") == service_id]
        return {
            "generated": data.get("generated"),
            "service_id": service_id,
            "count": len(entries),
            "entries": entries,
        }

    def append_pull_bundle(self, bundle_record: dict[str, Any]) -> dict[str, Any]:
        path = self.settings.evidence_dir / "pull-bundle-history.json"
        history = read_json(path, {"generated": bundle_record["created_at"], "bundles": []})
        history["generated"] = bundle_record["created_at"]
        history["bundles"].insert(0, bundle_record)
        write_json(path, history)
        return bundle_record

    def list_pull_bundles(self, service_id: str) -> list[dict[str, Any]]:
        data = read_json(self.settings.evidence_dir / "pull-bundle-history.json", {"bundles": []})
        return [entry for entry in data.get("bundles", []) if entry.get("service_id") == service_id]

    def list_all_pull_bundles(self) -> list[dict[str, Any]]:
        data = read_json(self.settings.evidence_dir / "pull-bundle-history.json", {"bundles": []})
        return list(data.get("bundles", []))

    def load_pull_bundle_exposure_reviews(self) -> dict[str, Any]:
        return read_json(
            self.settings.evidence_dir / "pull-bundle-exposure-reviews.json",
            {"generated": "", "bundles": {}},
        )

    def append_github_backup(self, record: dict[str, Any]) -> dict[str, Any]:
        path = self.settings.evidence_dir / "github-backup-history.json"
        generated = str(record.get("generated") or utc_now_iso())
        history = read_json(path, {"generated": generated, "runs": []})
        history["generated"] = generated
        history["runs"].insert(0, record)
        write_json(path, history)
        return record

    def append_repo_safety_check(self, summary: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
        public_path = self.settings.evidence_dir / "repo-safety-history.json"
        private_path = self.settings.private_state_dir / "repo-safety-findings.json"

        public_history = read_json(public_path, {"generated": summary["generated"], "checks": []})
        public_history["generated"] = summary["generated"]
        public_history["checks"].insert(0, summary)
        write_json(public_path, public_history)

        private_history = read_json(private_path, {"generated": summary["generated"], "checks": []})
        private_history["generated"] = summary["generated"]
        private_history["checks"].insert(
            0,
            {
                **summary,
                "findings": findings,
            },
        )
        write_json(private_path, private_history)
        return summary

    def get_repo_safety_history(self, service_id: str) -> list[dict[str, Any]]:
        data = read_json(self.settings.evidence_dir / "repo-safety-history.json", {"checks": []})
        return [entry for entry in data.get("checks", []) if entry.get("service_id") == service_id]

    def delete_service_data(self, service_id: str, workspace_id: str) -> dict[str, Any]:
        generated = utc_now_iso()

        def _filter_records(path: Path, key: str) -> None:
            data = read_json(path, {"generated": generated, key: []})
            data["generated"] = generated
            data[key] = [entry for entry in data.get(key, []) if entry.get("service_id") != service_id]
            write_json(path, data)

        _filter_records(self.settings.evidence_dir / "service-inventory.json", "services")
        _filter_records(self.settings.evidence_dir / "repo-inventory.json", "repos")
        _filter_records(self.settings.evidence_dir / "docs-index.json", "files")
        _filter_records(self.settings.evidence_dir / "logs-index.json", "files")
        _filter_records(self.settings.evidence_dir / "pull-bundle-history.json", "bundles")
        _filter_records(self.settings.evidence_dir / "repo-safety-history.json", "checks")
        _filter_records(self.settings.private_state_dir / "secret-path-index.json", "entries")
        _filter_records(self.settings.private_state_dir / "repo-safety-findings.json", "checks")

        runtime_cache = self._read_runtime_cache()
        runtime_cache.get("runtime_checks", {}).pop(service_id, None)
        runtime_cache.get("node_sync", {}).pop(service_id, None)
        runtime_cache.get("node_viewer", {}).pop(service_id, None)
        runtime_cache.get("task_ledger", {}).pop(service_id, None)
        for snapshot in runtime_cache.get("environment_runtime_snapshots", {}).values():
            if not isinstance(snapshot, dict):
                continue
            snapshot["locations"] = [
                entry for entry in snapshot.get("locations", [])
                if not isinstance(entry, dict) or entry.get("service_id") != service_id
            ]
            for key in ("open_ports", "expected_ports", "unexpected_ports", "exposed_ports", "process_findings", "node_findings"):
                if key in snapshot and isinstance(snapshot[key], list):
                    snapshot[key] = [
                        entry for entry in snapshot[key]
                        if not isinstance(entry, dict) or entry.get("service_id") != service_id
                    ]
        runtime_cache["generated"] = generated
        self._write_runtime_cache(runtime_cache)

        downloads_root = self.settings.downloads_dir / workspace_id / service_id
        if downloads_root.exists():
            shutil.rmtree(downloads_root)

        history_path = self.settings.evidence_dir / "run-history.json"
        history = read_json(history_path, {"generated": generated, "runs": []})
        history["generated"] = generated
        for run in history.get("runs", []):
            if run.get("workspace_id") != workspace_id or not run.get("archive_path"):
                continue
            archive_path = self.settings.evidence_dir.parent / run["archive_path"]
            snapshot = read_json(archive_path, None)
            if snapshot is None:
                continue
            services = [entry for entry in snapshot.get("services", []) if entry.get("service_id") != service_id]
            snapshot["services"] = services
            snapshot["repo_inventory"] = [
                entry for entry in snapshot.get("repo_inventory", []) if entry.get("service_id") != service_id
            ]
            snapshot["docs_index"] = [
                entry for entry in snapshot.get("docs_index", []) if entry.get("service_id") != service_id
            ]
            snapshot["logs_index"] = [
                entry for entry in snapshot.get("logs_index", []) if entry.get("service_id") != service_id
            ]
            snapshot["secret_path_index"] = [
                entry for entry in snapshot.get("secret_path_index", []) if entry.get("service_id") != service_id
            ]
            summary = snapshot.setdefault("summary", {})
            if isinstance(summary, dict):
                summary["service_count"] = len(services)
            write_json(archive_path, snapshot)
            if run.get("service_count") is not None:
                run["service_count"] = len(services)
        write_json(history_path, history)

        workspaces = self.manifests.load_workspaces()
        services = self.manifests.load_services()
        workspace_statuses = {
            entry.get("workspace_id"): entry.get("last_status", "unverified")
            for entry in read_json(self.settings.evidence_dir / "workspace-registry.json", {"workspaces": []}).get(
                "workspaces", []
            )
        }
        service_statuses = {
            entry.get("service_id"): entry.get("last_status", "unverified")
            for entry in read_json(self.settings.evidence_dir / "service-inventory.json", {"services": []}).get(
                "services", []
            )
        }

        write_json(
            self.settings.evidence_dir / "workspace-registry.json",
            {
                "generated": generated,
                "workspaces": [
                    {
                        **workspace.model_dump(mode="json"),
                        "service_count": len(
                            [service for service in services if service.workspace_id == workspace.workspace_id]
                        ),
                        "last_status": workspace_statuses.get(workspace.workspace_id, "unverified"),
                    }
                    for workspace in workspaces
                ],
            },
        )
        write_json(
            self.settings.evidence_dir / "service-inventory.json",
            {
                "generated": generated,
                "services": [
                    self._service_inventory_entry(
                        service,
                        service_statuses.get(service.service_id, "unverified"),
                    )
                    for service in services
                ],
            },
        )

        return {
            "deleted": True,
            "service_id": service_id,
            "workspace_id": workspace_id,
            "generated": generated,
        }

    def _service_inventory_entry(self, service: Any, last_status: str) -> dict[str, Any]:
        return {
            "service_id": service.service_id,
            "workspace_id": service.workspace_id,
            "display_name": service.display_name,
            "kind": service.kind,
            "execution_mode": getattr(service, "execution_mode", "networked"),
            "ownership_tier": service.ownership_tier,
            "tags": service.tags,
            "favorite_tier": service.favorite_tier,
            "notes": service.notes,
            "path_aliases": service.path_aliases,
            "location_count": len(service.locations),
            "last_status": last_status,
        }
