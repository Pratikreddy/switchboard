import type {
  ActionLock,
  ApiFlowCreateRequest,
  ApiFlowManifest,
  ApiFlowPatchRequest,
  ApiFlowRunRecord,
  CompanyCreateRequest,
  CompanyPatchRequest,
  EnvironmentLabView,
  EnvironmentRuntimeSnapshot,
  EnvironmentRuntimeSnapshotRequest,
  OperatorCommand,
  PortExposureFinding,
  ProcessFinding,
  ProjectEnvironmentCreateRequest,
  ProjectEnvironmentPatchRequest,
  ProjectEnvironmentView,
  ProjectManifest,
  ProjectPullSummary,
  ProjectCreateRequest,
  ProjectPatchRequest,
  ServerCreateRequest,
  ServerPatchRequest,
  TaskLedgerEntry,
  ApiResult,
  ApiError,
  CollectOptions,
  CreateServiceRequest,
  DiscoveryTreeRequest,
  DiscoveryTreeResult,
  DownloadRequest,
  GitHubBackupRequest,
  GitHubBackupResult,
  GitPushRequest,
  GitPullRequest,
  GitPullResult,
  HealthResponse,
  NodeSyncRequest,
  NodeSyncResult,
  PullBundleRecord,
  PullBundlePreflight,
  PullBundleRequest,
  RepoStateResult,
  RepoActionRequest,
  RepoPolicy,
  RuntimeActionRequest,
  RuntimeCheckResult,
  RuntimeConfig,
  RunRecord,
  SafetyCheckResult,
  ScanRootRequest,
  ScanRootResult,
  SecretPathsResult,
  Service,
  ServerRecord,
  ScopeEntry,
  ManagedDocConfig,
  NodeActionResult,
  NodeReleaseCheck,
  NodeViewerEntry,
  Workspace,
  WorkspaceLatest,
} from '../types/switchboard'
import { isApiError } from '../types/switchboard'

const BASE = '/api'

function normalizeFreshness(result: any) {
  return {
    data_as_of: result?.data_as_of ?? result?.freshness?.data_as_of ?? '',
    truth_as_of: result?.truth_as_of ?? result?.freshness?.truth_as_of ?? '',
    freshness_state: result?.freshness_state ?? result?.freshness?.freshness_state ?? '',
    stale_reason: result?.stale_reason ?? result?.freshness?.stale_reason ?? '',
    refresh_action: result?.refresh_action ?? result?.freshness?.refresh_action ?? '',
    freshness_source: result?.freshness_source ?? result?.freshness?.freshness_source ?? '',
  }
}

function favoriteRank(value: string | number | undefined): number {
  if (value === 1 || value === 'primary') return 1
  if (value === 2 || value === 'secondary') return 2
  return 99
}

function normalizeService(service: any) {
  return {
    ...normalizeFreshness(service),
    service_id: service.service_id,
    workspace_id: service.workspace_id,
    display_name: service.display_name,
    kind: service.kind ?? 'service',
    execution_mode: service.execution_mode ?? 'networked',
    tags: service.tags ?? [],
    favorite_tier: favoriteRank(service.favorite_tier),
    locations: (service.locations ?? []).map((location: any) => ({
      location_id: location.location_id,
      server_id: location.server_id,
      access_mode: location.access_mode ?? 'ssh',
      root: location.root ?? location.path ?? '',
      role: location.role ?? 'primary',
      is_primary: Boolean(location.is_primary),
      path_aliases: location.path_aliases ?? [],
      runtime: normalizeRuntimeConfig(location.runtime),
    })),
    repo_paths: service.repo_paths ?? [],
    docs_paths: service.docs_paths ?? [],
    log_paths: service.log_paths ?? [],
    allowed_git_pull_paths: service.allowed_git_pull_paths ?? [],
    exclude_globs: service.exclude_globs ?? [],
    scope_entries: (service.scope_entries ?? []).map(normalizeScopeEntry),
    managed_docs: (service.managed_docs ?? []).map(normalizeManagedDoc),
    repo_policies: (service.repo_policies ?? []).map(normalizeRepoPolicy),
    notes: service.notes ?? '',
    path_aliases: service.path_aliases ?? [],
    runtime_checks: (service.runtime_checks ?? []).map(normalizeRuntimeCheck),
    node_sync: (service.node_sync ?? []).map(normalizeNodeSync),
    task_ledger: (service.task_ledger ?? []).map(normalizeTaskLedgerEntry),
    node_viewer: (service.node_viewer ?? []).map(normalizeNodeViewer),
    saved_scope_generated_at: service.saved_scope_generated_at ?? '',
  } satisfies Service
}

function normalizeRuntimeConfig(runtime: any): RuntimeConfig {
  return {
    expected_ports: Array.isArray(runtime?.expected_ports)
      ? runtime.expected_ports
          .map((port: unknown) => Number(port))
          .filter((port: number) => Number.isFinite(port))
      : [],
    healthcheck_command: runtime?.healthcheck_command ?? '',
    run_command_hint: runtime?.run_command_hint ?? '',
    monitoring_mode: runtime?.monitoring_mode ?? 'manual',
    notes: runtime?.notes ?? '',
  }
}

function normalizeScopeEntry(entry: any): ScopeEntry {
  return {
    entry_id: entry.entry_id,
    kind: entry.kind,
    path: entry.path,
    path_type: entry.path_type,
    source: entry.source ?? 'user_added',
    enabled: entry.enabled ?? true,
  }
}

function normalizeRepoPolicy(policy: any): RepoPolicy {
  return {
    repo_path: policy.repo_path,
    push_mode: policy.push_mode ?? 'blocked',
    safety_profile: policy.safety_profile ?? 'generic_python',
    allowed_branches: policy.allowed_branches ?? [],
    allowed_remotes: policy.allowed_remotes ?? [],
  }
}

function normalizeManagedDoc(entry: any): ManagedDocConfig {
  return {
    doc_id: entry.doc_id,
    path: entry.path ?? '',
    enabled: entry.enabled ?? false,
    generated_from: entry.generated_from ?? 'switchboard/local/tasks-completed.md',
    last_generated_at: entry.last_generated_at ?? null,
  }
}

function normalizeDocIndex(docIndex: any) {
  return {
    generated: docIndex?.generated ?? '',
    service_id: docIndex?.service_id,
    project_root: docIndex?.project_root,
    docs: Array.isArray(docIndex?.docs)
      ? docIndex.docs.map((entry: any) => ({
          doc_id: entry.doc_id,
          label: entry.label,
          path: entry.path ?? '',
          enabled: entry.enabled ?? false,
          generated_at: entry.generated_at ?? null,
          generated_from: entry.generated_from ?? 'switchboard/local/tasks-completed.md',
          contributor_timestamps: entry.contributor_timestamps ?? [],
        }))
      : [],
  }
}

function normalizeWorkspace(workspace: any, services: any[] = []): Workspace {
  const workspaceServiceIds = Array.isArray(workspace.services) ? workspace.services : []
  const workspaceServerIds = workspace.server_ids ?? workspace.servers ?? []
  return {
    workspace_id: workspace.workspace_id,
    company_id: workspace.company_id ?? workspace.workspace_id,
    display_name: workspace.display_name ?? workspace.name ?? workspace.workspace_id,
    services: services.map(normalizeService),
    server_ids: workspaceServerIds,
    tags: workspace.tags ?? [],
    notes: workspace.notes ?? '',
    service_count:
      typeof workspace.service_count === 'number'
        ? workspace.service_count
        : services.length > 0
          ? services.length
          : workspaceServiceIds.length,
    server_count:
      typeof workspace.server_count === 'number'
        ? workspace.server_count
        : workspaceServerIds.length,
  }
}

function normalizeRepoSummary(repo: any, allowedPaths: string[]) {
  const lastCommit = typeof repo.last_commit === 'string' ? repo.last_commit.split('\t')[0] : ''
  return {
    path: repo.repo_path ?? repo.path ?? '',
    server_id: repo.server_id,
    branch: repo.branch ?? '',
    commit: repo.commit ?? lastCommit ?? '',
    dirty: Boolean(repo.dirty),
    status: repo.status ?? 'unverified',
    is_allowlisted: allowedPaths.includes(repo.repo_path ?? repo.path ?? ''),
    remotes: repo.remotes ?? [],
    push_mode: repo.push_mode,
    safety_profile: repo.safety_profile,
    push_eligible: repo.push_eligible,
  }
}

function normalizeRepoState(repo: any): RepoStateResult {
  const normalized = normalizeRepoSummary(repo, [])
  return {
    ...normalized,
    repo_path: repo.repo_path ?? repo.path ?? '',
  }
}

function normalizePortInfo(port: any) {
  return {
    port: Number(port.port ?? 0),
    protocol: port.protocol ?? 'tcp',
    process: port.process ?? '',
    pid: typeof port.pid === 'number' ? port.pid : port.pid ? Number(port.pid) : undefined,
    state: port.state,
  }
}

function normalizeRuntimeCheck(result: any): RuntimeCheckResult {
  return {
    ...normalizeFreshness(result),
    service_id: result.service_id,
    location_id: result.location_id,
    server_id: result.server_id,
    root: result.root ?? '',
    status: result.status ?? 'unverified',
    checked_at: result.checked_at ?? '',
    execution_mode: result.execution_mode ?? 'networked',
    configured_ports: Array.isArray(result.configured_ports)
      ? result.configured_ports.map((port: unknown) => Number(port)).filter((port: number) => Number.isFinite(port))
      : [],
    detected_ports: (result.detected_ports ?? []).map(normalizePortInfo),
    missing_ports: Array.isArray(result.missing_ports)
      ? result.missing_ports.map((port: unknown) => Number(port)).filter((port: number) => Number.isFinite(port))
      : [],
    healthcheck_command: result.healthcheck_command ?? '',
    healthcheck_status: result.healthcheck_status ?? 'skipped',
    healthcheck_output: result.healthcheck_output ?? '',
    detected_process_command: result.detected_process_command ?? '',
    run_command_hint: result.run_command_hint ?? '',
    monitoring_mode: result.monitoring_mode ?? 'manual',
    notes: result.notes ?? '',
    node_present: Boolean(result.node_present),
    source: result.source,
    firewall_status: result.firewall_status ?? 'unverified',
    unexpected_ports: Array.isArray(result.unexpected_ports) ? result.unexpected_ports.map((port: unknown) => Number(port)).filter((port: number) => Number.isFinite(port)) : [],
    process_findings: (result.process_findings ?? []).map(normalizeProcessFinding),
    exposed_ports: (result.exposed_ports ?? []).map(normalizePortExposureFinding),
    operator_commands: (result.operator_commands ?? []).map(normalizeOperatorCommand),
  }
}

function normalizeProcessFinding(result: any): ProcessFinding {
  return {
    port: typeof result?.port === 'number' ? result.port : result?.port ? Number(result.port) : undefined,
    bind_address: result?.bind_address ?? '',
    process_name: result?.process_name ?? '',
    pid: typeof result?.pid === 'number' ? result.pid : result?.pid ? Number(result.pid) : undefined,
    state: result?.state ?? '',
    raw: result?.raw ?? '',
    owner_service_id: result?.owner_service_id ?? '',
    owner_display_name: result?.owner_display_name ?? '',
    owner_location_id: result?.owner_location_id ?? '',
    owner_root: result?.owner_root ?? '',
  }
}

function normalizePortExposureFinding(result: any): PortExposureFinding {
  return {
    host: result?.host ?? '',
    port: Number(result?.port ?? 0),
    bind_address: result?.bind_address ?? '',
    process_name: result?.process_name ?? '',
    expected: Boolean(result?.expected),
    exposure: result?.exposure ?? 'unknown',
    notes: result?.notes ?? '',
  }
}

function normalizeOperatorCommand(result: any): OperatorCommand {
  return {
    category: result?.category ?? 'inspect_only',
    label: result?.label ?? '',
    command: result?.command ?? '',
    notes: result?.notes ?? '',
  }
}

function normalizeNodeReleaseCheck(result: any): NodeReleaseCheck {
  return {
    status: result?.status ?? 'unverified',
    current_version: result?.current_version ?? '',
    latest_version: result?.latest_version ?? '',
    update_available: Boolean(result?.update_available),
    published_at: result?.published_at ?? '',
    release_url: result?.release_url ?? '',
    asset_url: result?.asset_url ?? '',
    notes: result?.notes ?? '',
    message: result?.message ?? '',
    exact_match_known: Boolean(result?.exact_match_known),
    exact_match: Boolean(result?.exact_match),
    current_release_version: result?.current_release_version ?? '',
    current_release_asset_id: result?.current_release_asset_id ?? '',
    current_release_asset_name: result?.current_release_asset_name ?? '',
    current_release_published_at: result?.current_release_published_at ?? '',
    current_release_url: result?.current_release_url ?? '',
    current_release_commitish: result?.current_release_commitish ?? '',
    latest_release_asset_id: result?.latest_release_asset_id ?? '',
    latest_release_asset_name: result?.latest_release_asset_name ?? '',
    latest_release_asset_updated_at: result?.latest_release_asset_updated_at ?? '',
    latest_release_commitish: result?.latest_release_commitish ?? '',
  }
}

function normalizeEnvironmentRuntimeSnapshot(result: any): EnvironmentRuntimeSnapshot {
  return {
    environment_id: result?.environment_id ?? '',
    captured_at: result?.captured_at ?? '',
    locations: (result?.locations ?? []).map((location: any) => ({
      service_id: location?.service_id ?? '',
      service_name: location?.service_name ?? '',
      execution_mode: location?.execution_mode ?? 'networked',
      location_id: location?.location_id ?? '',
      server_id: location?.server_id ?? '',
      root: location?.root ?? '',
      host: location?.host ?? '',
      firewall_status: location?.firewall_status ?? 'unverified',
      node_status: location?.node_status ?? 'missing',
      expected_ports: location?.expected_ports ?? [],
      open_ports: location?.open_ports ?? [],
      unexpected_ports: location?.unexpected_ports ?? [],
      exposed_ports: (location?.exposed_ports ?? []).map(normalizePortExposureFinding),
      process_findings: (location?.process_findings ?? []).map(normalizeProcessFinding),
      operator_commands: (location?.operator_commands ?? []).map(normalizeOperatorCommand),
      runtime_hint: location?.runtime_hint ?? '',
      healthcheck_command: location?.healthcheck_command ?? '',
      healthcheck_status: location?.healthcheck_status ?? 'skipped',
      healthcheck_output: location?.healthcheck_output ?? '',
    })),
    open_ports: result?.open_ports ?? [],
    expected_ports: result?.expected_ports ?? [],
    unexpected_ports: result?.unexpected_ports ?? [],
    exposed_ports: (result?.exposed_ports ?? []).map(normalizePortExposureFinding),
    firewall_status: result?.firewall_status ?? 'unverified',
    process_findings: (result?.process_findings ?? []).map(normalizeProcessFinding),
    node_findings: result?.node_findings ?? [],
    operator_commands: (result?.operator_commands ?? []).map(normalizeOperatorCommand),
  }
}

function normalizeApiFlowStep(step: any) {
  return {
    step_id: step?.step_id ?? '',
    order: step?.order ?? 0,
    display_name: step?.display_name ?? '',
    method: step?.method ?? 'GET',
    path: step?.path ?? '',
    query: step?.query ?? {},
    headers: step?.headers ?? {},
    body: step?.body ?? '',
    expected_status: step?.expected_status ?? 200,
    continue_on_failure: step?.continue_on_failure ?? false,
    timeout_seconds: step?.timeout_seconds ?? 15,
    notes: step?.notes ?? '',
    captures: (step?.captures ?? []).map((capture: any) => ({
      variable_name: capture?.variable_name ?? '',
      source: capture?.source ?? 'json',
      selector: capture?.selector ?? '',
    })),
  }
}

function normalizeApiFlow(result: any): ApiFlowManifest {
  return {
    flow_id: result?.flow_id ?? '',
    environment_id: result?.environment_id ?? '',
    service_id: result?.service_id ?? '',
    display_name: result?.display_name ?? '',
    target_kind: result?.target_kind ?? 'service',
    target_name: result?.target_name ?? '',
    base_url: result?.base_url ?? '',
    execution_mode: result?.execution_mode ?? 'http',
    enabled: result?.enabled ?? true,
    tags: result?.tags ?? [],
    notes: result?.notes ?? '',
    steps: (result?.steps ?? []).map(normalizeApiFlowStep),
  }
}

function normalizeApiFlowRun(result: any): ApiFlowRunRecord {
  return {
    run_id: result?.run_id ?? '',
    flow_id: result?.flow_id ?? '',
    environment_id: result?.environment_id ?? '',
    started_at: result?.started_at ?? '',
    finished_at: result?.finished_at ?? '',
    status: result?.status ?? 'failed',
    summary: result?.summary ?? '',
    step_results: (result?.step_results ?? []).map((step: any) => ({
      step_id: step?.step_id ?? '',
      status: step?.status ?? 'failed',
      resolved_url: step?.resolved_url ?? '',
      duration_ms: step?.duration_ms ?? 0,
      request_preview: step?.request_preview ?? { method: '', url: '', headers: {}, body_preview: '' },
      response_status: step?.response_status ?? 0,
      response_headers: step?.response_headers ?? {},
      response_body_preview: step?.response_body_preview ?? '',
      extracted_variables: step?.extracted_variables ?? {},
      generated_curl: step?.generated_curl ?? '',
      error: step?.error ?? '',
    })),
  }
}

function normalizeNodeSync(result: any): NodeSyncResult {
  return {
    ...normalizeFreshness(result),
    service_id: result.service_id,
    location_id: result.location_id,
    direction: result.direction ?? 'from_node',
    timestamp: result.timestamp ?? '',
    status: result.status ?? 'unverified',
    source: result.source ?? '',
    target: result.target ?? '',
    include_scope_snapshot: result.include_scope_snapshot ?? true,
    include_runtime_config: result.include_runtime_config ?? true,
    managed_docs: (result.managed_docs ?? []).map(normalizeManagedDoc),
    doc_index: result.doc_index ? normalizeDocIndex(result.doc_index) : undefined,
    server_id: result.server_id ?? '',
    message: result.message ?? '',
    scope_snapshot_generated_at: result.scope_snapshot_generated_at ?? '',
    skipped: Boolean(result.skipped),
  }
}

function normalizeNodeViewer(result: any): NodeViewerEntry {
  return {
    ...normalizeFreshness(result),
    service_id: result.service_id ?? '',
    location_id: result.location_id ?? '',
    server_id: result.server_id ?? '',
    root: result.root ?? '',
    connection_status: result.connection_status ?? 'ok',
    last_inspected_at: result.last_inspected_at ?? '',
    node_present: Boolean(result.node_present),
    bootstrap_ready: Boolean(result.bootstrap_ready),
    runtime_ready: Boolean(result.runtime_ready),
    installed_version: result.installed_version ?? '',
    bootstrap_version: result.bootstrap_version ?? '',
    manifest_updated_at: result.manifest_updated_at ?? '',
    runtime_status: result.runtime_status ?? 'missing',
    runtime_pid: typeof result.runtime_pid === 'number' ? result.runtime_pid : undefined,
    runtime_port: result.runtime_port ?? 8020,
    runtime_port_source: result.runtime_port_source ?? '',
    target_manager_port: result.target_manager_port ?? 8020,
    manager_health_status: result.manager_health_status ?? '',
    manager_health_mode: result.manager_health_mode ?? '',
    manager_health_checked_at: result.manager_health_checked_at ?? '',
    manager_health_runtime_port: typeof result.manager_health_runtime_port === 'number' ? result.manager_health_runtime_port : undefined,
    manager_manifest_runtime_port: typeof result.manager_manifest_runtime_port === 'number' ? result.manager_manifest_runtime_port : undefined,
    legacy_runtime_port: typeof result.legacy_runtime_port === 'number' ? result.legacy_runtime_port : undefined,
    legacy_runtime_port_source: result.legacy_runtime_port_source ?? '',
    legacy_runtime_port_label: result.legacy_runtime_port_label ?? '',
    needs_install: Boolean(result.needs_install),
    needs_upgrade: Boolean(result.needs_upgrade),
    needs_bootstrap: Boolean(result.needs_bootstrap),
    attention_reason: result.attention_reason ?? '',
    manifest_path: result.manifest_path ?? '',
    runtime_dir: result.runtime_dir ?? '',
    log_file: result.log_file ?? '',
    last_error: result.last_error ?? '',
    installed_release_version: result.installed_release_version ?? '',
    installed_release_asset_id: result.installed_release_asset_id ?? '',
    installed_release_asset_name: result.installed_release_asset_name ?? '',
    installed_release_published_at: result.installed_release_published_at ?? '',
    installed_release_url: result.installed_release_url ?? '',
    installed_release_commitish: result.installed_release_commitish ?? '',
    manager_managed: Boolean(result.manager_managed),
    manager_root_id: result.manager_root_id ?? '',
    manager_root: result.manager_root ?? '',
    manager_version: result.manager_version ?? '',
  }
}

function normalizeFile(file: any) {
  return {
    path: file.path,
    name: file.name,
    size_bytes: file.size_bytes ?? file.size ?? 0,
    modified: file.modified ?? file.modified_at ?? '',
    kind: file.kind,
  }
}

function normalizeWorkspaceLatest(raw: any): WorkspaceLatest {
  const services = (raw.services ?? []).map((entry: any) => ({
    ...normalizeFreshness(entry),
    service_id: entry.service_id,
    status: entry.status ?? 'unverified',
    ports: (entry.ports ?? []).map(normalizePortInfo),
    firewall_status: entry.firewall_status ?? '',
    firewall_active: Boolean(entry.firewall_active),
    repo_summaries: (raw.repo_inventory ?? [])
      .filter((repo: any) => repo.service_id === entry.service_id)
      .map((repo: any) => normalizeRepoSummary(repo, [])),
    docs_count: entry.docs_count ?? entry.doc_count ?? 0,
    logs_count: entry.logs_count ?? entry.log_count ?? 0,
    docs_files: (raw.docs_index ?? [])
      .filter((file: any) => file.service_id === entry.service_id)
      .map((file: any) => normalizeFile({ ...file, kind: 'doc' })),
    logs_files: (raw.logs_index ?? [])
      .filter((file: any) => file.service_id === entry.service_id)
      .map((file: any) => normalizeFile({ ...file, kind: 'log' })),
    secret_path_count: entry.secret_path_count ?? 0,
    collected_at: raw.generated ?? '',
    runtime_checks: (entry.runtime_checks ?? []).map(normalizeRuntimeCheck),
    node_sync: (entry.node_sync ?? []).map(normalizeNodeSync),
  }))

  return {
    freshness: normalizeFreshness(raw),
    workspace: normalizeWorkspace(raw.workspace, []),
    servers: (raw.servers ?? []).map((server: any) => ({
      server_id: server.server_id,
      host: server.host,
      type: server.connection_type ?? 'unknown',
      role: server.name ?? server.hostname ?? '',
      port: server.port ?? 22,
      status: server.status ?? 'unverified',
    })),
    services,
    summary: {
      ...normalizeFreshness(raw.summary ?? raw),
      run_id: raw.generated ?? 'unverified',
      workspace_id: raw.workspace?.workspace_id ?? '',
      timestamp: raw.generated ?? '',
      status: raw.summary?.status ?? 'unverified',
      triggered_by: 'system',
      server_count: raw.summary?.server_count ?? raw.servers?.length ?? 0,
      service_count: raw.summary?.service_count ?? raw.services?.length ?? 0,
      node_sync_count: raw.summary?.node_sync_count ?? 0,
      node_sync_blocked_count: raw.summary?.node_sync_blocked_count ?? 0,
    },
    repo_inventory: (raw.repo_inventory ?? []).map((repo: any) => normalizeRepoSummary(repo, [])),
    docs_index: (raw.docs_index ?? []).map((file: any) => normalizeFile({ ...file, kind: 'doc' })),
    logs_index: (raw.logs_index ?? []).map((file: any) => normalizeFile({ ...file, kind: 'log' })),
    node_sync_results: (raw.node_sync_results ?? []).map(normalizeNodeSync),
  }
}

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const detail = body?.detail
      const message =
        typeof detail === 'string'
          ? detail
          : typeof detail?.message === 'string'
            ? detail.message
            : `HTTP ${res.status}`
      const status =
        typeof detail?.status === 'string'
          ? detail.status
          : res.status === 404
            ? 'path_missing'
            : 'unreachable'
      return {
        status,
        message,
        code: res.status,
      } as ApiError
    }
    return (await res.json()) as T
  } catch {
    return { status: 'unreachable', message: 'Backend not reachable' } as ApiError
  }
}

type WorkspacesResponse = { workspaces: unknown[] }
type WorkspaceResponse = { workspace: unknown; services: unknown[] }
type WorkspaceRunsResponse = { workspace_id: string; runs: unknown[] }
type ServiceResponse = { service: unknown }
type ServersResponse = { servers: unknown[] }
type ServiceScopeResponse = { service_id: string; scope_entries: unknown[]; repo_policies: unknown[] }
type PullBundlesResponse = { service_id: string; bundles: unknown[] }

function hasObjectProperty<K extends string>(
  value: unknown,
  key: K,
): value is Record<K, unknown> {
  return typeof value === 'object' && value !== null && key in value
}

export const getHealth = (): Promise<ApiResult<HealthResponse>> =>
  apiFetch<HealthResponse>('/health')

export const listServers = (): Promise<ApiResult<ServerRecord[]>> =>
  apiFetch<ServersResponse>('/servers').then((res) => {
    if (isApiError(res)) return res
    if (!hasObjectProperty(res, 'servers') || !Array.isArray(res.servers)) {
      return { status: 'unverified', message: 'Invalid servers response' }
    }
    return res.servers.map((server: any) => ({
      server_id: server.server_id,
      company_id: server.company_id ?? '',
      name: server.name,
      connection_type: server.connection_type,
      host: server.host,
      username: server.username,
      port: server.port ?? 22,
      deployment_mode: server.deployment_mode ?? 'native_agent',
      vpn_required: Boolean(server.vpn_required),
      tags: server.tags ?? [],
      notes: server.notes ?? '',
    }))
  })

export const listWorkspaces = (): Promise<ApiResult<Workspace[]>> =>
  apiFetch<WorkspacesResponse>('/workspaces').then((res) => {
    if (isApiError(res)) return res
    if (!hasObjectProperty(res, 'workspaces') || !Array.isArray(res.workspaces)) {
      return { status: 'unverified', message: 'Invalid workspaces response' }
    }
    return res.workspaces.map((workspace) => normalizeWorkspace(workspace))
  })

export const listCompanies = (): Promise<ApiResult<Workspace[]>> =>
  listWorkspaces()

export const getWorkspace = (id: string): Promise<ApiResult<Workspace>> =>
  apiFetch<WorkspaceResponse>(`/workspaces/${id}`).then((res) => {
    if (isApiError(res)) return res
    if (
      !hasObjectProperty(res, 'workspace') ||
      !hasObjectProperty(res, 'services') ||
      !Array.isArray(res.services)
    ) {
      return { status: 'unverified', message: 'Invalid workspace response' }
    }
    return normalizeWorkspace(res.workspace, res.services)
  })

export const getWorkspaceLatest = (id: string): Promise<ApiResult<WorkspaceLatest>> =>
  apiFetch<any>(`/workspaces/${id}/latest`).then((res) =>
    isApiError(res) ? res : normalizeWorkspaceLatest(res),
  )

export const getWorkspaceRuns = (id: string): Promise<ApiResult<RunRecord[]>> =>
  apiFetch<WorkspaceRunsResponse>(`/workspaces/${id}/runs`).then((res) => {
    if (isApiError(res)) return res
    if (!hasObjectProperty(res, 'runs') || !Array.isArray(res.runs)) {
      return { status: 'unverified', message: 'Invalid workspace runs response' }
    }
    return res.runs.map((run: any) => ({
      run_id: run.generated ?? run.run_id ?? '',
      workspace_id: run.workspace_id ?? id,
      timestamp: run.generated ?? run.timestamp ?? '',
      status: run.status ?? 'unverified',
      triggered_by: run.triggered_by ?? 'system',
    }))
  })

export const getService = (id: string): Promise<ApiResult<Service>> =>
  apiFetch<ServiceResponse>(`/services/${id}`).then((res) => {
    if (isApiError(res)) return res
    if (!hasObjectProperty(res, 'service')) {
      return { status: 'unverified', message: 'Invalid service response' }
    }
    return normalizeService(res.service)
  })

export const getServiceScope = (
  id: string,
): Promise<ApiResult<{ service_id: string; scope_entries: ScopeEntry[]; repo_policies: RepoPolicy[] }>> =>
  apiFetch<ServiceScopeResponse>(`/services/${id}/scope`).then((res) => {
    if (isApiError(res)) return res
    return {
      service_id: String((res as any).service_id ?? id),
      scope_entries: ((res as any).scope_entries ?? []).map(normalizeScopeEntry),
      repo_policies: ((res as any).repo_policies ?? []).map(normalizeRepoPolicy),
    }
  })

export const scanRoot = (req: ScanRootRequest): Promise<ApiResult<ScanRootResult>> =>
  apiFetch<ScanRootResult>('/discovery/scan-root', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const browseTree = (
  req: DiscoveryTreeRequest,
): Promise<ApiResult<DiscoveryTreeResult>> =>
  apiFetch<DiscoveryTreeResult>('/discovery/tree', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const triggerCollect = (
  id: string,
  opts: CollectOptions = {},
): Promise<ApiResult<WorkspaceLatest>> =>
  apiFetch<any>(`/workspaces/${id}/collect`, {
    method: 'POST',
    body: JSON.stringify(opts),
  }).then((res) => (isApiError(res) ? res : normalizeWorkspaceLatest(res)))

export const addService = (
  workspaceId: string,
  data: CreateServiceRequest,
): Promise<ApiResult<Service>> =>
  apiFetch<ServiceResponse>(`/workspaces/${workspaceId}/services`, {
    method: 'POST',
    body: JSON.stringify(data),
  }).then((res) => {
    if (isApiError(res)) return res
    if (!hasObjectProperty(res, 'service')) {
      return { status: 'unverified', message: 'Invalid service create response' }
    }
    return normalizeService(res.service)
  })

export const updateService = (
  id: string,
  patch: Partial<Service>,
): Promise<ApiResult<Service>> =>
  apiFetch<ServiceResponse>(`/services/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  }).then((res) => {
    if (isApiError(res)) return res
    if (!hasObjectProperty(res, 'service')) {
      return { status: 'unverified', message: 'Invalid service update response' }
    }
    return normalizeService(res.service)
  })

export const deleteService = (
  id: string,
): Promise<ApiResult<{ deleted: boolean; service_id: string; workspace_id: string; generated: string }>> =>
  apiFetch<{ deleted: boolean; service_id: string; workspace_id: string; generated: string }>(`/services/${id}`, {
    method: 'DELETE',
  })

export const requestDownload = (
  id: string,
  req: DownloadRequest,
): Promise<ApiResult<{ path: string; files: string[] }>> =>
  apiFetch<{ path: string; files: string[] }>(`/services/${id}/downloads`, {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const triggerGitPull = (
  id: string,
  req: GitPullRequest,
): Promise<ApiResult<GitPullResult>> =>
  apiFetch<GitPullResult>(`/services/${id}/actions/git-pull`, {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const getGitStatus = (
  id: string,
  req: RepoActionRequest,
): Promise<ApiResult<RepoStateResult>> =>
  apiFetch<any>(`/services/${id}/actions/git-status`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => (isApiError(res) ? res : normalizeRepoState(res)))

export const runSafetyCheck = (
  id: string,
  req: RepoActionRequest,
): Promise<ApiResult<SafetyCheckResult>> =>
  apiFetch<any>(`/services/${id}/actions/safety-check`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => {
    if (isApiError(res)) return res
    return {
      ...res,
      repo_state: normalizeRepoState(res.repo_state ?? {}),
    } satisfies SafetyCheckResult
  })

export const triggerGitPush = (
  id: string,
  req: GitPushRequest,
): Promise<ApiResult<GitPullResult>> =>
  apiFetch<GitPullResult>(`/services/${id}/actions/git-push`, {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const getGithubBackupReadiness = (
  workspaceId?: string,
): Promise<ApiResult<GitHubBackupResult>> => {
  const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ''
  return apiFetch<GitHubBackupResult>(`/github-backup/readiness${query}`)
}

export const runGithubBackupDryRun = (
  req: GitHubBackupRequest,
): Promise<ApiResult<GitHubBackupResult>> =>
  apiFetch<GitHubBackupResult>('/github-backup/dry-run', {
    method: 'POST',
    body: JSON.stringify({ ...req, dry_run: true }),
  })

export const runGithubBackup = (
  req: GitHubBackupRequest,
): Promise<ApiResult<GitHubBackupResult>> =>
  apiFetch<GitHubBackupResult>('/github-backup/run', {
    method: 'POST',
    body: JSON.stringify({ ...req, dry_run: false }),
  })

// Returns count only — never expose actual paths in the dashboard
export const getSecretPathCount = (
  id: string,
): Promise<ApiResult<SecretPathsResult>> =>
  apiFetch<SecretPathsResult>(`/services/${id}/secret-paths`)

export const runRuntimeCheck = (
  id: string,
  req: RuntimeActionRequest,
): Promise<ApiResult<RuntimeCheckResult>> =>
  apiFetch<RuntimeCheckResult>(`/services/${id}/actions/runtime-check`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => (isApiError(res) ? res : normalizeRuntimeCheck(res)))

export const syncFromNode = (
  id: string,
  req: NodeSyncRequest,
): Promise<ApiResult<{ service: Service; sync: NodeSyncResult }>> =>
  apiFetch<any>(`/services/${id}/actions/sync-from-node`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => {
    if (isApiError(res)) return res
    return {
      service: normalizeService(res.service),
      sync: normalizeNodeSync(res.sync),
    }
  })

export const syncToNode = (
  id: string,
  req: NodeSyncRequest,
): Promise<ApiResult<{ sync: NodeSyncResult; node_manifest_path?: string }>> =>
  apiFetch<any>(`/services/${id}/actions/sync-to-node`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => {
    if (isApiError(res)) return res
    return {
      sync: normalizeNodeSync(res.sync),
      node_manifest_path: res.node_manifest_path,
    }
  })

export const getNodeViewer = (
  id: string,
): Promise<ApiResult<{ locations: NodeViewerEntry[] }>> =>
  apiFetch<any>(`/services/${id}/node-viewer`).then((res) => {
    if (isApiError(res)) return res
    return { locations: (res.locations ?? []).map(normalizeNodeViewer) }
  })

export const inspectNode = (
  id: string,
  locationId?: string,
): Promise<ApiResult<NodeActionResult>> =>
  apiFetch<any>(`/services/${id}/actions/node-inspect`, {
    method: 'POST',
    body: JSON.stringify({ location_id: locationId }),
  }).then((res) => {
    if (isApiError(res) && !(res as any).node) return res
    return {
      status: res.status,
      node: normalizeNodeViewer(res.node),
      before: res.before ? normalizeNodeViewer(res.before) : undefined,
      after: res.after ? normalizeNodeViewer(res.after) : undefined,
      message: res.message,
    }
  })

export const deployNode = (
  id: string,
  locationId?: string,
): Promise<ApiResult<NodeActionResult>> =>
  apiFetch<any>(`/services/${id}/actions/node-deploy`, {
    method: 'POST',
    body: JSON.stringify({ location_id: locationId }),
  }).then((res) => {
    if (isApiError(res)) return res
    return {
      status: res.status,
      node: normalizeNodeViewer(res.node),
      before: res.before ? normalizeNodeViewer(res.before) : undefined,
      after: res.after ? normalizeNodeViewer(res.after) : undefined,
      message: res.message,
      release: res.release ? normalizeNodeReleaseCheck(res.release) : undefined,
    }
  })

export const upgradeNode = (
  id: string,
  locationId?: string,
): Promise<ApiResult<NodeActionResult>> =>
  apiFetch<any>(`/services/${id}/actions/node-upgrade`, {
    method: 'POST',
    body: JSON.stringify({ location_id: locationId }),
  }).then((res) => {
    if (isApiError(res)) return res
    return {
      status: res.status,
      node: normalizeNodeViewer(res.node),
      before: res.before ? normalizeNodeViewer(res.before) : undefined,
      after: res.after ? normalizeNodeViewer(res.after) : undefined,
      message: res.message,
      release: res.release ? normalizeNodeReleaseCheck(res.release) : undefined,
    }
  })

export const restartNode = (
  id: string,
  locationId?: string,
): Promise<ApiResult<NodeActionResult>> =>
  apiFetch<any>(`/services/${id}/actions/node-restart`, {
    method: 'POST',
    body: JSON.stringify({ location_id: locationId }),
  }).then((res) => {
    if (isApiError(res)) return res
    return {
      status: res.status,
      node: normalizeNodeViewer(res.node),
      before: res.before ? normalizeNodeViewer(res.before) : undefined,
      after: res.after ? normalizeNodeViewer(res.after) : undefined,
      message: res.message,
      release: res.release ? normalizeNodeReleaseCheck(res.release) : undefined,
    }
  })

export const getNodeReleaseCheck = (
  id: string,
  locationId?: string,
): Promise<ApiResult<NodeReleaseCheck>> =>
  apiFetch<any>(`/services/${id}/actions/node-release-check`, {
    method: 'POST',
    body: JSON.stringify({ location_id: locationId }),
  }).then((res) => (isApiError(res) ? res : normalizeNodeReleaseCheck(res)))

export const createPullBundle = (
  id: string,
  req: PullBundleRequest,
): Promise<ApiResult<PullBundleRecord & { files?: unknown[] }>> =>
  apiFetch<PullBundleRecord & { files?: unknown[] }>(`/services/${id}/pull-bundles`, {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const preflightPullBundle = (
  id: string,
  req: PullBundleRequest,
): Promise<ApiResult<PullBundlePreflight>> =>
  apiFetch<any>(`/services/${id}/pull-bundles/preflight`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => (isApiError(res) ? res : { ...res, freshness: normalizeFreshness(res.freshness ?? res) } satisfies PullBundlePreflight))

export const listPullBundles = (
  id: string,
): Promise<ApiResult<PullBundleRecord[]>> =>
  apiFetch<PullBundlesResponse>(`/services/${id}/pull-bundles`).then((res) => {
    if (isApiError(res)) return res
    if (!hasObjectProperty(res, 'bundles') || !Array.isArray(res.bundles)) {
      return { status: 'unverified', message: 'Invalid pull bundle history response' }
    }
    return res.bundles as PullBundleRecord[]
  })

export function normalizeTaskLedgerEntry(entry: any): TaskLedgerEntry {
  return {
    ...normalizeFreshness(entry),
    timestamp: entry.timestamp ?? '',
    title: entry.title ?? '',
    task_id: entry.task_id,
    agent: entry.agent,
    tool: entry.tool,
    tags: entry.tags ?? [],
    summary: entry.summary,
    changed_paths: entry.changed_paths ?? [],
    version: entry.version,
    bootstrap_version: entry.bootstrap_version,
    runtime_services: entry.runtime_services ?? [],
    dependencies: entry.dependencies ?? [],
    cross_dependencies: entry.cross_dependencies ?? [],
    diagram: entry.diagram,
    notes: entry.notes,
    scope_entries: (entry.scope_entries ?? []).map(normalizeScopeEntry),
    runtime: entry.runtime ? normalizeRuntimeConfig(entry.runtime) : undefined,
    readme: entry.readme,
    api: entry.api,
    changelog: entry.changelog,
    node_id: entry.node_id,
  }
}

export function normalizeActionLock(lock: any): ActionLock {
  return {
    action_key: lock.action_key ?? '',
    service_id: lock.service_id ?? '',
    started_at: lock.started_at ?? '',
    expires_at: lock.expires_at ?? '',
    ttl_seconds: lock.ttl_seconds ?? 0,
    status: lock.status ?? '',
  }
}

export const getTaskLedger = (serviceId: string): Promise<ApiResult<{ tasks: TaskLedgerEntry[] }>> =>
  apiFetch<{ tasks: any[] }>(`/services/${serviceId}/task-ledger`).then((res) => {
    if (isApiError(res)) return res
    return { tasks: res.tasks.map(normalizeTaskLedgerEntry) }
  })

export const getActionLocks = (serviceId: string): Promise<ApiResult<{ locks: ActionLock[] }>> =>
  apiFetch<{ locks: any[] }>(`/services/${serviceId}/action-locks`).then((res) => {
    if (isApiError(res)) return res
    return { locks: res.locks.map(normalizeActionLock) }
  })

export const acquireActionLock = (serviceId: string, actionKey: string): Promise<ApiResult<{ status: string; lock?: ActionLock }>> =>
  apiFetch<{ status: string; lock: any }>(`/services/${serviceId}/action-locks`, {
    method: 'POST',
    body: JSON.stringify({ action_key: actionKey }),
  }).then((res) => {
    if (isApiError(res)) return res
    return { status: res.status, lock: res.lock ? normalizeActionLock(res.lock) : undefined }
  })

export const releaseActionLock = (serviceId: string, actionKey: string): Promise<ApiResult<{ status: string }>> =>
  apiFetch<{ status: string }>(`/services/${serviceId}/action-locks/${actionKey}`, {
    method: 'DELETE',
  }).then((res) => {
    if (isApiError(res)) return res
    return { status: res.status }
  })

export const workspaceHealthCheck = (workspaceId: string, runtimePasswords: Record<string, string> = {}): Promise<ApiResult<{ results: RuntimeCheckResult[] }>> =>
  apiFetch<{ results: any[] }>(`/workspaces/${workspaceId}/health-check`, {
    method: 'POST',
    body: JSON.stringify(runtimePasswords),
  }).then((res) => {
    if (isApiError(res)) return res
    return { results: res.results.map(normalizeRuntimeCheck) }
  })

export const listProjects = (
  workspaceId: string,
): Promise<ApiResult<{ projects: ProjectManifest[]; environments: ProjectEnvironmentView[]; rollups: ProjectPullSummary[] }>> =>
  apiFetch<{ projects: any[]; environments?: any[]; rollups?: any[] }>(`/workspaces/${workspaceId}/projects`).then((res) => {
    if (isApiError(res)) return res
    return {
      projects: res.projects,
      environments: (res.environments ?? []) as ProjectEnvironmentView[],
      rollups: (res.rollups ?? []) as ProjectPullSummary[],
    }
  })

export const getEnvironmentLab = (
  environmentId: string,
): Promise<ApiResult<EnvironmentLabView>> =>
  apiFetch<any>(`/project-environments/${environmentId}/lab`).then((res) => {
    if (isApiError(res)) return res
    return {
      project: res.project,
      environment: res.environment as ProjectEnvironmentView,
      runtime_snapshot: res.runtime_snapshot ? normalizeEnvironmentRuntimeSnapshot(res.runtime_snapshot) : undefined,
      api_flows: (res.api_flows ?? []).map(normalizeApiFlow),
      api_runs: Object.fromEntries(
        Object.entries(res.api_runs ?? {}).map(([flowId, runs]) => [flowId, (runs as any[]).map(normalizeApiFlowRun)]),
      ),
    }
  })

export const refreshEnvironmentRuntimeSnapshot = (
  environmentId: string,
  req: EnvironmentRuntimeSnapshotRequest = {},
): Promise<ApiResult<EnvironmentRuntimeSnapshot>> =>
  apiFetch<any>(`/project-environments/${environmentId}/runtime-snapshot`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => (isApiError(res) ? res : normalizeEnvironmentRuntimeSnapshot(res)))

export const listApiFlows = (
  environmentId: string,
): Promise<ApiResult<ApiFlowManifest[]>> =>
  apiFetch<any>(`/project-environments/${environmentId}/api-flows`).then((res) => {
    if (isApiError(res)) return res
    return (res.flows ?? []).map(normalizeApiFlow)
  })

export const createApiFlow = (
  environmentId: string,
  req: ApiFlowCreateRequest,
): Promise<ApiResult<ApiFlowManifest>> =>
  apiFetch<any>(`/project-environments/${environmentId}/api-flows`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => (isApiError(res) ? res : normalizeApiFlow(res.flow)))

export const updateApiFlow = (
  environmentId: string,
  flowId: string,
  req: ApiFlowPatchRequest,
): Promise<ApiResult<ApiFlowManifest>> =>
  apiFetch<any>(`/project-environments/${environmentId}/api-flows/${flowId}`, {
    method: 'PATCH',
    body: JSON.stringify(req),
  }).then((res) => (isApiError(res) ? res : normalizeApiFlow(res.flow)))

export const deleteApiFlow = (
  environmentId: string,
  flowId: string,
): Promise<ApiResult<ApiFlowManifest>> =>
  apiFetch<any>(`/project-environments/${environmentId}/api-flows/${flowId}`, {
    method: 'DELETE',
  }).then((res) => (isApiError(res) ? res : normalizeApiFlow(res.flow)))

export const runApiFlow = (
  environmentId: string,
  flowId: string,
): Promise<ApiResult<ApiFlowRunRecord>> =>
  apiFetch<any>(`/project-environments/${environmentId}/api-flows/${flowId}/run`, {
    method: 'POST',
    body: JSON.stringify({}),
  }).then((res) => (isApiError(res) ? res : normalizeApiFlowRun(res.run)))

export const getApiFlowRuns = (
  environmentId: string,
  flowId: string,
): Promise<ApiResult<ApiFlowRunRecord[]>> =>
  apiFetch<any>(`/project-environments/${environmentId}/api-flows/${flowId}/runs`).then((res) => {
    if (isApiError(res)) return res
    return (res.runs ?? []).map(normalizeApiFlowRun)
  })

export const getEnvironmentPullRollup = (
  environmentId: string,
): Promise<ApiResult<ProjectPullSummary>> =>
  apiFetch<any>(`/project-environments/${environmentId}/pull-rollup`).then((res) => {
    if (isApiError(res)) return res
    return res.pull_rollup as ProjectPullSummary
  })

export const createProject = (workspaceId: string, req: ProjectCreateRequest): Promise<ApiResult<{ project: ProjectManifest }>> =>
  apiFetch<{ project: any }>(`/workspaces/${workspaceId}/projects`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => {
    if (isApiError(res)) return res
    return { project: res.project }
  })

export const updateProject = (projectId: string, req: ProjectPatchRequest): Promise<ApiResult<{ project: ProjectManifest }>> =>
  apiFetch<{ project: any }>(`/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify(req),
  }).then((res) => {
    if (isApiError(res)) return res
    return { project: res.project }
  })

export const deleteProject = (projectId: string): Promise<ApiResult<{ project: ProjectManifest }>> =>
  apiFetch<{ project: any }>(`/projects/${projectId}`, {
    method: 'DELETE',
  }).then((res) => {
    if (isApiError(res)) return res
    return { project: res.project }
  })

export const createProjectEnvironment = (
  projectId: string,
  req: ProjectEnvironmentCreateRequest,
): Promise<ApiResult<{ environment: ProjectEnvironmentView }>> =>
  apiFetch<{ environment: any }>(`/projects/${projectId}/environments`, {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => {
    if (isApiError(res)) return res
    return { environment: res.environment as ProjectEnvironmentView }
  })

export const updateProjectEnvironment = (
  environmentId: string,
  req: ProjectEnvironmentPatchRequest,
): Promise<ApiResult<{ environment: ProjectEnvironmentView }>> =>
  apiFetch<{ environment: any }>(`/project-environments/${environmentId}`, {
    method: 'PATCH',
    body: JSON.stringify(req),
  }).then((res) => {
    if (isApiError(res)) return res
    return { environment: res.environment as ProjectEnvironmentView }
  })

export const deleteProjectEnvironment = (
  environmentId: string,
): Promise<ApiResult<{ environment: ProjectEnvironmentView }>> =>
  apiFetch<{ environment: any }>(`/project-environments/${environmentId}`, {
    method: 'DELETE',
  }).then((res) => {
    if (isApiError(res)) return res
    return { environment: res.environment as ProjectEnvironmentView }
  })

export const createCompany = (req: CompanyCreateRequest): Promise<ApiResult<{ company: Workspace }>> =>
  apiFetch<{ company: any }>('/companies', {
    method: 'POST',
    body: JSON.stringify(req),
  }).then((res) => {
    if (isApiError(res)) return res
    return { company: normalizeWorkspace(res.company, []) }
  })

export const updateCompany = (companyId: string, req: CompanyPatchRequest): Promise<ApiResult<{ company: Workspace }>> =>
  apiFetch<{ company: any }>(`/companies/${companyId}`, {
    method: 'PATCH',
    body: JSON.stringify(req),
  }).then((res) => {
    if (isApiError(res)) return res
    return { company: normalizeWorkspace(res.company, []) }
  })

export const deleteCompany = (companyId: string): Promise<ApiResult<{ company: Workspace }>> =>
  apiFetch<{ company: any }>(`/companies/${companyId}`, {
    method: 'DELETE',
  }).then((res) => {
    if (isApiError(res)) return res
    return { company: normalizeWorkspace(res.company, []) }
  })

export const createServer = (req: ServerCreateRequest): Promise<ApiResult<{ server: any }>> =>
  apiFetch<{ server: any }>('/servers', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const updateServer = (serverId: string, req: ServerPatchRequest): Promise<ApiResult<{ server: any }>> =>
  apiFetch<{ server: any }>(`/servers/${serverId}`, {
    method: 'PATCH',
    body: JSON.stringify(req),
  })

export const deleteServer = (serverId: string): Promise<ApiResult<{ server: any }>> =>
  apiFetch<{ server: any }>(`/servers/${serverId}`, {
    method: 'DELETE',
  })
