"""Pydantic models for manifests and requests."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .defaults import DEFAULT_NODE_PORT


FavoriteTier = Literal["primary", "secondary", "none"]
OwnershipTier = Literal["owned", "shared", "infra"]
ConnectionType = Literal["local", "ssh"]
DeploymentMode = Literal["native_agent", "local_bundle_only"]
ScopeKind = Literal["repo", "code", "doc", "log", "exclude"]
ScopePathType = Literal["file", "dir", "glob"]
ScopeSource = Literal["seeded", "user_added", "node_manifest", "tasks_completed", "manual_consolidation"]
PushMode = Literal["allowed", "blocked"]
SafetyProfile = Literal["generic_python", "secret_heavy"]
MonitoringMode = Literal["manual", "detect", "node_managed"]
ManagedDocId = Literal[
    "readme",
    "api",
    "changelog",
    "handoff",
    "runbook",
    "approach_history",
    "doc_index_md",
    "doc_index_json",
]
ActionStatus = Literal[
    "ok",
    "partial",
    "auth_failed",
    "unreachable",
    "vpn_or_network_blocked",
    "command_missing",
    "path_missing",
    "not_git_repo",
    "dirty_repo",
    "permission_limited",
    "skipped_by_exclude",
    "unverified",
    "action_in_progress",
]
ServiceKind = Literal[
    "service",
    "external_service",
    "database",
    "deployment_host",
    "dependency_node",
]
UsageEvidenceKind = Literal["model", "tool", "api", "runtime", "storage", "manual", "human_ui", "tokens"]
BoundaryStatus = Literal["active", "projection_only", "deferred", "parked"]
DocLifecycleState = Literal[
    "current",
    "disabled",
    "stale_after_latest_task",
    "generated_no_contributors",
    "manual_or_missing",
    "unverified",
]
DependencyKind = Literal[
    "service",
    "database",
    "deployment_host",
    "saas",
    "shared_data",
    "api",
    "runtime",
    "library",
]
ExecutionMode = Literal["networked", "batch", "lambda", "docs_only"]
ProjectEnvironmentKind = Literal["dev", "test", "staging", "qa", "prod", "custom"]
ApiFlowTargetKind = Literal["service", "dependency", "cross_dependency"]
CaptureSource = Literal["json", "header"]
PortExposure = Literal["local_only", "public", "unknown"]
FlowExecutionMode = Literal["http"]


class ServerManifest(BaseModel):
    server_id: str
    company_id: str = ""
    name: str
    connection_type: ConnectionType
    host: str
    username: str
    port: int = 22
    deployment_mode: DeploymentMode = "native_agent"
    vpn_required: bool = False
    tags: list[str] = Field(default_factory=list)
    favorite_tier: FavoriteTier = "none"
    notes: str = ""


class ResolvedServer(ServerManifest):
    password: str | None = None


class RuntimeConfig(BaseModel):
    expected_ports: list[int] = Field(default_factory=list)
    healthcheck_command: str = ""
    run_command_hint: str = ""
    monitoring_mode: MonitoringMode = "manual"
    notes: str = ""

    @field_validator("expected_ports")
    @classmethod
    def validate_expected_ports(cls, value: list[int]) -> list[int]:
        deduped: list[int] = []
        for port in value:
            if port < 1 or port > 65535:
                raise ValueError("expected_ports entries must be between 1 and 65535")
            if port not in deduped:
                deduped.append(port)
        return deduped


class LocationSpec(BaseModel):
    location_id: str
    server_id: str
    access_mode: ConnectionType
    root: str
    role: str
    is_primary: bool = False
    path_aliases: list[str] = Field(default_factory=list)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


class ManagedDocConfig(BaseModel):
    doc_id: ManagedDocId
    path: str
    enabled: bool = False
    generated_from: str = "switchboard/local/tasks-completed.md"
    last_generated_at: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("managed doc path must not be empty")
        return trimmed


class ScopeEntry(BaseModel):
    entry_id: str | None = None
    kind: ScopeKind
    path: str
    path_type: ScopePathType
    source: ScopeSource = "user_added"
    enabled: bool = True

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("path must not be empty")
        return trimmed


class RepoPolicy(BaseModel):
    repo_path: str
    push_mode: PushMode = "allowed"
    safety_profile: SafetyProfile = "generic_python"
    allowed_branches: list[str] = Field(default_factory=list)
    allowed_remotes: list[str] = Field(default_factory=list)

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("repo_path must not be empty")
        return trimmed


class RuntimeService(BaseModel):
    name: str
    host: str = ""
    port: int | None = None
    purpose: str = ""
    health_path: str = ""
    owner: str = ""


class DependencyNode(BaseModel):
    kind: DependencyKind
    name: str
    host: str = ""
    port: int | None = None
    notes: str = ""


class TaskLedgerEntry(BaseModel):
    timestamp: str
    title: str
    task_id: str | None = None
    agent: str = ""
    tool: str = ""
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    changed_paths: list[str] = Field(default_factory=list)
    version: str = ""
    bootstrap_version: str = ""
    runtime_services: list[RuntimeService] = Field(default_factory=list)
    dependencies: list[DependencyNode] = Field(default_factory=list)
    cross_dependencies: list[DependencyNode] = Field(default_factory=list)
    brick_entries: list[dict[str, Any]] = Field(default_factory=list)
    diagram: str = ""
    notes: list[str] = Field(default_factory=list)
    scope_entries: list[dict] = Field(default_factory=list)
    runtime: dict = Field(default_factory=dict)
    readme: str = ""
    api: str = ""
    changelog: str = ""


class FoundationPrivacyPolicy(BaseModel):
    classification: Literal["git_safe_metadata"] = "git_safe_metadata"
    raw_payloads: Literal["excluded"] = "excluded"
    private_cost_payloads: Literal["excluded"] = "excluded"
    token_payloads: Literal["count_only_if_explicitly_sanitized"] = "count_only_if_explicitly_sanitized"
    forbidden_sources: list[str] = Field(default_factory=list)


class UsageEvidenceEntry(BaseModel):
    entry_id: str
    evidence_kind: UsageEvidenceKind
    source: str
    source_kind: str = ""
    service_id: str = ""
    status: str = "observed"
    count: int = 0
    latest_at: str = ""
    token_count: int | None = None
    labels: list[str] = Field(default_factory=list)
    private_payload: Literal["excluded"] = "excluded"
    notes: str = ""


class ProductionUsageLedger(BaseModel):
    generated: str
    schema_version: Literal["production-usage-v0"] = "production-usage-v0"
    privacy: FoundationPrivacyPolicy = Field(default_factory=FoundationPrivacyPolicy)
    evidence_kinds: list[UsageEvidenceKind] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    entries: list[UsageEvidenceEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AgentHandoffQualityProjection(BaseModel):
    generated: str
    schema_version: Literal["agent-handoff-quality-v0"] = "agent-handoff-quality-v0"
    source: Literal["task_ledgers"] = "task_ledgers"
    task_count: int = 0
    handoff_tag_count: int = 0
    with_read_back: int = 0
    with_scope_check: int = 0
    with_changed_paths: int = 0
    with_agent: int = 0
    with_tool: int = 0
    with_verification_hint: int = 0
    quality_score: int = 0
    missing: dict[str, int] = Field(default_factory=dict)
    latest_records: list[dict[str, Any]] = Field(default_factory=list)
    privacy: FoundationPrivacyPolicy = Field(default_factory=FoundationPrivacyPolicy)


class DocsLifecycleEntry(BaseModel):
    doc_id: str
    path: str
    enabled: bool = False
    generated_at: str = ""
    generated_from: str = ""
    contributor_count: int = 0
    latest_contributor_at: str = ""
    lifecycle_state: DocLifecycleState = "unverified"
    memory_role: str = ""


class DocsRelevanceProjection(BaseModel):
    generated: str
    schema_version: Literal["docs-relevance-v0"] = "docs-relevance-v0"
    source: Literal["switchboard/evidence/doc-index.json"] = "switchboard/evidence/doc-index.json"
    latest_task_at: str = ""
    doc_count: int = 0
    enabled_count: int = 0
    current_count: int = 0
    stale_count: int = 0
    docs: list[DocsLifecycleEntry] = Field(default_factory=list)
    privacy: FoundationPrivacyPolicy = Field(default_factory=FoundationPrivacyPolicy)


class SuiteBoundary(BaseModel):
    boundary_id: str
    status: BoundaryStatus
    owner_system: str
    allowed: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class SuiteBoundaryRegistry(BaseModel):
    generated: str
    schema_version: Literal["suite-boundaries-v0"] = "suite-boundaries-v0"
    source: Literal["manifests_and_manager_rules"] = "manifests_and_manager_rules"
    suites: list[dict[str, Any]] = Field(default_factory=list)
    boundaries: list[SuiteBoundary] = Field(default_factory=list)
    privacy: FoundationPrivacyPolicy = Field(default_factory=FoundationPrivacyPolicy)


class FoundationProjection(BaseModel):
    generated: str
    schema_version: Literal["switchboard-pass1-foundation-v0"] = "switchboard-pass1-foundation-v0"
    privacy: FoundationPrivacyPolicy = Field(default_factory=FoundationPrivacyPolicy)
    line_noise: dict[str, Any] = Field(default_factory=dict)
    production_usage: ProductionUsageLedger
    agent_handoff_quality: AgentHandoffQualityProjection
    docs_relevance: DocsRelevanceProjection
    harness_source_map: dict[str, Any] = Field(default_factory=dict)
    suite_boundaries: SuiteBoundaryRegistry
    notes: list[str] = Field(default_factory=list)


class ProjectManifest(BaseModel):
    project_id: str
    workspace_id: str
    display_name: str
    parent_project_id: str | None = None
    service_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class ProjectDeploymentRef(BaseModel):
    service_id: str
    location_id: str | None = None
    server_id: str | None = None
    root: str | None = None
    version: str = ""
    runtime_services: list[RuntimeService] = Field(default_factory=list)
    dependencies: list[DependencyNode] = Field(default_factory=list)
    cross_dependencies: list[DependencyNode] = Field(default_factory=list)
    notes: str = ""


class ProjectEnvironmentManifest(BaseModel):
    environment_id: str
    project_id: str
    display_name: str
    kind: ProjectEnvironmentKind = "custom"
    deployments: list[ProjectDeploymentRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class ProjectPullSummary(BaseModel):
    project_id: str
    environment_id: str | None = None
    added_count: int = 0
    removed_count: int = 0
    changed_count: int = 0
    unchanged_count: int = 0
    latest_created_at: str = ""
    service_count: int = 0


class ApiStepCapture(BaseModel):
    variable_name: str
    source: CaptureSource = "json"
    selector: str


class ApiFlowStep(BaseModel):
    step_id: str
    order: int = 0
    display_name: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    path: str = ""
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    expected_status: int = 200
    continue_on_failure: bool = False
    timeout_seconds: int = 15
    notes: str = ""
    captures: list[ApiStepCapture] = Field(default_factory=list)


class ApiFlowManifest(BaseModel):
    flow_id: str
    environment_id: str
    service_id: str | None = None
    display_name: str
    target_kind: ApiFlowTargetKind = "service"
    target_name: str = ""
    base_url: str = ""
    execution_mode: FlowExecutionMode = "http"
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    steps: list[ApiFlowStep] = Field(default_factory=list)


class ApiStepRunResult(BaseModel):
    step_id: str
    status: Literal["ok", "failed", "skipped"] = "ok"
    resolved_url: str = ""
    duration_ms: int = 0
    request_preview: dict[str, object] = Field(default_factory=dict)
    response_status: int = 0
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body_preview: str = ""
    extracted_variables: dict[str, str] = Field(default_factory=dict)
    generated_curl: str = ""
    error: str = ""


class ApiFlowRunRecord(BaseModel):
    run_id: str
    flow_id: str
    environment_id: str
    started_at: str
    finished_at: str = ""
    status: Literal["ok", "partial", "failed"] = "ok"
    step_results: list[ApiStepRunResult] = Field(default_factory=list)
    summary: str = ""


class OperatorCommand(BaseModel):
    category: Literal["inspect_only", "verify_listener", "verify_firewall", "verify_health", "verify_node"] = "inspect_only"
    label: str
    command: str
    notes: str = ""


class ProcessFinding(BaseModel):
    port: int | None = None
    bind_address: str = ""
    process_name: str = ""
    pid: int | None = None
    state: str = ""
    raw: str = ""
    owner_service_id: str = ""
    owner_display_name: str = ""
    owner_location_id: str = ""
    owner_root: str = ""


class PortExposureFinding(BaseModel):
    host: str = ""
    port: int
    bind_address: str = ""
    process_name: str = ""
    expected: bool = False
    exposure: PortExposure = "unknown"
    notes: str = ""


class EnvironmentLocationSnapshot(BaseModel):
    service_id: str
    service_name: str = ""
    execution_mode: ExecutionMode = "networked"
    location_id: str = ""
    server_id: str = ""
    root: str = ""
    host: str = ""
    firewall_status: str = "unverified"
    node_status: str = "missing"
    expected_ports: list[int] = Field(default_factory=list)
    open_ports: list[int] = Field(default_factory=list)
    unexpected_ports: list[int] = Field(default_factory=list)
    exposed_ports: list[PortExposureFinding] = Field(default_factory=list)
    process_findings: list[ProcessFinding] = Field(default_factory=list)
    operator_commands: list[OperatorCommand] = Field(default_factory=list)
    runtime_hint: str = ""
    healthcheck_command: str = ""
    healthcheck_status: str = "skipped"
    healthcheck_output: str = ""


class EnvironmentRuntimeSnapshot(BaseModel):
    environment_id: str
    captured_at: str
    locations: list[EnvironmentLocationSnapshot] = Field(default_factory=list)
    open_ports: list[int] = Field(default_factory=list)
    expected_ports: list[int] = Field(default_factory=list)
    unexpected_ports: list[int] = Field(default_factory=list)
    exposed_ports: list[PortExposureFinding] = Field(default_factory=list)
    firewall_status: str = "unverified"
    process_findings: list[ProcessFinding] = Field(default_factory=list)
    node_findings: list[dict[str, object]] = Field(default_factory=list)
    operator_commands: list[OperatorCommand] = Field(default_factory=list)


class ServiceManifest(BaseModel):
    service_id: str
    workspace_id: str
    display_name: str
    kind: ServiceKind = "service"
    execution_mode: ExecutionMode = "networked"
    ownership_tier: OwnershipTier = "owned"
    tags: list[str] = Field(default_factory=list)
    favorite_tier: FavoriteTier = "none"
    locations: list[LocationSpec] = Field(default_factory=list)
    repo_paths: list[str] = Field(default_factory=list)
    docs_paths: list[str] = Field(default_factory=list)
    log_paths: list[str] = Field(default_factory=list)
    allowed_git_pull_paths: list[str] = Field(default_factory=list)
    exclude_globs: list[str] = Field(default_factory=list)
    scope_entries: list[ScopeEntry] = Field(default_factory=list)
    managed_docs: list[ManagedDocConfig] = Field(default_factory=list)
    repo_policies: list[RepoPolicy] = Field(default_factory=list)
    notes: str = ""
    path_aliases: list[str] = Field(default_factory=list)


class WorkspaceManifest(BaseModel):
    workspace_id: str
    name: str
    tags: list[str] = Field(default_factory=list)
    favorite_tier: FavoriteTier = "none"
    servers: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    notes: str = ""


class WorkspaceCreateRequest(BaseModel):
    workspace_id: str
    name: str
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class WorkspacePatchRequest(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


class CollectRequest(BaseModel):
    runtime_passwords: dict[str, str] = Field(default_factory=dict)
    service_ids: list[str] = Field(default_factory=list)
    include_node_sync: bool = True

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):  # type: ignore[override]
        if isinstance(obj, dict):
            obj = {
                **obj,
                "runtime_passwords": obj.get("runtime_passwords", obj.get("password_overrides", {})),
                "service_ids": obj.get("service_ids", obj.get("service_filter", [])),
                "include_node_sync": obj.get(
                    "include_node_sync",
                    obj.get("sync_from_nodes", obj.get("bulk_sync_nodes", True)),
                ),
            }
        return super().model_validate(obj, *args, **kwargs)


class ServiceCreateRequest(BaseModel):
    service_id: str
    display_name: str
    kind: ServiceKind = "service"
    execution_mode: ExecutionMode = "networked"
    ownership_tier: OwnershipTier = "owned"
    tags: list[str] = Field(default_factory=list)
    favorite_tier: FavoriteTier = "none"
    locations: list[LocationSpec] = Field(default_factory=list)
    repo_paths: list[str] = Field(default_factory=list)
    docs_paths: list[str] = Field(default_factory=list)
    log_paths: list[str] = Field(default_factory=list)
    allowed_git_pull_paths: list[str] = Field(default_factory=list)
    exclude_globs: list[str] = Field(default_factory=list)
    scope_entries: list[ScopeEntry] = Field(default_factory=list)
    managed_docs: list[ManagedDocConfig] = Field(default_factory=list)
    repo_policies: list[RepoPolicy] = Field(default_factory=list)
    notes: str = ""
    path_aliases: list[str] = Field(default_factory=list)


class ServicePatchRequest(BaseModel):
    display_name: str | None = None
    kind: ServiceKind | None = None
    execution_mode: ExecutionMode | None = None
    ownership_tier: OwnershipTier | None = None
    tags: list[str] | None = None
    favorite_tier: FavoriteTier | None = None
    locations: list[LocationSpec] | None = None
    repo_paths: list[str] | None = None
    docs_paths: list[str] | None = None
    log_paths: list[str] | None = None
    allowed_git_pull_paths: list[str] | None = None
    exclude_globs: list[str] | None = None
    scope_entries: list[ScopeEntry] | None = None
    managed_docs: list[ManagedDocConfig] | None = None
    repo_policies: list[RepoPolicy] | None = None
    notes: str | None = None
    path_aliases: list[str] | None = None


class DownloadRequest(BaseModel):
    server_id: str | None = None
    kind: Literal["doc", "log"]
    files: list[str] = Field(default_factory=list)
    runtime_password: str | None = None


class GitPullRequest(BaseModel):
    repo_path: str = Field(min_length=1)
    server_id: str | None = None
    runtime_password: str | None = None

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("repo_path must not be empty")
        return trimmed


class RepoActionRequest(BaseModel):
    repo_path: str = Field(min_length=1)
    server_id: str | None = None
    runtime_password: str | None = None

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("repo_path must not be empty")
        return trimmed


class GitPushRequest(RepoActionRequest):
    remote: str | None = None
    branch: str | None = None


class GitHubBackupRequest(BaseModel):
    workspace_id: str | None = None
    service_ids: list[str] = Field(default_factory=list)
    runtime_passwords: dict[str, str] = Field(default_factory=dict)
    remote: str = "origin"
    dry_run: bool = True


class PullBundleBackupDryRunRequest(BaseModel):
    bundle_id: str | None = None


class ScanRootRequest(BaseModel):
    server_id: str
    root: str
    runtime_password: str | None = None
    max_depth: int = Field(default=2, ge=0, le=4)

    @field_validator("root")
    @classmethod
    def validate_root(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("root must not be empty")
        return trimmed


class DiscoveryTreeRequest(BaseModel):
    server_id: str
    root: str
    node_path: str | None = None
    runtime_password: str | None = None

    @field_validator("root")
    @classmethod
    def validate_root(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("root must not be empty")
        return trimmed

    @field_validator("node_path")
    @classmethod
    def validate_node_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        return trimmed


class PullBundleRequest(BaseModel):
    server_id: str | None = None
    location_id: str | None = None
    runtime_password: str | None = None
    extra_includes: list[ScopeEntry] = Field(default_factory=list)
    extra_excludes: list[str] = Field(default_factory=list)
    note: str = ""


class RuntimeActionRequest(BaseModel):
    location_id: str | None = None
    runtime_password: str | None = None


class NodeActionRequest(RuntimeActionRequest):
    pass


class NodeSyncRequest(BaseModel):
    location_id: str | None = None
    runtime_password: str | None = None
    include_scope_snapshot: bool = True
    include_runtime_config: bool = True
    include_task_ledger: bool = True
    include_dependency_context: bool = True


class ActionLockRequest(BaseModel):
    action_key: str


class PullBundleDiffEntry(BaseModel):
    change: Literal["added", "removed", "changed"]
    relative_path: str
    kind: Literal["repo", "code", "doc", "log"]


class PullBundleDiffSummary(BaseModel):
    added_count: int = 0
    removed_count: int = 0
    changed_count: int = 0
    unchanged_count: int = 0
    summary: str = ""


class ExposureFinding(BaseModel):
    relative_path: str
    finding_kind: str
    variable_name: str = ""
    line_number: int = 0
    redacted: bool = True


class NodeInspectResult(BaseModel):
    service_id: str
    location_id: str
    server_id: str
    root: str
    node_present: bool = False
    bootstrap_ready: bool = False
    runtime_ready: bool = False
    installed_version: str = ""
    bootstrap_version: str = ""
    manifest_updated_at: str = ""
    runtime_status: Literal["running", "stopped", "running_unmanaged", "missing", "manager_running"] = "missing"
    runtime_pid: int | None = None
    runtime_port: int = DEFAULT_NODE_PORT
    runtime_port_source: str = ""
    needs_install: bool = False
    needs_upgrade: bool = False
    needs_bootstrap: bool = False
    attention_reason: str = ""
    manifest_path: str = ""
    runtime_dir: str = ""
    log_file: str = ""
    last_error: str = ""
    installed_release_version: str = ""
    installed_release_asset_id: str = ""
    installed_release_asset_name: str = ""
    installed_release_published_at: str = ""
    installed_release_url: str = ""
    installed_release_commitish: str = ""
    manager_managed: bool = False
    manager_root_id: str = ""
    manager_root: str = ""
    manager_version: str = ""
    data_as_of: str = ""
    truth_as_of: str = ""
    freshness_state: str = ""
    stale_reason: str = ""
    refresh_action: str = ""
    freshness_source: str = ""
    target_manager_port: int = DEFAULT_NODE_PORT
    manager_health_status: str = ""
    manager_health_mode: str = ""
    manager_health_checked_at: str = ""
    manager_health_runtime_port: int | None = None
    manager_manifest_runtime_port: int | None = None
    legacy_runtime_port: int | None = None
    legacy_runtime_port_source: str = ""
    legacy_runtime_port_label: str = ""


class ProjectCreateRequest(BaseModel):
    project_id: str
    display_name: str
    parent_project_id: str | None = None
    service_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class ProjectPatchRequest(BaseModel):
    project_id: str | None = None
    display_name: str | None = None
    parent_project_id: str | None = None
    service_ids: list[str] | None = None
    tags: list[str] | None = None
    notes: str | None = None


class ProjectEnvironmentCreateRequest(BaseModel):
    environment_id: str
    display_name: str
    kind: ProjectEnvironmentKind = "custom"
    deployments: list[ProjectDeploymentRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class ProjectEnvironmentPatchRequest(BaseModel):
    environment_id: str | None = None
    display_name: str | None = None
    kind: ProjectEnvironmentKind | None = None
    deployments: list[ProjectDeploymentRef] | None = None
    tags: list[str] | None = None
    notes: str | None = None


class EnvironmentRuntimeSnapshotRequest(BaseModel):
    runtime_passwords: dict[str, str] = Field(default_factory=dict)


class ApiFlowCreateRequest(BaseModel):
    flow_id: str
    service_id: str | None = None
    display_name: str
    target_kind: ApiFlowTargetKind = "service"
    target_name: str = ""
    base_url: str = ""
    execution_mode: FlowExecutionMode = "http"
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    steps: list[ApiFlowStep] = Field(default_factory=list)


class ApiFlowPatchRequest(BaseModel):
    flow_id: str | None = None
    service_id: str | None = None
    display_name: str | None = None
    target_kind: ApiFlowTargetKind | None = None
    target_name: str | None = None
    base_url: str | None = None
    execution_mode: FlowExecutionMode | None = None
    enabled: bool | None = None
    tags: list[str] | None = None
    notes: str | None = None
    steps: list[ApiFlowStep] | None = None


class ApiFlowRunRequest(BaseModel):
    pass


class ServerCreateRequest(BaseModel):
    server_id: str
    company_id: str = ""
    name: str
    connection_type: ConnectionType
    host: str
    username: str
    port: int = 22
    deployment_mode: DeploymentMode = "native_agent"
    vpn_required: bool = False
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    local_password: str | None = None


class ServerPatchRequest(BaseModel):
    company_id: str | None = None
    name: str | None = None
    host: str | None = None
    username: str | None = None
    port: int | None = None
    deployment_mode: DeploymentMode | None = None
    vpn_required: bool | None = None
    tags: list[str] | None = None
    notes: str | None = None
    local_password: str | None = None


class SecretPathQuery(BaseModel):
    service_id: str
