export type CollectStatus =
  | 'ok'
  | 'partial'
  | 'auth_failed'
  | 'unreachable'
  | 'vpn_or_network_blocked'
  | 'command_missing'
  | 'path_missing'
  | 'not_git_repo'
  | 'dirty_repo'
  | 'permission_limited'
  | 'skipped_by_exclude'
  | 'unverified'
  | 'action_in_progress'

export interface PortInfo {
  port: number
  protocol: string
  process: string
  pid?: number | null
  state?: string
  bind_address?: string
}

export interface RuntimeConfig {
  expected_ports: number[]
  healthcheck_command: string
  run_command_hint: string
  monitoring_mode: 'manual' | 'detect' | 'node_managed'
  notes: string
}

export type ExecutionMode = 'networked' | 'batch' | 'lambda' | 'docs_only'

export interface FreshnessMeta {
  data_as_of?: string
  truth_as_of?: string
  freshness_state?: 'Fresh' | 'Stale' | 'Unverified' | 'Manager unreachable' | string
  stale_reason?: string
  refresh_action?: string
  freshness_source?: string
}

export interface RepoSummary {
  path: string
  branch: string
  commit: string
  dirty: boolean
  status: CollectStatus
  is_allowlisted: boolean
  server_id?: string
  remotes?: string[]
  push_mode?: 'allowed' | 'blocked'
  safety_profile?: 'generic_python' | 'secret_heavy'
  push_eligible?: boolean
}

export interface ServiceLocation {
  location_id: string
  server_id: string
  access_mode: 'local' | 'ssh'
  root: string
  role: string
  is_primary: boolean
  path_aliases: string[]
  runtime: RuntimeConfig
}

export interface ServiceLocationDraft {
  location_id: string
  server_id: string
  access_mode: 'local' | 'ssh'
  root: string
  role: string
  is_primary: boolean
  path_aliases: string[]
  runtime: RuntimeConfig
}

export interface ScopeEntry {
  entry_id?: string
  kind: 'repo' | 'code' | 'doc' | 'log' | 'exclude'
  path: string
  path_type: 'file' | 'dir' | 'glob'
  source: 'seeded' | 'user_added' | 'node_manifest' | 'tasks_completed' | 'manual_consolidation'
  enabled: boolean
}

export interface RepoPolicy {
  repo_path: string
  push_mode: 'allowed' | 'blocked'
  safety_profile: 'generic_python' | 'secret_heavy'
  allowed_branches: string[]
  allowed_remotes: string[]
}

export type ManagedDocId =
  | 'readme'
  | 'api'
  | 'changelog'
  | 'handoff'
  | 'runbook'
  | 'approach_history'
  | 'doc_index_md'
  | 'doc_index_json'

export interface ManagedDocConfig {
  doc_id: ManagedDocId
  path: string
  enabled: boolean
  generated_from: string
  last_generated_at?: string | null
}

export interface DocIndexEntry {
  doc_id: ManagedDocId
  label?: string
  path: string
  enabled: boolean
  generated_at?: string | null
  generated_from?: string
  contributor_timestamps: string[]
}

export interface DocIndexState {
  generated: string
  service_id?: string
  project_root?: string
  docs: DocIndexEntry[]
}

export type ServiceKind = 'service' | 'external_service' | 'database' | 'deployment_host' | 'dependency_node'

export interface RuntimeService {
  name: string
  host?: string
  port?: number
  purpose?: string
  health_path?: string
  owner?: string
}

export type DependencyKind = 'service' | 'database' | 'deployment_host' | 'saas' | 'shared_data' | 'api' | 'runtime' | 'library'

export interface DependencyNode {
  kind: DependencyKind
  name: string
  host?: string
  port?: number
  notes?: string
}

export interface TaskLedgerEntry {
  timestamp: string
  title: string
  task_id?: string
  agent?: string
  tool?: string
  tags?: string[]
  summary?: string
  changed_paths?: string[]
  version?: string
  bootstrap_version?: string
  runtime_services?: RuntimeService[]
  dependencies?: DependencyNode[]
  cross_dependencies?: DependencyNode[]
  diagram?: string
  notes?: string[]
  scope_entries?: ScopeEntry[]
  runtime?: RuntimeConfig
  readme?: string
  api?: string
  changelog?: string
  node_id?: string
  service_name?: string
  data_as_of?: string
  truth_as_of?: string
  freshness_state?: string
  stale_reason?: string
  refresh_action?: string
  freshness_source?: string
}

export interface ActionLock {
  action_key: string
  service_id: string
  started_at: string
  expires_at: string
  ttl_seconds: number
  status: string
}

export interface ProjectManifest {
  project_id: string
  workspace_id: string
  display_name: string
  parent_project_id?: string | null
  service_ids: string[]
  tags: string[]
  notes: string
}

export type ProjectEnvironmentKind = 'dev' | 'test' | 'staging' | 'qa' | 'prod' | 'custom'

export interface ProjectDeploymentRef {
  service_id: string
  location_id?: string
  server_id?: string
  root?: string
  version?: string
  runtime_services?: RuntimeService[]
  dependencies?: DependencyNode[]
  cross_dependencies?: DependencyNode[]
  notes?: string
}

export interface ProjectEnvironmentManifest {
  environment_id: string
  project_id: string
  display_name: string
  kind: ProjectEnvironmentKind
  deployments: ProjectDeploymentRef[]
  tags: string[]
  notes: string
}

export interface ProjectPullSummary {
  project_id: string
  environment_id?: string
  added_count: number
  removed_count: number
  changed_count: number
  unchanged_count: number
  latest_created_at: string
  service_count: number
  summary?: string
}

export interface EnvironmentDependencySummary {
  dependencies: DependencyNode[]
  cross_dependencies: DependencyNode[]
  composition?: DependencyComposition
}

export interface DependencyComposition {
  basis: string
  language_percentages: Array<{
    name: string
    percentage: number
    file_count: number
  }>
  ai_percentage: number
  llm_percentage: number
  embedding_percentage: number
  models: ModelUsage[]
}

export interface ModelUsage {
  name: string
  category: 'llm' | 'embedding' | 'unknown'
  source: string
}

export interface ProjectEnvironmentServiceSummary {
  service_id: string
  display_name: string
  execution_mode: ExecutionMode
  location_id?: string
  server_id?: string
  root?: string
  version?: string
  runtime_services?: RuntimeService[]
  dependencies?: DependencyNode[]
  cross_dependencies?: DependencyNode[]
  runtime_snapshot?: EnvironmentLocationSnapshot
  runtime_checks?: RuntimeCheckResult[]
  node_viewer?: NodeViewerEntry[]
  node_health?: {
    status: string
    runtime_ready: boolean
    bootstrap_ready: boolean
    runtime_port?: number
    checked_at?: string
    freshness_state?: string
    stale_reason?: string
    refresh_action?: string
  }
  service_health?: {
    status: string
    healthcheck_status: string
    checked_at?: string
    healthcheck_command?: string
    healthcheck_output?: string
  }
  pull_summary?: ProjectPullSummary
  notes?: string
}

export interface ProjectEnvironmentView extends ProjectEnvironmentManifest {
  pull_summary?: ProjectPullSummary
  dependency_summary?: EnvironmentDependencySummary
  service_summaries?: ProjectEnvironmentServiceSummary[]
  runtime_snapshot?: EnvironmentRuntimeSnapshot
  runtime_snapshot_summary?: {
    captured_at: string
    open_port_count: number
    exposed_port_count: number
    firewall_status: string
  }
  api_flow_count?: number
  latest_flow_run_at?: string
}

export type ApiFlowTargetKind = 'service' | 'dependency' | 'cross_dependency'
export type CaptureSource = 'json' | 'header'

export interface ApiStepCapture {
  variable_name: string
  source: CaptureSource
  selector: string
}

export interface ApiFlowStep {
  step_id: string
  order: number
  display_name: string
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS'
  path: string
  query: Record<string, string>
  headers: Record<string, string>
  body: string
  expected_status: number
  continue_on_failure: boolean
  timeout_seconds: number
  notes: string
  captures: ApiStepCapture[]
}

export interface ApiFlowManifest {
  flow_id: string
  environment_id: string
  service_id?: string
  display_name: string
  target_kind: ApiFlowTargetKind
  target_name: string
  base_url: string
  execution_mode: 'http'
  enabled: boolean
  tags: string[]
  notes: string
  steps: ApiFlowStep[]
}

export interface ApiStepRunResult {
  step_id: string
  status: 'ok' | 'failed' | 'skipped'
  resolved_url: string
  duration_ms: number
  request_preview: {
    method: string
    url: string
    headers: Record<string, string>
    body_preview: string
  }
  response_status: number
  response_headers: Record<string, string>
  response_body_preview: string
  extracted_variables: Record<string, string>
  generated_curl: string
  error: string
}

export interface ApiFlowRunRecord {
  run_id: string
  flow_id: string
  environment_id: string
  started_at: string
  finished_at: string
  status: 'ok' | 'partial' | 'failed'
  step_results: ApiStepRunResult[]
  summary: string
}

export interface OperatorCommand {
  category: 'inspect_only' | 'verify_listener' | 'verify_firewall' | 'verify_health' | 'verify_node'
  label: string
  command: string
  notes: string
}

export interface ProcessFinding {
  port?: number
  bind_address: string
  process_name: string
  pid?: number
  state: string
  raw: string
  owner_service_id: string
  owner_display_name: string
  owner_location_id: string
  owner_root: string
}

export interface PortExposureFinding {
  host: string
  port: number
  bind_address: string
  process_name: string
  expected: boolean
  exposure: 'local_only' | 'public' | 'unknown'
  notes: string
}

export interface EnvironmentLocationSnapshot {
  service_id: string
  service_name: string
  execution_mode: ExecutionMode
  location_id: string
  server_id: string
  root: string
  host: string
  firewall_status: string
  node_status: string
  expected_ports: number[]
  open_ports: number[]
  unexpected_ports: number[]
  exposed_ports: PortExposureFinding[]
  process_findings: ProcessFinding[]
  operator_commands: OperatorCommand[]
  runtime_hint: string
  healthcheck_command: string
  healthcheck_status: string
  healthcheck_output: string
}

export interface EnvironmentRuntimeSnapshot {
  environment_id: string
  captured_at: string
  locations: EnvironmentLocationSnapshot[]
  open_ports: number[]
  expected_ports: number[]
  unexpected_ports: number[]
  exposed_ports: PortExposureFinding[]
  firewall_status: string
  process_findings: ProcessFinding[]
  node_findings: Array<Record<string, unknown>>
  operator_commands: OperatorCommand[]
}

export interface EnvironmentLabView {
  project: ProjectManifest
  environment: ProjectEnvironmentView
  runtime_snapshot?: EnvironmentRuntimeSnapshot
  api_flows: ApiFlowManifest[]
  api_runs: Record<string, ApiFlowRunRecord[]>
}

export interface CompanyCreateRequest {
  workspace_id: string
  name: string
  tags?: string[]
  notes?: string
}

export interface CompanyPatchRequest {
  name?: string
  tags?: string[]
  notes?: string
}

export interface ServerCreateRequest {
  server_id: string
  company_id?: string
  name: string
  connection_type: 'local' | 'ssh'
  host?: string
  username?: string
  port?: number
  deployment_mode?: 'native_agent' | 'local_bundle_only'
  vpn_required?: boolean
  tags: string[]
  notes: string
  local_password?: string
}

export interface ServerPatchRequest {
  company_id?: string
  name?: string
  host?: string
  username?: string
  port?: number
  deployment_mode?: 'native_agent' | 'local_bundle_only'
  vpn_required?: boolean
  tags?: string[]
  notes?: string
  local_password?: string
}

export interface ProjectCreateRequest {
  project_id: string
  display_name: string
  parent_project_id?: string | null
  service_ids?: string[]
  tags?: string[]
  notes?: string
}

export interface ProjectPatchRequest {
  project_id?: string
  display_name?: string
  parent_project_id?: string | null
  service_ids?: string[]
  tags?: string[]
  notes?: string
}

export interface ProjectEnvironmentCreateRequest {
  environment_id: string
  display_name: string
  kind?: ProjectEnvironmentKind
  deployments?: ProjectDeploymentRef[]
  tags?: string[]
  notes?: string
}

export interface ProjectEnvironmentPatchRequest {
  environment_id?: string
  display_name?: string
  kind?: ProjectEnvironmentKind
  deployments?: ProjectDeploymentRef[]
  tags?: string[]
  notes?: string
}

export interface EnvironmentRuntimeSnapshotRequest {
  runtime_passwords?: Record<string, string>
}

export interface ApiFlowCreateRequest {
  flow_id: string
  service_id?: string
  display_name: string
  target_kind?: ApiFlowTargetKind
  target_name?: string
  base_url?: string
  execution_mode?: 'http'
  enabled?: boolean
  tags?: string[]
  notes?: string
  steps?: ApiFlowStep[]
}

export interface ApiFlowPatchRequest {
  flow_id?: string
  service_id?: string
  display_name?: string
  target_kind?: ApiFlowTargetKind
  target_name?: string
  base_url?: string
  execution_mode?: 'http'
  enabled?: boolean
  tags?: string[]
  notes?: string
  steps?: ApiFlowStep[]
}

export type PendingActionKey = `${string}:${string}:${'pull_bundle'|'sync_to_node'|'sync_from_node'|'runtime_check'}`

export interface PendingActionState {
  startedAt: string
  label: string
}

export interface ActionExplainConfig {
  title: string
  happens: string[]
  untouched: string[]
  writesTo: string[]
}

export interface Service extends FreshnessMeta {
  service_id: string
  workspace_id: string
  display_name: string
  kind: ServiceKind
  execution_mode: ExecutionMode
  tags: string[]
  favorite_tier: number
  locations: ServiceLocation[]
  repo_paths: string[]
  docs_paths: string[]
  log_paths: string[]
  allowed_git_pull_paths: string[]
  exclude_globs: string[]
  scope_entries: ScopeEntry[]
  managed_docs: ManagedDocConfig[]
  repo_policies: RepoPolicy[]
  notes: string
  path_aliases: string[]
  runtime_checks?: RuntimeCheckResult[]
  node_sync?: NodeSyncResult[]
  task_ledger?: TaskLedgerEntry[]
  node_viewer?: NodeViewerEntry[]
  saved_scope_generated_at?: string
  freshness?: FreshnessMeta
}

export interface ServiceRunResult extends FreshnessMeta {
  service_id: string
  status: CollectStatus
  ports: PortInfo[]
  firewall_status: string
  firewall_active: boolean
  repo_summaries: RepoSummary[]
  docs_count: number
  logs_count: number
  docs_files: FileEntry[]
  logs_files: FileEntry[]
  secret_path_count: number
  collected_at: string
  runtime_checks?: RuntimeCheckResult[]
  node_sync?: NodeSyncResult[]
}

export interface FileEntry {
  path: string
  name: string
  size_bytes: number
  modified: string
  kind: 'doc' | 'log' | 'repo'
}

export interface Workspace {
  workspace_id: string
  company_id?: string
  display_name: string
  services: Service[]
  server_ids: string[]
  service_count?: number
  server_count?: number
  tags?: string[]
  notes?: string
}

export interface WorkspaceLatest {
  workspace: Workspace
  company?: Workspace
  servers: ServerInfo[]
  services: ServiceRunResult[]
  summary: CollectSummary
  repo_inventory: RepoSummary[]
  docs_index: FileEntry[]
  logs_index: FileEntry[]
  node_sync_results?: NodeSyncResult[]
  freshness?: FreshnessMeta
  archived_service_ids?: string[]
  current_service_ids?: string[]
}

export interface ServerInfo {
  server_id: string
  host: string
  type: string
  role: string
  port: number
  status?: CollectStatus
}

export interface ServerRecord {
  server_id: string
  company_id?: string
  name?: string
  connection_type?: 'local' | 'ssh'
  host?: string
  username?: string
  port?: number
  deployment_mode?: 'native_agent' | 'local_bundle_only'
  vpn_required?: boolean
  tags?: string[]
  notes?: string
}

export interface CollectSummary extends FreshnessMeta {
  run_id: string
  workspace_id: string
  timestamp: string
  status: CollectStatus
  triggered_by?: string
  server_count?: number
  service_count?: number
  node_sync_count?: number
  node_sync_blocked_count?: number
}

export interface RunRecord {
  run_id: string
  workspace_id: string
  timestamp: string
  status: CollectStatus
  triggered_by: string
}

export interface HealthResponse {
  status: string
  version?: string
  timestamp?: string
  framework?: string
  vpn_note?: string
}

export interface ApiError {
  status: CollectStatus
  message: string
  code?: number
}

export type ApiResult<T> = T | ApiError

export function isApiError(v: unknown): v is ApiError {
  return typeof v === 'object' && v !== null && 'message' in v && 'status' in v
}

export interface CollectOptions {
  service_filter?: string[]
  password_overrides?: Record<string, string>
  include_node_sync?: boolean
}

export interface DownloadRequest {
  server_id?: string
  files: string[]
  kind: 'doc' | 'log'
}

export interface RepoActionRequest {
  repo_path: string
  server_id?: string
  runtime_password?: string
}

export interface RuntimeActionRequest {
  location_id?: string
  runtime_password?: string
}

export interface NodeSyncRequest extends RuntimeActionRequest {
  include_scope_snapshot?: boolean
  include_runtime_config?: boolean
  include_task_ledger?: boolean
  include_dependency_context?: boolean
}

export interface GitPullRequest extends RepoActionRequest {}

export interface GitPushRequest extends RepoActionRequest {
  remote?: string
  branch?: string
}

export interface GitPullResult {
  repo_path: string
  status: CollectStatus
  output: string
  stdout?: string
  stderr?: string
}

export interface GitHubBackupRequest {
  workspace_id?: string
  service_ids?: string[]
  runtime_passwords?: Record<string, string>
  remote?: string
  dry_run?: boolean
}

export interface GitHubBackupRepo {
  workspace_id: string
  service_id: string
  repo_path: string
  server_id: string
  status: CollectStatus
  branch: string
  dirty: boolean
  last_commit: string
  remote_count: number
  github_remote: boolean
  push_mode: 'allowed' | 'blocked'
  eligible: boolean
  blocking_reasons: string[]
}

export interface GitHubBackupResult {
  status: CollectStatus
  generated: string
  workspace_id: string
  service_ids: string[]
  repository_count: number
  eligible_count: number
  blocked_count: number
  credential_note: string
  repositories: GitHubBackupRepo[]
  action?: 'dry_run' | 'run'
  pushed_count?: number
  push_results?: Array<Record<string, unknown>>
}

export interface PullBundleGithubBackupDryRunRequest {
  bundle_id?: string
}

export interface PullBundleGithubBackupDryRun {
  run_id: string
  generated_at: string
  service_id: string
  bundle_id: string
  source_tree_path: string
  source_policy?: string
  target_repo: string
  target_remote: string
  target_branch: string
  repo_head: string
  repo_dirty: boolean
  repo_head_at_run?: string
  repo_dirty_at_run?: boolean
  report_artifact_write?: boolean
  current_repo_head?: string
  current_repo_dirty?: boolean
  repo_status?: string
  bundle_profile: string
  backup_readiness_status: 'proof_only' | 'review_required' | 'not_backup_ready'
  not_backup_ready: boolean
  not_push_ready: boolean
  status: 'blocked' | CollectStatus
  included_file_count: number
  skipped_entry_count: number
  unresolved_exposure_count: number
  review_state_counts: Record<ExposureReviewState, number>
  review_counts_hash?: string
  current_review_counts_hash?: string
  authority_fresh: boolean
  authority_updated_at: string
  bundle_created_at?: string
  bundle_authority_updated_at?: string
  control_center_truth_as_of: string
  pull_authority_truth_as_of?: string
  manager_health_checked_at?: string
  freshness_state?: 'current' | 'stale_repo_head' | 'stale_authority' | 'stale_review_state' | 'superseded' | 'historical' | string
  freshness_reasons?: string[]
  superseded_by?: string
  blocked_reasons: string[]
  would_stage_files: string[]
  would_commit: boolean
  would_push: boolean
  push_performed: boolean
  commit_performed: boolean
  stage_performed: boolean
  git_readonly_commands?: string[]
  bundle_history_count?: number
}

export interface RepoStateResult extends RepoSummary {
  repo_path: string
}

export interface SecretPathsResult {
  generated: string
  service_id: string
  count: number
  // entries intentionally omitted from UI types — use count only
}

export interface ScanEntry {
  path: string
  name: string
  entry_type: 'file' | 'dir'
  depth: number
  suggested_kind: 'repo' | 'code' | 'doc' | 'log' | 'exclude'
}

export interface TreeNodeEntry {
  path: string
  name: string
  node_type: 'file' | 'dir'
  entry_type?: 'file' | 'dir'
  has_children: boolean
  children_loaded: boolean
  suggested_kind: 'repo' | 'code' | 'doc' | 'log' | 'exclude'
  default_selected: boolean
}

export interface ScanRootRequest {
  server_id: string
  root: string
  runtime_password?: string
  max_depth?: number
}

export interface ScanRootResult {
  status: CollectStatus
  generated?: string
  server_id: string
  root: string
  entries: ScanEntry[]
}

export interface DiscoveryTreeRequest {
  server_id: string
  root: string
  node_path?: string
  runtime_password?: string
}

export interface DiscoveryTreeResult {
  status: CollectStatus
  generated?: string
  server_id: string
  root: string
  node_path: string
  message?: string
  current_node: TreeNodeEntry | null
  entries: TreeNodeEntry[]
}

export interface SafetyCheckResult {
  generated: string
  service_id: string
  repo_path: string
  server_id: string
  scanner: string
  push_mode: 'allowed' | 'blocked'
  safety_profile: 'generic_python' | 'secret_heavy'
  finding_count: number
  blocking_reason_count: number
  blocking_reasons: string[]
  safe_to_push: boolean
  safe_to_deploy: boolean
  status: CollectStatus
  repo_state: RepoSummary
}

export interface RuntimeCheckResult extends FreshnessMeta {
  service_id: string
  location_id: string
  server_id: string
  root: string
  status: CollectStatus
  checked_at: string
  execution_mode?: ExecutionMode
  configured_ports: number[]
  detected_ports: PortInfo[]
  missing_ports: number[]
  healthcheck_command: string
  healthcheck_status: 'ok' | 'failed' | 'skipped'
  healthcheck_output: string
  detected_process_command: string
  run_command_hint: string
  monitoring_mode: 'manual' | 'detect' | 'node_managed'
  notes: string
  node_present: boolean
  source?: string
  firewall_status?: string
  unexpected_ports?: number[]
  process_findings?: ProcessFinding[]
  exposed_ports?: PortExposureFinding[]
  operator_commands?: OperatorCommand[]
}

export interface NodeSyncResult extends FreshnessMeta {
  service_id: string
  location_id: string
  direction?: 'from_node' | 'to_node'
  timestamp: string
  status: CollectStatus
  source: string
  target: string
  include_scope_snapshot: boolean
  include_runtime_config: boolean
  managed_docs?: ManagedDocConfig[]
  doc_index?: DocIndexState
  server_id?: string
  message?: string
  scope_snapshot_generated_at?: string
  skipped?: boolean
}

export interface PullBundleRequest {
  server_id?: string
  location_id?: string
  runtime_password?: string
  extra_includes: ScopeEntry[]
  extra_excludes: string[]
  note?: string
}

export interface PullBundlePreflight {
  status: CollectStatus
  message: string
  service_id: string
  server_id?: string
  location_id?: string
  root?: string
  connection_type?: 'local' | 'ssh'
  source_authority?: PullBundleAuthority
  node_local_scope_timestamp?: string
  node_scope_generated_at?: string
  control_center_scope_timestamp?: string
  authority_stale?: boolean
  missing_remote_sync?: boolean
  missing_authority_timestamp?: boolean
  vpn_required?: boolean
  fix?: string
  bundle_profile?: string
  backup_clean?: boolean
  backup_clean_exclude_count?: number
  include_count?: number
  saved_include_count?: number
  extra_include_count?: number
  exclude_count?: number
  suspicious_entries?: Array<{ path: string; kind: string; reason: string }>
  blocked_reasons?: string[]
  freshness?: FreshnessMeta
  location_required?: boolean
  locations?: Array<{
    location_id: string
    server_id: string
    root: string
    role: string
    is_primary?: boolean
  }>
}

export interface ExposureFinding {
  relative_path: string
  finding_kind: string
  variable_name?: string
  line_number: number
  redacted: boolean
}

export interface PullBundleDiffSummary {
  added_count: number
  removed_count: number
  changed_count: number
  unchanged_count: number
  summary: string
}

export interface PullBundleDiffEntry {
  change: 'added' | 'removed' | 'changed'
  relative_path: string
  kind: 'repo' | 'code' | 'doc' | 'log'
}

export interface DependencyContext {
  dependencies: DependencyNode[]
  cross_dependencies: DependencyNode[]
  notes: string[]
  diagram: string
  composition?: DependencyComposition
}

export interface PullBundleMetadataSummaries {
  profile?: string
  source_tree_policy?: string
  raw_evidence_files?: string
  copied_summary?: Record<string, number>
  skipped_summary?: Record<string, number>
  exposure_summary?: Record<string, number>
  scope_snapshot_summary?: Record<string, unknown>
  update_gate_summary?: Record<string, unknown>
  completed_tasks_summary?: Record<string, unknown>
  doc_index_summary?: Record<string, unknown>
}

export interface PullBundleAuthority {
  source: 'node-local' | 'control-center' | string
  direction: string
  location_id: string
  server_id: string
  root: string
  manifest_path: string
  updated_at: string
  note: string
}

export interface NodeViewerEntry {
  service_id: string
  location_id: string
  server_id: string
  root: string
  connection_status?: CollectStatus
  last_inspected_at?: string
  node_present: boolean
  bootstrap_ready: boolean
  runtime_ready: boolean
  installed_version: string
  bootstrap_version: string
  manifest_updated_at: string
  runtime_status: 'running' | 'stopped' | 'running_unmanaged' | 'missing' | 'manager_running'
  runtime_pid?: number
  runtime_port: number
  runtime_port_source?: string
  needs_install: boolean
  needs_upgrade: boolean
  needs_bootstrap: boolean
  attention_reason?: string
  manifest_path: string
  runtime_dir: string
  log_file: string
  last_error?: string
  installed_release_version?: string
  installed_release_asset_id?: string
  installed_release_asset_name?: string
  installed_release_published_at?: string
  installed_release_url?: string
  installed_release_commitish?: string
  manager_managed?: boolean
  manager_root_id?: string
  manager_root?: string
  manager_version?: string
  data_as_of?: string
  truth_as_of?: string
  freshness_state?: 'Fresh' | 'Stale' | 'Unverified' | 'Manager unreachable' | string
  stale_reason?: string
  refresh_action?: string
  freshness_source?: string
  target_manager_port?: number
  manager_health_status?: string
  manager_health_mode?: string
  manager_health_checked_at?: string
  manager_health_runtime_port?: number
  manager_manifest_runtime_port?: number
  legacy_runtime_port?: number
  legacy_runtime_port_source?: string
  legacy_runtime_port_label?: string
}

export interface NodeActionResult {
  status?: CollectStatus
  node: NodeViewerEntry
  before?: NodeViewerEntry
  after?: NodeViewerEntry
  message?: string
  release?: NodeReleaseCheck
}

export interface NodeReleaseCheck {
  status: CollectStatus
  current_version: string
  latest_version: string
  update_available: boolean
  published_at?: string
  release_url?: string
  asset_url?: string
  notes?: string
  message?: string
  exact_match_known?: boolean
  exact_match?: boolean
  current_release_version?: string
  current_release_asset_id?: string
  current_release_asset_name?: string
  current_release_published_at?: string
  current_release_url?: string
  current_release_commitish?: string
  latest_release_asset_id?: string
  latest_release_asset_name?: string
  latest_release_asset_updated_at?: string
  latest_release_commitish?: string
}

export interface PullBundleRecord {
  bundle_id: string
  created_at: string
  workspace_id: string
  service_id: string
  server_id: string
  bundle_profile?: string
  backup_clean?: boolean
  backup_readiness_status?: 'proof_only' | 'review_required' | 'not_backup_ready'
  review_required?: boolean
  proof_only?: boolean
  not_backup_ready?: boolean
  authority_fresh?: boolean
  unresolved_exposure_count?: number
  exposure_review_status?: 'unreviewed' | 'reviewed'
  exposure_review?: PullBundleExposureReview
  exposure_summary?: Record<string, number>
  exposure_variable_summary?: Record<string, number>
  skipped_review_required?: boolean
  skipped_review_count?: number
  readiness_reasons?: string[]
  file_count: number
  docs_count: number
  logs_count: number
  bundle_path: string
  source_tree_path?: string
  manifest_path: string
  repo_commits: string[]
  note?: string
  compared_to_bundle_id?: string
  diff_summary?: PullBundleDiffSummary
  diff_entries?: PullBundleDiffEntry[]
  exposure_findings?: ExposureFinding[]
  dependency_context?: DependencyContext
  metadata_summaries?: PullBundleMetadataSummaries
  authority?: PullBundleAuthority
  skipped_entry_count?: number
  skipped_entries?: Array<{
    path: string
    kind: 'doc' | 'log' | 'repo' | 'code' | 'exclude'
    path_type: 'file' | 'dir' | 'glob'
    reason: string
  }>
  files?: Array<{
    kind: 'doc' | 'log' | 'repo' | 'code'
    source_path: string
    target_path: string
    relative_path: string
    size: number
    mtime: string
    sha256: string
  }>
}

export type ExposureReviewState = 'unreviewed' | 'false_positive' | 'needs_action' | 'accepted_risk'

export interface PullBundleExposureReviewGroup {
  group_key: string
  bundle_id: string
  finding_kind: string
  relative_path: string
  variable_name?: string
  finding_count: number
  line_numbers?: number[]
  review_state: ExposureReviewState
  review_note?: string
  reviewed_by?: string
  reviewed_at?: string
}

export interface PullBundleExposureReview {
  bundle_id: string
  review_state_counts: Record<ExposureReviewState, number>
  finding_kind_counts: Record<string, number>
  path_counts: Record<string, number>
  variable_counts: Record<string, number>
  total_groups: number
  total_findings: number
  unresolved_review_count: number
  groups: PullBundleExposureReviewGroup[]
}

export interface CreateServiceRequest {
  service_id: string
  display_name: string
  kind?: string
  execution_mode?: ExecutionMode
  ownership_tier?: 'owned' | 'shared' | 'infra'
  tags?: string[]
  favorite_tier?: 'primary' | 'secondary' | 'none'
  locations: ServiceLocationDraft[]
  repo_paths?: string[]
  docs_paths?: string[]
  log_paths?: string[]
  allowed_git_pull_paths?: string[]
  exclude_globs?: string[]
  scope_entries: ScopeEntry[]
  managed_docs?: ManagedDocConfig[]
  repo_policies?: RepoPolicy[]
  notes?: string
  path_aliases?: string[]
}
