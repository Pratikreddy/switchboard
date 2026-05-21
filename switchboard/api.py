"""FastAPI application."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException

from . import __version__
from .collectors import CollectionCoordinator
from .config import get_settings
from .freshness import file_mtime, freshen_node_viewers, freshness_envelope, latest_timestamp, timestamp_before
from .manifests import ManifestStore
from .models import (
    ActionLockRequest,
    ApiFlowCreateRequest,
    ApiFlowPatchRequest,
    ApiFlowRunRequest,
    CollectRequest,
    DiscoveryTreeRequest,
    DownloadRequest,
    EnvironmentRuntimeSnapshotRequest,
    GitHubBackupRequest,
    GitPullRequest,
    GitPushRequest,
    NodeActionRequest,
    NodeSyncRequest,
    ProjectCreateRequest,
    ProjectEnvironmentCreateRequest,
    ProjectEnvironmentPatchRequest,
    ProjectPatchRequest,
    PullBundleBackupDryRunRequest,
    PullBundleRequest,
    RepoActionRequest,
    RuntimeActionRequest,
    ScanRootRequest,
    ServerCreateRequest,
    ServerPatchRequest,
    ServiceCreateRequest,
    ServicePatchRequest,
    WorkspaceManifest,
    WorkspaceCreateRequest,
    WorkspacePatchRequest,
)
from .storage import SnapshotStore


settings = get_settings()
manifest_store = ManifestStore(settings)
snapshot_store = SnapshotStore(settings, manifest_store)
coordinator = CollectionCoordinator(settings, manifest_store, snapshot_store)

app = FastAPI(title="Switchboard", version=__version__)


def _manager_root() -> Path:
    return settings.manifest_dir.parent.parent


def _runtime_cache_generated() -> str:
    try:
        cache = snapshot_store._read_runtime_cache()
    except Exception:
        return ""
    return str(cache.get("generated", "") or "")


def _workspace_truth_as_of(workspace_id: str) -> str:
    manifest_files = [
        settings.manifest_dir / "workspaces.json",
        settings.manifest_dir / "services.json",
        settings.manifest_dir / "servers.json",
        settings.manifest_dir / "projects.json",
        settings.manifest_dir / "project-environments.json",
        settings.manifest_dir.parent / "manager.manifest.json",
    ]
    return latest_timestamp(_runtime_cache_generated(), *(file_mtime(path) for path in manifest_files))


def _service_truth_as_of(payload: dict[str, object]) -> str:
    root_times: list[str] = []
    for location in payload.get("locations", []) or []:
        if not isinstance(location, dict):
            continue
        root = str(location.get("root", ""))
        if not root:
            continue
        root_times.append(file_mtime(Path(root) / "switchboard" / "node.manifest.json"))
    return latest_timestamp(
        file_mtime(settings.manifest_dir / "services.json"),
        file_mtime(settings.manifest_dir.parent / "manager.manifest.json"),
        _runtime_cache_generated(),
        *root_times,
    )


def _attach_record_freshness(
    record: dict[str, object],
    *,
    data_field: str,
    truth_as_of: str,
    source: str,
    refresh_action: str,
) -> dict[str, object]:
    data_as_of = str(record.get(data_field, "") or "")
    reason = "cache_older_than_truth" if truth_as_of and (not data_as_of or timestamp_before(data_as_of, truth_as_of)) else ""
    return {
        **record,
        **freshness_envelope(
            data_as_of=data_as_of,
            truth_as_of=truth_as_of,
            source=source,
            stale_reason=reason,
            refresh_action=refresh_action if reason else "",
        ),
    }


def _workspace_payload(workspace: WorkspaceManifest) -> dict[str, object]:
    payload = workspace.model_dump(mode="json")
    return {
        **payload,
        "company_id": payload.get("workspace_id", ""),
        "company_name": payload.get("name", ""),
    }


def _normalize_latest_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    normalized = dict(snapshot)
    normalized.setdefault("servers", [])
    normalized.setdefault("services", [])
    normalized.setdefault("repo_inventory", [])
    normalized.setdefault("docs_index", [])
    normalized.setdefault("logs_index", [])
    summary = normalized.setdefault("summary", {})
    if isinstance(summary, dict):
        summary.setdefault("status", "unverified")
        summary.setdefault("server_count", len(normalized["servers"]))
        summary.setdefault("service_count", len(normalized["services"]))
    return normalized


def _enrich_service_payload(payload: dict[str, object]) -> dict[str, object]:
    enriched = dict(payload)
    service_id = str(enriched.get("service_id") or "")
    if not service_id:
        return enriched
    runtime_state = snapshot_store.get_service_runtime_state(service_id)
    service_truth_as_of = _service_truth_as_of(enriched)
    enriched["runtime_checks"] = [
        _attach_record_freshness(
            dict(entry),
            data_field="checked_at",
            truth_as_of=service_truth_as_of,
            source="runtime_cache",
            refresh_action="Check ports",
        )
        for entry in runtime_state["runtime_checks"]
    ]
    enriched["node_sync"] = [
        _attach_record_freshness(
            dict(entry),
            data_field="timestamp",
            truth_as_of=service_truth_as_of,
            source="runtime_cache",
            refresh_action="Sync From Node",
        )
        for entry in runtime_state["node_sync"]
    ]
    try:
        saved_scope_generated_at = datetime.fromtimestamp(
            (manifest_store.settings.manifest_dir / "services.json").stat().st_mtime,
            timezone.utc,
        ).replace(microsecond=0).isoformat()
    except OSError:
        saved_scope_generated_at = str(runtime_state.get("generated", ""))
    enriched["saved_scope_generated_at"] = saved_scope_generated_at
    enriched["freshness"] = freshness_envelope(
        data_as_of=latest_timestamp(
            *(entry.get("checked_at", "") for entry in runtime_state["runtime_checks"]),
            *(entry.get("timestamp", "") for entry in runtime_state["node_sync"]),
        ),
        truth_as_of=service_truth_as_of,
        source="service_manifest",
        refresh_action="Collect",
    )
    enriched["node_viewer"] = freshen_node_viewers(
        manager_root=_manager_root(),
        service_payload=enriched,
        cached_rows=snapshot_store.get_service_node_viewer(service_id),
        control_center_version=__version__,
    )
    task_ledger = snapshot_store.get_service_task_ledger(service_id)
    enriched["task_ledger"] = [
        _attach_record_freshness(
            dict(entry),
            data_field="timestamp",
            truth_as_of=service_truth_as_of,
            source="runtime_cache",
            refresh_action="Sync From Node",
        )
        for entry in task_ledger.get("tasks", [])
    ]
    return enriched


def _enrich_latest_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_latest_snapshot(snapshot)
    workspace = normalized.get("workspace", {})
    workspace_id = str(workspace.get("workspace_id", "") if isinstance(workspace, dict) else "")
    manifest_services_by_id: dict[str, dict[str, object]] = {}
    current_workspace: dict[str, object] | None = None
    if workspace_id:
        try:
            current_workspace = _workspace_payload(manifest_store.get_workspace(workspace_id))
            normalized["workspace"] = current_workspace
            normalized["company"] = current_workspace
        except KeyError:
            pass
        manifest_services_by_id = {
            service.service_id: service.model_dump(mode="json")
            for service in manifest_store.load_services()
            if service.workspace_id == workspace_id
        }
    truth_as_of = _workspace_truth_as_of(workspace_id)
    data_as_of = str(normalized.get("generated", "") or "")
    snapshot_services_by_id = {
        str(service.get("service_id", "")): service
        for service in normalized.get("services", [])
        if isinstance(service, dict)
    }
    archived_service_ids = sorted(service_id for service_id in snapshot_services_by_id if service_id)
    current_service_ids = sorted(service_id for service_id in manifest_services_by_id if service_id)
    service_list_mismatch = bool(current_service_ids and archived_service_ids != current_service_ids)
    reason = (
        "archive_service_list_mismatch"
        if service_list_mismatch
        else "archive_older_than_truth"
        if truth_as_of and (not data_as_of or timestamp_before(data_as_of, truth_as_of))
        else ""
    )
    freshness = freshness_envelope(
        data_as_of=data_as_of,
        truth_as_of=truth_as_of,
        source="archive_snapshot",
        stale_reason=reason,
        refresh_action="Collect" if reason else "",
    )
    normalized["freshness"] = freshness
    normalized["archived_service_ids"] = archived_service_ids
    normalized["current_service_ids"] = current_service_ids
    summary = normalized.setdefault("summary", {})
    if isinstance(summary, dict):
        summary.update(freshness)
    service_sources = list(manifest_services_by_id.values()) or [
        service for service in normalized.get("services", []) if isinstance(service, dict)
    ]
    services = []
    for source in service_sources:
        service_id = str(source.get("service_id", ""))
        snapshot_service = snapshot_services_by_id.get(service_id, {})
        merged = {**snapshot_service, **source}
        for key in (
            "status",
            "ports",
            "firewall_status",
            "firewall_active",
            "repo_summaries",
            "docs_count",
            "doc_count",
            "logs_count",
            "log_count",
            "secret_path_count",
        ):
            if key in snapshot_service:
                merged[key] = snapshot_service[key]
        services.append(_enrich_service_payload(merged))
    normalized["services"] = services
    if isinstance(summary, dict):
        summary["service_count"] = len(services)
        if current_workspace is not None:
            summary["server_count"] = len(current_workspace.get("servers", []) or [])
    return normalized


def _raise_for_action_result(result: dict[str, object]) -> None:
    status = result.get("status")
    message = str(result.get("message") or result.get("output") or "Request failed.")
    if status == "action_in_progress":
        raise HTTPException(status_code=409, detail={"status": status, "message": message})
    if status == "permission_limited":
        raise HTTPException(status_code=403, detail={"status": status, "message": message})
    if status == "path_missing":
        raise HTTPException(status_code=422, detail={"status": status, "message": message})


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": __import__("datetime").datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "framework": "switchboard",
        "vpn_note": "If VPN is needed for a server, turn it on manually. Switchboard does not store VPN state.",
    }


@app.get("/api/exports/palimpsest")
def export_palimpsest() -> dict[str, object]:
    return coordinator.export_palimpsest_state()


@app.get("/api/workspaces")
def list_workspaces() -> dict[str, object]:
    workspaces = manifest_store.load_workspaces()
    services = manifest_store.load_services()
    return {
        "workspaces": [
            {
                **workspace.model_dump(mode="json"),
                "company_id": workspace.workspace_id,
                "company_name": workspace.name,
                "server_count": len(workspace.servers),
                "service_count": len([service for service in services if service.workspace_id == workspace.workspace_id]),
            }
            for workspace in workspaces
        ]
    }


@app.get("/api/servers")
def list_servers() -> dict[str, object]:
    return {"servers": [server.model_dump(mode="json") for server in manifest_store.load_servers()]}


@app.get("/api/workspaces/{workspace_id}")
def get_workspace(workspace_id: str) -> dict[str, object]:
    try:
        workspace = manifest_store.get_workspace(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    services = manifest_store.get_workspace_services(workspace_id)
    return {
        "workspace": {
            **workspace.model_dump(mode="json"),
            "company_id": workspace.workspace_id,
            "company_name": workspace.name,
        },
        "services": [_enrich_service_payload(service.model_dump(mode="json")) for service in services],
    }


@app.get("/api/workspaces/{workspace_id}/latest")
def get_workspace_latest(workspace_id: str) -> dict[str, object]:
    latest = snapshot_store.get_workspace_latest(workspace_id)
    if latest is None:
        try:
            workspace = manifest_store.get_workspace(workspace_id)
            services = manifest_store.get_workspace_services(workspace_id)
            servers = [
                manifest_store.get_server(server_id).model_dump(mode="json")
                for server_id in workspace.servers
            ]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        freshness = freshness_envelope(
            data_as_of="",
            truth_as_of=_workspace_truth_as_of(workspace_id),
            source="manifest",
            stale_reason="missing_latest_snapshot",
            refresh_action="Collect",
        )
        workspace_payload = _workspace_payload(workspace)
        return {
            "generated": None,
            "workspace": workspace_payload,
            "company": workspace_payload,
            "servers": [
                {
                    **server,
                    "status": "unverified",
                    "hostname": server.get("host"),
                    "services": [],
                    "docker": [],
                    "firewall": "unverified",
                    "ports": [],
                }
                for server in servers
            ],
            "services": [_enrich_service_payload(service.model_dump(mode="json")) for service in services],
            "repo_inventory": [],
            "docs_index": [],
            "logs_index": [],
            "freshness": freshness,
            "summary": {
                "status": "unverified",
                "server_count": len(workspace.servers),
                "service_count": len(services),
                **freshness,
            },
        }
    return _enrich_latest_snapshot(latest)


@app.get("/api/workspaces/{workspace_id}/runs")
def get_workspace_runs(workspace_id: str) -> dict[str, object]:
    return {"workspace_id": workspace_id, "runs": snapshot_store.get_workspace_runs(workspace_id)}


@app.get("/api/services/{service_id}")
def get_service(service_id: str) -> dict[str, object]:
    try:
        service = manifest_store.get_service(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"service": _enrich_service_payload(service.model_dump(mode="json"))}


@app.get("/api/services/{service_id}/scope")
def get_service_scope(service_id: str) -> dict[str, object]:
    try:
        service = manifest_store.get_service(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "service_id": service_id,
        "scope_entries": [entry.model_dump(mode="json") for entry in service.scope_entries],
        "repo_policies": [policy.model_dump(mode="json") for policy in service.repo_policies],
    }


@app.post("/api/discovery/scan-root")
def scan_root(request: ScanRootRequest) -> dict[str, object]:
    return coordinator.scan_root(request)


@app.post("/api/discovery/tree")
def browse_tree(request: DiscoveryTreeRequest) -> dict[str, object]:
    return coordinator.browse_tree(request)


@app.post("/api/workspaces/{workspace_id}/collect")
def collect_workspace(workspace_id: str, request: CollectRequest) -> dict[str, object]:
    try:
        return coordinator.collect_workspace(workspace_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/workspaces/{workspace_id}/services")
def create_service(workspace_id: str, request: ServiceCreateRequest) -> dict[str, object]:
    try:
        service = manifest_store.create_service(workspace_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"service": _enrich_service_payload(service.model_dump(mode="json"))}


@app.patch("/api/services/{service_id}")
def patch_service(service_id: str, request: ServicePatchRequest) -> dict[str, object]:
    try:
        service = manifest_store.patch_service(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"service": _enrich_service_payload(service.model_dump(mode="json"))}


@app.delete("/api/services/{service_id}")
def delete_service(service_id: str) -> dict[str, object]:
    try:
        service = manifest_store.delete_service(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return snapshot_store.delete_service_data(service_id, service.workspace_id)


@app.post("/api/services/{service_id}/downloads")
def download_files(service_id: str, request: DownloadRequest) -> dict[str, object]:
    try:
        return coordinator.download_files(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/services/{service_id}/actions/git-status")
def git_status(service_id: str, request: RepoActionRequest) -> dict[str, object]:
    try:
        return coordinator.git_status(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/services/{service_id}/actions/safety-check")
def safety_check(service_id: str, request: RepoActionRequest) -> dict[str, object]:
    try:
        return coordinator.safety_check(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/services/{service_id}/actions/git-pull")
def git_pull(service_id: str, request: GitPullRequest) -> dict[str, object]:
    try:
        result = coordinator.git_pull(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _raise_for_action_result(result)
    return result


@app.post("/api/services/{service_id}/actions/git-push")
def git_push(service_id: str, request: GitPushRequest) -> dict[str, object]:
    try:
        result = coordinator.git_push(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _raise_for_action_result(result)
    return result


@app.get("/api/github-backup/readiness")
def github_backup_readiness(workspace_id: str | None = None) -> dict[str, object]:
    return coordinator.github_backup_readiness(GitHubBackupRequest(workspace_id=workspace_id, dry_run=True))


@app.post("/api/github-backup/dry-run")
def github_backup_dry_run(request: GitHubBackupRequest) -> dict[str, object]:
    request = request.model_copy(update={"dry_run": True})
    return coordinator.github_backup_run(request)


@app.post("/api/github-backup/run")
def github_backup_run(request: GitHubBackupRequest) -> dict[str, object]:
    request = request.model_copy(update={"dry_run": False})
    result = coordinator.github_backup_run(request)
    _raise_for_action_result(result)
    return result


@app.post("/api/services/{service_id}/actions/runtime-check")
def runtime_check(service_id: str, request: RuntimeActionRequest) -> dict[str, object]:
    try:
        result = coordinator.runtime_check(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _raise_for_action_result(result)
    return result


@app.get("/api/project-environments/{environment_id}/lab")
def get_environment_lab(environment_id: str) -> dict[str, object]:
    try:
        return coordinator.get_environment_lab(environment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/project-environments/{environment_id}/runtime-snapshot")
def refresh_environment_runtime_snapshot(
    environment_id: str,
    request: EnvironmentRuntimeSnapshotRequest,
) -> dict[str, object]:
    try:
        return coordinator.environment_runtime_snapshot(environment_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/project-environments/{environment_id}/api-flows")
def list_api_flows(environment_id: str) -> dict[str, object]:
    try:
        return coordinator.list_api_flows(environment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/project-environments/{environment_id}/api-flows")
def create_api_flow(environment_id: str, request: ApiFlowCreateRequest) -> dict[str, object]:
    try:
        return coordinator.create_api_flow(environment_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/project-environments/{environment_id}/api-flows/{flow_id}")
def patch_api_flow(environment_id: str, flow_id: str, request: ApiFlowPatchRequest) -> dict[str, object]:
    try:
        return coordinator.patch_api_flow(environment_id, flow_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/project-environments/{environment_id}/api-flows/{flow_id}")
def delete_api_flow(environment_id: str, flow_id: str) -> dict[str, object]:
    try:
        return coordinator.delete_api_flow(environment_id, flow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/project-environments/{environment_id}/api-flows/{flow_id}/run")
def run_api_flow(environment_id: str, flow_id: str, request: ApiFlowRunRequest) -> dict[str, object]:
    try:
        result = coordinator.run_api_flow(environment_id, flow_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _raise_for_action_result(result)
    return result


@app.get("/api/project-environments/{environment_id}/api-flows/{flow_id}/runs")
def get_api_flow_runs(environment_id: str, flow_id: str) -> dict[str, object]:
    try:
        return coordinator.get_api_flow_runs(environment_id, flow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/project-environments/{environment_id}/pull-rollup")
def get_environment_pull_rollup(environment_id: str) -> dict[str, object]:
    try:
        return coordinator.get_environment_pull_rollup(environment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/services/{service_id}/actions/sync-from-node")
def sync_from_node(service_id: str, request: NodeSyncRequest) -> dict[str, object]:
    try:
        result = coordinator.sync_from_node(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _raise_for_action_result(result)
    if isinstance(result.get("service"), dict):
        result = {**result, "service": _enrich_service_payload(result["service"])}
    return result


@app.post("/api/services/{service_id}/actions/sync-to-node")
def sync_to_node(service_id: str, request: NodeSyncRequest) -> dict[str, object]:
    try:
        result = coordinator.sync_to_node(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _raise_for_action_result(result)
    return result


@app.get("/api/services/{service_id}/node-viewer")
def get_node_viewer(service_id: str) -> dict[str, object]:
    return coordinator.get_node_viewer(service_id)


@app.post("/api/services/{service_id}/actions/node-inspect")
def node_inspect(service_id: str, request: NodeActionRequest) -> dict[str, object]:
    result = coordinator.node_inspect(service_id, request)
    _raise_for_action_result(result)
    return result


@app.post("/api/services/{service_id}/actions/node-release-check")
def node_release_check(service_id: str, request: NodeActionRequest) -> dict[str, object]:
    result = coordinator.node_release_check(service_id, request)
    _raise_for_action_result(result)
    return result


@app.post("/api/services/{service_id}/actions/node-deploy")
def node_deploy(service_id: str, request: NodeActionRequest) -> dict[str, object]:
    result = coordinator.node_deploy(service_id, request)
    _raise_for_action_result(result)
    return result


@app.post("/api/services/{service_id}/actions/node-upgrade")
def node_upgrade(service_id: str, request: NodeActionRequest) -> dict[str, object]:
    result = coordinator.node_upgrade(service_id, request)
    _raise_for_action_result(result)
    return result


@app.post("/api/services/{service_id}/actions/node-restart")
def node_restart(service_id: str, request: NodeActionRequest) -> dict[str, object]:
    result = coordinator.node_restart(service_id, request)
    _raise_for_action_result(result)
    return result


@app.get("/api/services/{service_id}/pull-bundles")
def list_pull_bundles(service_id: str) -> dict[str, object]:
    try:
        manifest_store.get_service(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "service_id": service_id,
        "bundles": [
            coordinator.normalize_pull_bundle_record(bundle)
            for bundle in snapshot_store.list_pull_bundles(service_id)
        ],
    }


@app.get("/api/services/{service_id}/pull-bundles/{bundle_id}/exposure-review")
def get_pull_bundle_exposure_review(service_id: str, bundle_id: str) -> dict[str, object]:
    try:
        manifest_store.get_service(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    for bundle in snapshot_store.list_pull_bundles(service_id):
        if bundle.get("bundle_id") == bundle_id:
            normalized = coordinator.normalize_pull_bundle_record(bundle)
            return normalized.get("exposure_review", {"bundle_id": bundle_id, "groups": []})
    raise HTTPException(status_code=404, detail=f"bundle not found: {bundle_id}")


@app.get("/api/services/{service_id}/github-backup-dry-runs")
def list_service_github_backup_dry_runs(service_id: str) -> dict[str, object]:
    try:
        manifest_store.get_service(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "service_id": service_id,
        "runs": coordinator.list_github_backup_dry_runs(service_id),
    }


@app.post("/api/services/{service_id}/github-backup-dry-runs")
def create_service_github_backup_dry_run(service_id: str, request: PullBundleBackupDryRunRequest) -> dict[str, object]:
    try:
        result = coordinator.github_backup_dry_run_from_pull_bundle(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _raise_for_action_result(result)
    return result


@app.post("/api/services/{service_id}/pull-bundles")
def create_pull_bundle(service_id: str, request: PullBundleRequest) -> dict[str, object]:
    try:
        result = coordinator.pull_bundle(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _raise_for_action_result(result)
    return result


@app.post("/api/services/{service_id}/pull-bundles/preflight")
def preflight_pull_bundle(service_id: str, request: PullBundleRequest) -> dict[str, object]:
    try:
        result = coordinator.pull_bundle_preflight(service_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _raise_for_action_result(result)
    return result


@app.get("/api/services/{service_id}/secret-paths")
def get_secret_paths(service_id: str) -> dict[str, object]:
    try:
        manifest_store.get_service(service_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return snapshot_store.get_service_secret_paths(service_id)


@app.get("/api/servers")
def list_servers() -> dict[str, object]:
    return {"servers": [s.model_dump(mode="json") for s in manifest_store.load_servers()]}

@app.get("/api/services/{service_id}/task-ledger")
def get_service_task_ledger(service_id: str) -> dict[str, object]:
    ledger = snapshot_store.get_service_task_ledger(service_id)
    return {"tasks": ledger.get("tasks", [])}


@app.get("/api/services/{service_id}/action-locks")
def get_service_action_locks(service_id: str) -> dict[str, object]:
    cache = snapshot_store._read_runtime_cache()
    locks = snapshot_store._prune_expired_locks(cache).get("action_locks", {})
    return {"locks": [lock for key, lock in locks.items() if lock.get("service_id") == service_id]}


@app.post("/api/services/{service_id}/action-locks")
def acquire_service_action_lock(service_id: str, request: ActionLockRequest) -> dict[str, object]:
    lock = snapshot_store.acquire_action_lock(request.action_key, service_id)
    if lock is None:
        raise HTTPException(status_code=409, detail="Lock already active")
    return {"status": "ok", "lock": lock}


@app.delete("/api/services/{service_id}/action-locks/{action_key}")
def release_service_action_lock(service_id: str, action_key: str) -> dict[str, object]:
    lock = snapshot_store.release_action_lock(action_key, service_id)
    return {"status": "ok", "lock": lock}


@app.post("/api/workspaces/{workspace_id}/health-check")
def workspace_health_check(workspace_id: str, runtime_passwords: dict[str, str] | None = None) -> dict[str, object]:
    return coordinator.workspace_health_check(workspace_id, runtime_passwords)


@app.get("/api/workspaces/{workspace_id}/projects")
def list_workspace_projects(workspace_id: str) -> dict[str, object]:
    try:
        return coordinator.list_workspace_project_context(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/workspaces/{workspace_id}/projects")
def create_project(workspace_id: str, request: ProjectCreateRequest) -> dict[str, object]:
    try:
        project = manifest_store.create_project(workspace_id, request)
        return {"status": "ok", "project": project.model_dump(mode="json")}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/environments")
def create_project_environment(project_id: str, request: ProjectEnvironmentCreateRequest) -> dict[str, object]:
    try:
        environment = manifest_store.create_project_environment(project_id, request)
        return {"status": "ok", "environment": environment.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/companies")
def list_companies() -> dict[str, object]:
    return list_workspaces()


@app.post("/api/companies")
def create_company(request: WorkspaceCreateRequest) -> dict[str, object]:
    try:
        workspace = manifest_store.create_workspace(request)
        return {"status": "ok", "company": workspace.model_dump(mode="json")}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/companies/{company_id}")
def patch_company(company_id: str, request: WorkspacePatchRequest) -> dict[str, object]:
    try:
        workspace = manifest_store.patch_workspace(company_id, request)
        return {"status": "ok", "company": workspace.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/companies/{company_id}")
def delete_company(company_id: str) -> dict[str, object]:
    try:
        workspace = manifest_store.delete_workspace(company_id)
        return {"status": "ok", "company": workspace.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, request: ProjectPatchRequest) -> dict[str, object]:
    try:
        project = manifest_store.patch_project(project_id, request)
        return {"status": "ok", "project": project.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, object]:
    try:
        project = manifest_store.delete_project(project_id)
        return {"status": "ok", "project": project.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/project-environments/{environment_id}")
def patch_project_environment(environment_id: str, request: ProjectEnvironmentPatchRequest) -> dict[str, object]:
    try:
        environment = manifest_store.patch_project_environment(environment_id, request)
        return {"status": "ok", "environment": environment.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/project-environments/{environment_id}")
def delete_project_environment(environment_id: str) -> dict[str, object]:
    try:
        environment = manifest_store.delete_project_environment(environment_id)
        return {"status": "ok", "environment": environment.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/servers")
def create_server(request: ServerCreateRequest) -> dict[str, object]:
    try:
        server = manifest_store.create_server(request)
        return {"status": "ok", "server": server.model_dump(mode="json")}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/servers/{server_id}")
def patch_server(server_id: str, request: ServerPatchRequest) -> dict[str, object]:
    try:
        server = manifest_store.patch_server(server_id, request)
        return {"status": "ok", "server": server.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/servers/{server_id}")
def delete_server(server_id: str) -> dict[str, object]:
    try:
        server = manifest_store.delete_server(server_id)
        return {"status": "ok", "server": server.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
