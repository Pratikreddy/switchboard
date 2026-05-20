"""Manifest loading and mutation."""

from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import Settings
from .models import (
    ApiFlowCreateRequest,
    ApiFlowManifest,
    ApiFlowPatchRequest,
    ManagedDocConfig,
    ProjectCreateRequest,
    ProjectEnvironmentCreateRequest,
    ProjectEnvironmentManifest,
    ProjectEnvironmentPatchRequest,
    ProjectManifest,
    ProjectPatchRequest,
    RepoPolicy,
    ResolvedServer,
    ScopeEntry,
    ServerCreateRequest,
    ServerManifest,
    ServerPatchRequest,
    ServiceCreateRequest,
    ServiceManifest,
    ServicePatchRequest,
    WorkspaceCreateRequest,
    WorkspaceManifest,
    WorkspacePatchRequest,
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=False)
        handle.write("\n")


@lru_cache(maxsize=1)
def _load_local_env_files() -> dict[str, str]:
    values: dict[str, str] = {}
    for name in (".env", ".env.local"):
        path = Path.cwd() / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def server_env_key(server_id: str, suffix: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "_", server_id.upper())
    return f"SWITCHBOARD_SERVER_{token}_{suffix}"


def _upsert_local_env_value(key: str, value: str | None) -> None:
    path = Path.cwd() / ".env.local"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated = False
    retained: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            retained.append(line)
            continue
        current_key, _current_value = line.split("=", 1)
        if current_key.strip() != key:
            retained.append(line)
            continue
        updated = True
        if value:
            retained.append(f"{key}={value}")
    if value and not updated:
        retained.append(f"{key}={value}")
    path.write_text("\n".join(retained).rstrip() + ("\n" if retained else ""), encoding="utf-8")
    _load_local_env_files.cache_clear()


def _has_glob(path: str) -> bool:
    return any(token in path for token in ("*", "?", "["))


def _guess_path_type(path: str, kind: str) -> str:
    if kind == "exclude" or _has_glob(path):
        return "glob"
    if path.endswith("/"):
        return "dir"
    return "file" if Path(path).suffix else "dir"


def _scope_entry_id(kind: str, path: str) -> str:
    digest = hashlib.sha1(f"{kind}:{path}".encode("utf-8")).hexdigest()[:12]
    return f"{kind}-{digest}"


def _default_safety_profile(service_id: str, repo_path: str) -> str:
    token = f"{service_id}:{repo_path}".lower()
    return "secret_heavy" if "lambda" in token else "generic_python"


def _default_push_mode(service_id: str, repo_path: str) -> str:
    return "blocked" if _default_safety_profile(service_id, repo_path) == "secret_heavy" else "allowed"


def _scope_entries_from_record(item: dict[str, Any]) -> list[ScopeEntry]:
    if item.get("scope_entries"):
        entries = [ScopeEntry.model_validate(entry) for entry in item["scope_entries"]]
    else:
        entries = []
        for kind, source_field in (
            ("repo", "repo_paths"),
            ("doc", "docs_paths"),
            ("log", "log_paths"),
            ("exclude", "exclude_globs"),
        ):
            for path in item.get(source_field, []):
                entries.append(
                    ScopeEntry(
                        entry_id=_scope_entry_id(kind, path),
                        kind=kind,
                        path=path,
                        path_type=_guess_path_type(path, kind),
                        source="seeded",
                        enabled=True,
                    )
                )

    deduped: list[ScopeEntry] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (entry.kind, entry.path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            ScopeEntry(
                entry_id=entry.entry_id or _scope_entry_id(entry.kind, entry.path),
                kind=entry.kind,
                path=entry.path,
                path_type=entry.path_type,
                source=entry.source,
                enabled=entry.enabled,
            )
        )
    return deduped


def _flatten_scope(entries: list[ScopeEntry]) -> dict[str, list[str]]:
    repo_paths = [entry.path for entry in entries if entry.enabled and entry.kind == "repo"]
    docs_paths = [entry.path for entry in entries if entry.enabled and entry.kind == "doc"]
    log_paths = [entry.path for entry in entries if entry.enabled and entry.kind == "log"]
    exclude_globs = [entry.path for entry in entries if entry.enabled and entry.kind == "exclude"]
    return {
        "repo_paths": repo_paths,
        "docs_paths": docs_paths,
        "log_paths": log_paths,
        "exclude_globs": exclude_globs,
        "allowed_git_pull_paths": repo_paths,
    }


def _repo_policies_from_record(item: dict[str, Any], scope_entries: list[ScopeEntry]) -> list[RepoPolicy]:
    if item.get("repo_policies"):
        policies = [RepoPolicy.model_validate(policy) for policy in item["repo_policies"]]
    else:
        repo_paths = [entry.path for entry in scope_entries if entry.enabled and entry.kind == "repo"]
        policies = [
            RepoPolicy(
                repo_path=repo_path,
                push_mode=_default_push_mode(item.get("service_id", ""), repo_path),
                safety_profile=_default_safety_profile(item.get("service_id", ""), repo_path),
            )
            for repo_path in repo_paths
        ]

    deduped: list[RepoPolicy] = []
    seen: set[str] = set()
    for policy in policies:
        if policy.repo_path in seen:
            continue
        seen.add(policy.repo_path)
        deduped.append(policy)
    return deduped


def _default_managed_docs() -> list[ManagedDocConfig]:
    defaults = [
        ("readme", "README.md", False),
        ("api", "API.md", False),
        ("changelog", "CHANGELOG.md", False),
        ("handoff", "switchboard/local/control-center-handoff.md", True),
        ("runbook", "switchboard/local/runbook.md", True),
        ("approach_history", "switchboard/local/approach-history.md", True),
        ("doc_index_md", "switchboard/local/doc-index.md", True),
        ("doc_index_json", "switchboard/evidence/doc-index.json", True),
    ]
    return [
        ManagedDocConfig(doc_id=doc_id, path=path, enabled=enabled)
        for doc_id, path, enabled in defaults
    ]


def _managed_docs_from_record(item: dict[str, Any]) -> list[ManagedDocConfig]:
    entries = [ManagedDocConfig.model_validate(entry) for entry in item.get("managed_docs", [])]
    if not entries:
        entries = _default_managed_docs()

    deduped: list[ManagedDocConfig] = []
    seen: set[str] = set()
    defaults_by_id = {entry.doc_id: entry for entry in _default_managed_docs()}
    for entry in entries:
        if entry.doc_id in seen:
            continue
        seen.add(entry.doc_id)
        default = defaults_by_id.get(entry.doc_id)
        deduped.append(
            ManagedDocConfig(
                doc_id=entry.doc_id,
                path=entry.path or (default.path if default else ""),
                enabled=entry.enabled,
                generated_from=entry.generated_from,
                last_generated_at=entry.last_generated_at,
            )
        )
    for doc_id, default in defaults_by_id.items():
        if doc_id in seen:
            continue
        deduped.append(default)
    return deduped


def _normalize_service_record(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    scope_entries = _scope_entries_from_record(normalized)
    managed_docs = _managed_docs_from_record(normalized)
    repo_policies = _repo_policies_from_record(normalized, scope_entries)
    normalized["scope_entries"] = [entry.model_dump(mode="json") for entry in scope_entries]
    normalized["managed_docs"] = [entry.model_dump(mode="json") for entry in managed_docs]
    normalized["repo_policies"] = [policy.model_dump(mode="json") for policy in repo_policies]
    normalized.update(_flatten_scope(scope_entries))
    return normalized


class ManifestStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._servers_path = settings.manifest_dir / "servers.json"
        self._workspaces_path = settings.manifest_dir / "workspaces.json"
        self._services_path = settings.manifest_dir / "services.json"
        self._projects_path = settings.manifest_dir / "projects.json"
        self._project_environments_path = settings.manifest_dir / "project-environments.json"
        self._api_flows_path = settings.manifest_dir / "api-flows.json"

    def load_servers(self) -> list[ServerManifest]:
        server_rows = load_json(self._servers_path)
        memberships = {
            server_id: workspace.workspace_id
            for workspace in self.load_workspaces()
            for server_id in workspace.servers
        }
        normalized: list[ServerManifest] = []
        for item in server_rows:
            payload = dict(item)
            payload.setdefault("company_id", memberships.get(payload.get("server_id", ""), ""))
            payload.setdefault("deployment_mode", "native_agent")
            normalized.append(ServerManifest.model_validate(payload))
        return normalized

    def load_workspaces(self) -> list[WorkspaceManifest]:
        return [WorkspaceManifest.model_validate(item) for item in load_json(self._workspaces_path)]

    def load_services(self) -> list[ServiceManifest]:
        return [ServiceManifest.model_validate(_normalize_service_record(item)) for item in load_json(self._services_path)]

    def load_projects(self) -> list[ProjectManifest]:
        return [ProjectManifest.model_validate(item) for item in load_json(self._projects_path)]

    def load_project_environments(self) -> list[ProjectEnvironmentManifest]:
        if not self._project_environments_path.exists():
            return []
        return [
            ProjectEnvironmentManifest.model_validate(item)
            for item in load_json(self._project_environments_path)
        ]

    def load_api_flows(self) -> list[ApiFlowManifest]:
        if not self._api_flows_path.exists():
            return []
        return [ApiFlowManifest.model_validate(item) for item in load_json(self._api_flows_path)]

    def get_server(self, server_id: str) -> ServerManifest:
        for server in self.load_servers():
            if server.server_id == server_id:
                return server
        raise KeyError(f"Unknown server: {server_id}")

    def get_workspace(self, workspace_id: str) -> WorkspaceManifest:
        for workspace in self.load_workspaces():
            if workspace.workspace_id == workspace_id:
                return workspace
        raise KeyError(f"Unknown workspace: {workspace_id}")

    def create_workspace(self, payload: WorkspaceCreateRequest) -> WorkspaceManifest:
        existing = self.load_workspaces()
        if any(workspace.workspace_id == payload.workspace_id for workspace in existing):
            raise ValueError(f"Workspace already exists: {payload.workspace_id}")
        workspace = WorkspaceManifest.model_validate(
            {
                **payload.model_dump(mode="json"),
                "favorite_tier": "primary",
                "servers": [],
                "services": [],
            }
        )
        save_json(self._workspaces_path, [*load_json(self._workspaces_path), workspace.model_dump(mode="json")])
        return workspace

    def patch_workspace(self, workspace_id: str, payload: WorkspacePatchRequest) -> WorkspaceManifest:
        workspaces = load_json(self._workspaces_path)
        updated: WorkspaceManifest | None = None
        for index, item in enumerate(workspaces):
            if item["workspace_id"] != workspace_id:
                continue
            merged = {**item, **payload.model_dump(exclude_none=True, mode="json")}
            updated = WorkspaceManifest.model_validate(merged)
            workspaces[index] = updated.model_dump(mode="json")
            break
        if updated is None:
            raise KeyError(f"Unknown workspace: {workspace_id}")
        save_json(self._workspaces_path, workspaces)
        return updated

    def delete_workspace(self, workspace_id: str) -> WorkspaceManifest:
        workspace = self.get_workspace(workspace_id)
        if workspace.services or workspace.servers:
            raise ValueError("Company still has linked services or servers.")
        retained = [item for item in load_json(self._workspaces_path) if item["workspace_id"] != workspace_id]
        save_json(self._workspaces_path, retained)
        return workspace

    def get_service(self, service_id: str) -> ServiceManifest:
        for service in self.load_services():
            if service.service_id == service_id:
                return service
        raise KeyError(f"Unknown service: {service_id}")

    def get_workspace_services(self, workspace_id: str) -> list[ServiceManifest]:
        return [service for service in self.load_services() if service.workspace_id == workspace_id]

    def get_repo_policy(self, service_id: str, repo_path: str) -> RepoPolicy | None:
        service = self.get_service(service_id)
        for policy in service.repo_policies:
            if policy.repo_path == repo_path:
                return policy
        return None

    def resolve_server(
        self,
        server_id: str,
        runtime_passwords: dict[str, str] | None = None,
    ) -> ResolvedServer:
        server = self.get_server(server_id)
        runtime_passwords = runtime_passwords or {}
        env_values = _load_local_env_files()
        host = os.getenv(server_env_key(server_id, "HOST")) or env_values.get(server_env_key(server_id, "HOST"), server.host)
        username = os.getenv(server_env_key(server_id, "USERNAME")) or env_values.get(server_env_key(server_id, "USERNAME"), server.username)
        port = int(os.getenv(server_env_key(server_id, "PORT")) or env_values.get(server_env_key(server_id, "PORT"), str(server.port)))
        password = (
            runtime_passwords.get(server_id)
            or os.getenv(server_env_key(server_id, "PASSWORD"))
            or env_values.get(server_env_key(server_id, "PASSWORD"))
            or None
        )
        payload = server.model_dump()
        payload.update(
            {
                "host": host,
                "username": username,
                "port": port,
                "password": password,
            }
        )
        return ResolvedServer(
            **payload,
        )

    def create_service(self, workspace_id: str, payload: ServiceCreateRequest) -> ServiceManifest:
        self.get_workspace(workspace_id)
        existing = self.load_services()
        if any(service.service_id == payload.service_id for service in existing):
            raise ValueError(f"Service already exists: {payload.service_id}")
        service = ServiceManifest.model_validate(
            _normalize_service_record(
                {
                    "workspace_id": workspace_id,
                    **payload.model_dump(mode="json"),
                }
            )
        )
        save_json(self._services_path, [*load_json(self._services_path), service.model_dump(mode="json")])
        workspaces = load_json(self._workspaces_path)
        for workspace in workspaces:
            if workspace["workspace_id"] != workspace_id:
                continue
            services = workspace.setdefault("services", [])
            if payload.service_id not in services:
                services.append(payload.service_id)
            break
        save_json(self._workspaces_path, workspaces)
        return service

    def patch_service(self, service_id: str, payload: ServicePatchRequest) -> ServiceManifest:
        services = load_json(self._services_path)
        updated: ServiceManifest | None = None
        for index, item in enumerate(services):
            if item["service_id"] != service_id:
                continue
            merged = _normalize_service_record({**item, **payload.model_dump(exclude_none=True, mode="json")})
            updated = ServiceManifest.model_validate(merged)
            services[index] = updated.model_dump(mode="json")
            break
        if updated is None:
            raise KeyError(f"Unknown service: {service_id}")
        save_json(self._services_path, services)
        return updated

    def delete_service(self, service_id: str) -> ServiceManifest:
        services = load_json(self._services_path)
        removed: ServiceManifest | None = None
        retained: list[dict[str, Any]] = []

        for item in services:
            if item["service_id"] == service_id:
                removed = ServiceManifest.model_validate(_normalize_service_record(item))
                continue
            retained.append(item)

        if removed is None:
            raise KeyError(f"Unknown service: {service_id}")

        save_json(self._services_path, retained)

        workspaces = load_json(self._workspaces_path)
        for workspace in workspaces:
            services_list = workspace.setdefault("services", [])
            workspace["services"] = [item for item in services_list if item != service_id]
        save_json(self._workspaces_path, workspaces)
        return removed

    def get_project(self, project_id: str) -> ProjectManifest:
        for project in self.load_projects():
            if project.project_id == project_id:
                return project
        raise KeyError(f"Unknown project: {project_id}")

    def get_workspace_projects(self, workspace_id: str) -> list[ProjectManifest]:
        return [project for project in self.load_projects() if project.workspace_id == workspace_id]

    def get_project_environment(self, environment_id: str) -> ProjectEnvironmentManifest:
        for environment in self.load_project_environments():
            if environment.environment_id == environment_id:
                return environment
        raise KeyError(f"Unknown project environment: {environment_id}")

    def get_project_environments(self, project_id: str) -> list[ProjectEnvironmentManifest]:
        return [
            environment
            for environment in self.load_project_environments()
            if environment.project_id == project_id
        ]

    def get_environment_api_flows(self, environment_id: str) -> list[ApiFlowManifest]:
        return [flow for flow in self.load_api_flows() if flow.environment_id == environment_id]

    def get_api_flow(self, environment_id: str, flow_id: str) -> ApiFlowManifest:
        for flow in self.get_environment_api_flows(environment_id):
            if flow.flow_id == flow_id:
                return flow
        raise KeyError(f"Unknown API flow: {flow_id}")

    def get_workspace_project_environments(self, workspace_id: str) -> list[ProjectEnvironmentManifest]:
        project_ids = {project.project_id for project in self.get_workspace_projects(workspace_id)}
        return [
            environment
            for environment in self.load_project_environments()
            if environment.project_id in project_ids
        ]

    def _validated_project_service_ids(self, workspace_id: str, service_ids: list[str]) -> list[str]:
        workspace_service_ids = {
            service.service_id
            for service in self.load_services()
            if service.workspace_id == workspace_id
        }
        deduped: list[str] = []
        seen: set[str] = set()
        invalid: list[str] = []
        for raw_service_id in service_ids:
            service_id = raw_service_id.strip()
            if not service_id or service_id in seen:
                continue
            if service_id not in workspace_service_ids:
                invalid.append(service_id)
                continue
            seen.add(service_id)
            deduped.append(service_id)
        if invalid:
            raise ValueError(f"Service does not belong to workspace {workspace_id}: {', '.join(invalid)}")
        return deduped

    def _move_project_services(
        self,
        projects: list[dict[str, Any]],
        workspace_id: str,
        owner_project_id: str,
        service_ids: list[str],
    ) -> list[dict[str, Any]]:
        selected = set(service_ids)
        for item in projects:
            if item.get("workspace_id") != workspace_id or item.get("project_id") == owner_project_id:
                continue
            item["service_ids"] = [
                service_id
                for service_id in item.get("service_ids", [])
                if service_id not in selected
            ]
        return projects

    def create_project(self, workspace_id: str, payload: ProjectCreateRequest) -> ProjectManifest:
        self.get_workspace(workspace_id)
        existing = self.load_projects()
        if any(project.project_id == payload.project_id for project in existing):
            raise ValueError(f"Project already exists: {payload.project_id}")
        service_ids = self._validated_project_service_ids(workspace_id, payload.service_ids)
        project = ProjectManifest.model_validate(
            {
                "workspace_id": workspace_id,
                **payload.model_dump(mode="json", exclude={"service_ids"}),
                "service_ids": service_ids,
            }
        )
        projects = [item.model_dump(mode="json") for item in existing]
        projects.append(project.model_dump(mode="json"))
        projects = self._move_project_services(projects, workspace_id, project.project_id, service_ids)
        save_json(self._projects_path, projects)
        return project

    def patch_project(self, project_id: str, payload: ProjectPatchRequest) -> ProjectManifest:
        projects = load_json(self._projects_path)
        updated: ProjectManifest | None = None
        next_project_id = payload.project_id or project_id
        if next_project_id != project_id and any(item["project_id"] == next_project_id for item in projects):
            raise ValueError(f"Project already exists: {next_project_id}")
        for index, item in enumerate(projects):
            if item["project_id"] != project_id:
                continue
            payload_json = payload.model_dump(exclude_none=True, mode="json")
            if "parent_project_id" in payload.model_fields_set and payload.parent_project_id is None:
                payload_json["parent_project_id"] = None
            if payload.service_ids is not None:
                payload_json["service_ids"] = self._validated_project_service_ids(item["workspace_id"], payload.service_ids)
            merged = {**item, **payload_json}
            updated = ProjectManifest.model_validate(merged)
            projects[index] = updated.model_dump(mode="json")
            break
        if updated is None:
            raise KeyError(f"Unknown project: {project_id}")
        if payload.service_ids is not None:
            projects = self._move_project_services(projects, updated.workspace_id, next_project_id, updated.service_ids)
        if next_project_id != project_id:
            for item in projects:
                if item.get("parent_project_id") == project_id:
                    item["parent_project_id"] = next_project_id
        save_json(self._projects_path, projects)
        if next_project_id != project_id and self._project_environments_path.exists():
            environments = load_json(self._project_environments_path)
            for item in environments:
                if item.get("project_id") == project_id:
                    item["project_id"] = next_project_id
            save_json(self._project_environments_path, environments)
        return updated

    def delete_project(self, project_id: str) -> ProjectManifest:
        projects = load_json(self._projects_path)
        removed: ProjectManifest | None = None
        retained: list[dict[str, Any]] = []
        for item in projects:
            if item["project_id"] == project_id:
                removed = ProjectManifest.model_validate(item)
                continue
            retained.append(item)
        if removed is None:
            raise KeyError(f"Unknown project: {project_id}")
        save_json(self._projects_path, retained)
        if self._project_environments_path.exists():
            environments = [
                item
                for item in load_json(self._project_environments_path)
                if item.get("project_id") != project_id
            ]
            save_json(self._project_environments_path, environments)
        return removed

    def create_project_environment(
        self,
        project_id: str,
        payload: ProjectEnvironmentCreateRequest,
    ) -> ProjectEnvironmentManifest:
        self.get_project(project_id)
        existing = self.load_project_environments()
        if any(environment.environment_id == payload.environment_id for environment in existing):
            raise ValueError(f"Project environment already exists: {payload.environment_id}")
        environment = ProjectEnvironmentManifest.model_validate(
            {
                "project_id": project_id,
                **payload.model_dump(mode="json"),
            }
        )
        base = load_json(self._project_environments_path) if self._project_environments_path.exists() else []
        save_json(
            self._project_environments_path,
            [*base, environment.model_dump(mode="json")],
        )
        return environment

    def patch_project_environment(
        self,
        environment_id: str,
        payload: ProjectEnvironmentPatchRequest,
    ) -> ProjectEnvironmentManifest:
        environments = load_json(self._project_environments_path) if self._project_environments_path.exists() else []
        updated: ProjectEnvironmentManifest | None = None
        next_environment_id = payload.environment_id or environment_id
        if next_environment_id != environment_id and any(
            item["environment_id"] == next_environment_id for item in environments
        ):
            raise ValueError(f"Project environment already exists: {next_environment_id}")
        for index, item in enumerate(environments):
            if item["environment_id"] != environment_id:
                continue
            merged = {**item, **payload.model_dump(exclude_none=True, mode="json")}
            updated = ProjectEnvironmentManifest.model_validate(merged)
            environments[index] = updated.model_dump(mode="json")
            break
        if updated is None:
            raise KeyError(f"Unknown project environment: {environment_id}")
        save_json(self._project_environments_path, environments)
        return updated

    def delete_project_environment(self, environment_id: str) -> ProjectEnvironmentManifest:
        environments = load_json(self._project_environments_path) if self._project_environments_path.exists() else []
        removed: ProjectEnvironmentManifest | None = None
        retained: list[dict[str, Any]] = []
        for item in environments:
            if item["environment_id"] == environment_id:
                removed = ProjectEnvironmentManifest.model_validate(item)
                continue
            retained.append(item)
        if removed is None:
            raise KeyError(f"Unknown project environment: {environment_id}")
        save_json(self._project_environments_path, retained)
        if self._api_flows_path.exists():
            save_json(
                self._api_flows_path,
                [item for item in load_json(self._api_flows_path) if item.get("environment_id") != environment_id],
            )
        return removed

    def create_api_flow(self, environment_id: str, payload: ApiFlowCreateRequest) -> ApiFlowManifest:
        self.get_project_environment(environment_id)
        existing = self.load_api_flows()
        if any(flow.flow_id == payload.flow_id for flow in existing):
            raise ValueError(f"API flow already exists: {payload.flow_id}")
        flow = ApiFlowManifest.model_validate(
            {
                "environment_id": environment_id,
                **payload.model_dump(mode="json"),
            }
        )
        base = load_json(self._api_flows_path) if self._api_flows_path.exists() else []
        save_json(self._api_flows_path, [*base, flow.model_dump(mode="json")])
        return flow

    def patch_api_flow(self, environment_id: str, flow_id: str, payload: ApiFlowPatchRequest) -> ApiFlowManifest:
        flows = load_json(self._api_flows_path) if self._api_flows_path.exists() else []
        updated: ApiFlowManifest | None = None
        next_flow_id = payload.flow_id or flow_id
        if next_flow_id != flow_id and any(item["flow_id"] == next_flow_id for item in flows):
            raise ValueError(f"API flow already exists: {next_flow_id}")
        for index, item in enumerate(flows):
            if item.get("environment_id") != environment_id or item["flow_id"] != flow_id:
                continue
            merged = {**item, **payload.model_dump(exclude_none=True, mode="json")}
            updated = ApiFlowManifest.model_validate(merged)
            flows[index] = updated.model_dump(mode="json")
            break
        if updated is None:
            raise KeyError(f"Unknown API flow: {flow_id}")
        save_json(self._api_flows_path, flows)
        return updated

    def delete_api_flow(self, environment_id: str, flow_id: str) -> ApiFlowManifest:
        flows = load_json(self._api_flows_path) if self._api_flows_path.exists() else []
        removed: ApiFlowManifest | None = None
        retained: list[dict[str, Any]] = []
        for item in flows:
            if item.get("environment_id") == environment_id and item.get("flow_id") == flow_id:
                removed = ApiFlowManifest.model_validate(item)
                continue
            retained.append(item)
        if removed is None:
            raise KeyError(f"Unknown API flow: {flow_id}")
        save_json(self._api_flows_path, retained)
        return removed

    def create_server(self, payload: ServerCreateRequest) -> ServerManifest:
        existing = self.load_servers()
        if any(server.server_id == payload.server_id for server in existing):
            raise ValueError(f"Server already exists: {payload.server_id}")
        if payload.company_id:
            self.get_workspace(payload.company_id)
        payload_json = payload.model_dump(mode="json", exclude={"local_password"})
        server = ServerManifest.model_validate(payload_json)
        save_json(self._servers_path, [*load_json(self._servers_path), server.model_dump(mode="json")])
        self._assign_server_to_workspace(server.server_id, payload.company_id)
        if payload.local_password is not None:
            _upsert_local_env_value(server_env_key(server.server_id, "PASSWORD"), payload.local_password)
        return server

    def patch_server(self, server_id: str, payload: ServerPatchRequest) -> ServerManifest:
        servers = load_json(self._servers_path)
        updated: ServerManifest | None = None
        company_id = payload.company_id
        if company_id:
            self.get_workspace(company_id)
        for index, item in enumerate(servers):
            if item["server_id"] != server_id:
                continue
            merged = {**item, **payload.model_dump(exclude_none=True, mode="json", exclude={"local_password"})}
            updated = ServerManifest.model_validate(merged)
            servers[index] = updated.model_dump(mode="json")
            break
        if updated is None:
            raise KeyError(f"Unknown server: {server_id}")
        save_json(self._servers_path, servers)
        self._assign_server_to_workspace(server_id, company_id if company_id is not None else updated.company_id)
        if payload.local_password is not None:
            _upsert_local_env_value(server_env_key(server_id, "PASSWORD"), payload.local_password)
        return updated

    def delete_server(self, server_id: str) -> ServerManifest:
        servers = load_json(self._servers_path)
        removed: ServerManifest | None = None
        retained: list[dict[str, Any]] = []
        for item in servers:
            if item["server_id"] == server_id:
                removed = ServerManifest.model_validate(item)
                continue
            retained.append(item)
        if removed is None:
            raise KeyError(f"Unknown server: {server_id}")
        save_json(self._servers_path, retained)
        self._assign_server_to_workspace(server_id, "")
        _upsert_local_env_value(server_env_key(server_id, "PASSWORD"), None)
        return removed

    def _assign_server_to_workspace(self, server_id: str, workspace_id: str) -> None:
        workspaces = load_json(self._workspaces_path)
        for workspace in workspaces:
            servers = workspace.setdefault("servers", [])
            workspace["servers"] = [item for item in servers if item != server_id]
            if workspace["workspace_id"] == workspace_id and server_id not in workspace["servers"]:
                workspace["servers"].append(server_id)
        save_json(self._workspaces_path, workspaces)
