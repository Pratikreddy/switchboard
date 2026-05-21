import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, FileStack, FolderTree, LoaderCircle, Pencil, RefreshCw, Server, Save, Trash2, X } from 'lucide-react'
import type {
  ActionLock,
  ManagedDocConfig,
  NodeActionResult,
  ProjectEnvironmentView,
  RuntimeCheckResult,
  Service,
  ServiceLocationDraft,
  ServiceRunResult,
  RepoSummary as RepoSummaryRecord,
  RunRecord,
  ScopeEntry,
  ServerRecord,
  TaskLedgerEntry,
} from '../types/switchboard'
import {
  deleteService,
  deployNode,
  getService,
  getServiceScope,
  getActionLocks,
  getNodeViewer,
  listServers,
  getWorkspaceRuns,
  inspectNode,
  listProjects,
  listPullBundles,
  restartNode,
  runRuntimeCheck,
  syncFromNode,
  syncToNode,
  upgradeNode,
  updateService,
  acquireActionLock,
  releaseActionLock,
} from '../api/client'
import { isApiError } from '../types/switchboard'
import { StatusBadge } from '../components/StatusBadge'
import { RepoSummary } from '../components/RepoSummary'
import { DownloadPanel } from '../components/DownloadPanel'
import { SecretPathGuard } from '../components/SecretPathGuard'
import { PullBundlePanel } from '../components/PullBundlePanel'
import { ConfirmationModal, ACTION_EXPLAIN } from '../components/ConfirmationModal'
import { TaskLedgerPanel } from '../components/TaskLedgerPanel'
import { InfoDropdown } from '../components/InfoDropdown'
import { AccordionSection } from '../components/AccordionSection'

interface Props {
  serviceId: string
  runResult?: ServiceRunResult
  offline: boolean
  onBack: () => void
  onDeleted: (serviceId: string, workspaceId: string) => void
  onOpenEnvironmentLab: (environmentId: string) => void
}

function parsePorts(value: string): number[] {
  return value
    .split(',')
    .map((token) => Number(token.trim()))
    .filter((port) => Number.isFinite(port) && port > 0 && port <= 65535)
}

const SERVICE_PANEL_KEYS = ['port_health', 'project', 'runtime', 'managed_docs', 'task_ledger', 'repositories', 'scope', 'pull_bundles', 'secret_paths', 'run_history'] as const
type ServicePanelKey = (typeof SERVICE_PANEL_KEYS)[number]
const DEFAULT_OPEN_PANELS: ServicePanelKey[] = ['runtime']
const CONTROL_CENTER_PORT = 8009
const DEFAULT_MANAGER_PORT = 8020
const DEV_UI_PORT = 5173
type NodeActionKey = 'inspect' | 'deploy' | 'upgrade' | 'restart'
type LocationActionKey = NodeActionKey | 'runtime_check' | 'sync_from_node' | 'sync_to_node'
type PersistedActionKey = 'node_deploy' | 'node_upgrade' | 'node_restart' | 'runtime_check' | 'sync_from_node' | 'sync_to_node'
type ConfirmActionKey = 'node_inspect' | 'node_deploy' | 'node_upgrade' | 'node_restart' | 'runtime_check' | 'sync_from_node' | 'sync_to_node'

interface ConfirmDetails {
  preflight?: string[]
  followUp?: string[]
  commandPreview?: string[]
  confirmLabel?: string
}

interface LocationActionEvent {
  action: LocationActionKey
  status: 'running' | 'ok' | 'error'
  message: string
  timestamp: string
  started_at?: string
  duration_seconds?: number
}

const ACTION_LOCK_KEY: Record<Exclude<LocationActionKey, 'inspect'>, PersistedActionKey> = {
  deploy: 'node_deploy',
  upgrade: 'node_upgrade',
  restart: 'node_restart',
  runtime_check: 'runtime_check',
  sync_from_node: 'sync_from_node',
  sync_to_node: 'sync_to_node',
}

const LOCK_KEY_TO_ACTION: Record<PersistedActionKey, Exclude<LocationActionKey, 'inspect'>> = {
  node_deploy: 'deploy',
  node_upgrade: 'upgrade',
  node_restart: 'restart',
  runtime_check: 'runtime_check',
  sync_from_node: 'sync_from_node',
  sync_to_node: 'sync_to_node',
}

const ACTION_META: Record<LocationActionKey, { label: string; running_label: string; eta_seconds: number }> = {
  inspect: { label: 'Inspect State', running_label: 'Inspecting source state', eta_seconds: 12 },
  deploy: { label: 'Register Root', running_label: 'Registering root', eta_seconds: 45 },
  upgrade: { label: 'Normalize Root', running_label: 'Normalizing root', eta_seconds: 45 },
  restart: { label: 'Manager Status', running_label: 'Checking manager status', eta_seconds: 18 },
  runtime_check: { label: 'Runtime Snapshot', running_label: 'Refreshing runtime snapshot', eta_seconds: 28 },
  sync_from_node: { label: 'Sync From Node', running_label: 'Syncing from node', eta_seconds: 22 },
  sync_to_node: { label: 'Sync To Node', running_label: 'Syncing to node', eta_seconds: 22 },
}

function panelStorageKey(serviceId: string, key: string) {
  return `service-panel:${serviceId}:${key}`
}

function pendingSessionKey(actionKey: PersistedActionKey, locationId: string) {
  return `pending:${actionKey}:${locationId}`
}

function actionStartKey(locationId: string, action: LocationActionKey) {
  return `${locationId}:${action}`
}

function formatDurationLabel(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function getActionProgress(startedAt: string, etaSeconds: number, nowMs: number) {
  const startedMs = Number.isNaN(Date.parse(startedAt)) ? nowMs : Date.parse(startedAt)
  const elapsedSeconds = Math.max(0, Math.floor((nowMs - startedMs) / 1000))
  const remainingSeconds = Math.max(0, etaSeconds - elapsedSeconds)
  const overrunSeconds = Math.max(0, elapsedSeconds - etaSeconds)
  const percent = etaSeconds > 0 ? Math.min(100, Math.round((elapsedSeconds / etaSeconds) * 100)) : 0
  return { elapsedSeconds, remainingSeconds, overrunSeconds, percent }
}

function quoteShell(value: string) {
  return `'${value.replace(/'/g, `'\"'\"'`)}'`
}

function shellPrefix(host?: string, username?: string, port?: number) {
  if (!host) return ''
  const target = username ? `${username}@${host}` : host
  return port && port !== 22 ? `ssh -p ${port} ${target}` : `ssh ${target}`
}

function serverShellCommand(server?: ServerRecord, command?: string) {
  if (!command) return ''
  if (server?.connection_type === 'ssh' && server.host) {
    return `${shellPrefix(server.host, server.username, server.port)} ${quoteShell(command)}`
  }
  return command
}

function freshnessDisplayLabel(value?: string) {
  const state = value || 'Unverified'
  return state === 'Stale' ? 'Stale cache' : state
}

function freshnessSourceLabel(value?: string) {
  return value ? value.replace(/_/g, ' ') : 'Unverified'
}

function formatTimestampLabel(value?: string) {
  if (!value) return 'never'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function isTimestampAfter(left?: string, right?: string) {
  if (!left) return false
  if (!right) return true
  const leftMs = Date.parse(left)
  const rightMs = Date.parse(right)
  if (Number.isNaN(leftMs) || Number.isNaN(rightMs)) return false
  return leftMs > rightMs
}

function stripCodeFence(value?: string) {
  if (!value) return ''
  const trimmed = value.trim()
  const match = /^```[a-zA-Z0-9_-]*\n([\s\S]*?)\n```$/.exec(trimmed)
  return match ? match[1].trim() : trimmed
}

function isFrameworkOverheadDoc(path?: string) {
  const normalized = (path ?? '').trim().toLowerCase().replace(/\\/g, '/')
  if (!normalized) return true
  return (
    normalized.includes('/switchboard/local/') ||
    normalized.includes('/switchboard/evidence/') ||
    normalized.includes('/switchboard/core/') ||
    normalized.includes('/switchboard/runtime/') ||
    normalized.startsWith('switchboard/local/') ||
    normalized.startsWith('switchboard/evidence/') ||
    normalized.startsWith('switchboard/core/') ||
    normalized.startsWith('switchboard/runtime/')
  )
}

function isFrameworkMaintenanceTask(task?: TaskLedgerEntry) {
  if (!task) return false
  const title = (task.title ?? '').toLowerCase()
  const summary = (task.summary ?? '').toLowerCase()
  const tags = Array.isArray(task.tags) ? task.tags.map((tag: string) => tag.toLowerCase()) : []
  const changedPaths = Array.isArray(task.changed_paths) ? task.changed_paths : []
  const mentionsSwitchboard = title.includes('switchboard') || summary.includes('switchboard')
  const mentionsBootstrap = title.includes('bootstrap') || summary.includes('bootstrap')
  const frameworkOnlyPaths =
    changedPaths.length > 0 &&
    changedPaths.every((path: string) => path.startsWith('switchboard/') || path === 'README.md' || path === 'API.md' || path === 'CHANGELOG.md')
  return mentionsSwitchboard || (mentionsBootstrap && (tags.includes('handoff') || frameworkOnlyPaths))
}

export function ServiceDetailPage({ serviceId, runResult, offline, onBack, onDeleted, onOpenEnvironmentLab }: Props) {
  const [service, setService] = useState<Service | null>(null)
  const [runs, setRuns] = useState<RunRecord[]>([])
  const [scopeEntries, setScopeEntries] = useState<ScopeEntry[]>([])
  const [scopeDraft, setScopeDraft] = useState<ScopeEntry[]>([])
  const [editingScope, setEditingScope] = useState(false)
  const [savingScope, setSavingScope] = useState(false)
  const [scopeMessage, setScopeMessage] = useState<string | null>(null)
  const [newScopePath, setNewScopePath] = useState('')
  const [newScopeKind, setNewScopeKind] = useState<ScopeEntry['kind']>('doc')
  const [newScopePathType, setNewScopePathType] = useState<ScopeEntry['path_type']>('file')
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [editingRuntime, setEditingRuntime] = useState(false)
  const [runtimeDraft, setRuntimeDraft] = useState<ServiceLocationDraft[]>([])
  const [runtimeExecutionMode, setRuntimeExecutionMode] = useState<Service['execution_mode']>('networked')
  const [savingRuntime, setSavingRuntime] = useState(false)
  const [runtimeMessage, setRuntimeMessage] = useState<string | null>(null)
  const [managedDocsDraft, setManagedDocsDraft] = useState<ManagedDocConfig[]>([])
  const [editingManagedDocs, setEditingManagedDocs] = useState(false)
  const [savingManagedDocs, setSavingManagedDocs] = useState(false)
  const [managedDocsMessage, setManagedDocsMessage] = useState<string | null>(null)
  const [checkingRuntimeLocation, setCheckingRuntimeLocation] = useState<string | null>(null)
  const [syncingFromLocation, setSyncingFromLocation] = useState<string | null>(null)
  const [syncingToLocation, setSyncingToLocation] = useState<string | null>(null)
  const [confirmAction, setConfirmAction] = useState<ConfirmActionKey | null>(null)
  const [confirmLocationId, setConfirmLocationId] = useState<string | null>(null)
  const [confirmDetails, setConfirmDetails] = useState<ConfirmDetails | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [servers, setServers] = useState<ServerRecord[]>([])
  const [, setPendingActions] = useState<Record<string, boolean>>({})
  const [activeLocks, setActiveLocks] = useState<Record<string, ActionLock>>({})
  const [actionLockStatus, setActionLockStatus] = useState<'online' | 'offline'>('online')
  const [actionStartTimes, setActionStartTimes] = useState<Record<string, string>>({})
  const [panelOpen, setPanelOpen] = useState<Record<string, boolean>>({})
  const [locationPanels, setLocationPanels] = useState<Record<string, boolean>>({})
  const [nodeActionResults, setNodeActionResults] = useState<Record<string, NodeActionResult>>({})
  const [nodeActionLoading, setNodeActionLoading] = useState<Record<string, NodeActionKey | null>>({})
  const [locationActionEvents, setLocationActionEvents] = useState<Record<string, LocationActionEvent[]>>({})
  const [bundleHistoryMeta, setBundleHistoryMeta] = useState<{ count: number; latestCreatedAt: string }>({ count: 0, latestCreatedAt: '' })
  const [pullBundleRefreshKey, setPullBundleRefreshKey] = useState(0)
  const [projectEnvironments, setProjectEnvironments] = useState<ProjectEnvironmentView[]>([])
  const [nowMs, setNowMs] = useState(() => Date.now())
  const [docPreviewId, setDocPreviewId] = useState<string | null>(null)

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const next: Record<string, boolean> = {}
    for (const key of SERVICE_PANEL_KEYS) {
      const stored = sessionStorage.getItem(panelStorageKey(serviceId, key))
      next[key] = stored === null ? DEFAULT_OPEN_PANELS.includes(key) : stored === 'true'
    }
    setPanelOpen(next)
  }, [serviceId])

  useEffect(() => {
    if (offline) return
    getService(serviceId).then((res) => {
      if (!isApiError(res)) {
        setService(res)
        setRuntimeDraft(res.locations.map((location) => ({ ...location, runtime: { ...location.runtime } })))
        setRuntimeExecutionMode(res.execution_mode)
        setManagedDocsDraft(res.managed_docs.map((entry) => ({ ...entry })))
      }
    })
    getServiceScope(serviceId).then((res) => {
      if (!isApiError(res)) {
        setScopeEntries(res.scope_entries)
        setScopeDraft(res.scope_entries.map((entry) => ({ ...entry })))
      }
    })
  }, [serviceId, offline])

  useEffect(() => {
    if (offline || !service?.workspace_id) return
    getWorkspaceRuns(service.workspace_id).then((result) => {
      if (!isApiError(result)) setRuns(result)
    })
  }, [offline, service?.workspace_id])

  useEffect(() => {
    if (offline || !service?.workspace_id) return
    listProjects(service.workspace_id).then((result) => {
      if (!isApiError(result)) setProjectEnvironments(result.environments ?? [])
    })
  }, [offline, service?.workspace_id])

  useEffect(() => {
    if (offline) return
    listServers().then((result) => {
      if (!isApiError(result)) setServers(result)
    })
  }, [offline])

  useEffect(() => {
    void refreshBundleHistoryMeta()
  }, [offline, serviceId])

  useEffect(() => {
    if (offline) return
    let cancelled = false

    const refresh = async () => {
      const result = await getActionLocks(serviceId)
      if (cancelled) return
      if (isApiError(result)) {
        setActionLockStatus('offline')
        setActiveLocks({})
        setPendingActions({})
        for (const key of Object.keys(sessionStorage)) {
          if (key.startsWith('pending:')) sessionStorage.removeItem(key)
          if (key.startsWith(`service-panel:${serviceId}:`)) sessionStorage.removeItem(key)
        }
        return
      }
      setActionLockStatus('online')
      setActiveLocks(Object.fromEntries(result.locks.map((lock) => [lock.action_key, lock])))
    }

    void refresh()
    const timer = window.setInterval(() => {
      void refresh()
    }, 5000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [offline, serviceId])

  useEffect(() => {
    if (!service) {
      setPendingActions({})
      return
    }
    const locationIds = new Set(service.locations.map((location) => location.location_id))
    const nextPending: Record<string, boolean> = {}
    for (const key of Object.keys(sessionStorage)) {
      if (!key.startsWith('pending:')) continue
      const match = /^pending:([^:]+):(.+)$/.exec(key)
      if (!match) continue
      const [, actionKey, locationId] = match
      if (!locationIds.has(locationId)) continue
      if (activeLocks[actionKey]) {
        nextPending[key] = true
      } else {
        sessionStorage.removeItem(key)
        for (const panelKey of SERVICE_PANEL_KEYS) {
          sessionStorage.removeItem(panelStorageKey(serviceId, panelKey))
        }
      }
    }
    setPendingActions(nextPending)
  }, [activeLocks, service])

  const docs = runResult?.docs_files ?? []
  const logs = runResult?.logs_files ?? []
  const configuredRepoPaths = useMemo(() => {
    const paths = new Set<string>()
    for (const path of service?.repo_paths ?? []) paths.add(path)
    for (const path of service?.allowed_git_pull_paths ?? []) paths.add(path)
    for (const entry of scopeEntries) {
      if (entry.enabled && entry.kind === 'repo') paths.add(entry.path)
    }
    return [...paths]
  }, [scopeEntries, service?.allowed_git_pull_paths, service?.repo_paths])
  const repos = useMemo<RepoSummaryRecord[]>(() => {
    const collected = runResult?.repo_summaries ?? []
    if (collected.length > 0) return collected
    return configuredRepoPaths.map((path) => ({
      path,
      branch: '',
      commit: '',
      dirty: false,
      status: 'unverified',
      is_allowlisted: Boolean(service?.allowed_git_pull_paths?.includes(path)),
      push_mode: 'blocked',
    }))
  }, [configuredRepoPaths, runResult?.repo_summaries, service?.allowed_git_pull_paths])

  async function handleDelete() {
    if (!service || deleting) return
    setDeleteError(null)
    setDeleting(true)
    const result = await deleteService(serviceId)
    setDeleting(false)
    setDeleteConfirmOpen(false)
    if (isApiError(result)) {
      setDeleteError(result.message)
      return
    }
    onDeleted(serviceId, result.workspace_id)
  }

  function handleServiceUpdated(updated: Service) {
    setService(updated)
    setScopeEntries(updated.scope_entries)
    setScopeDraft(updated.scope_entries.map((entry) => ({ ...entry })))
    setRuntimeDraft(updated.locations.map((location) => ({ ...location, runtime: { ...location.runtime } })))
    setRuntimeExecutionMode(updated.execution_mode)
    setManagedDocsDraft(updated.managed_docs.map((entry) => ({ ...entry })))
  }

  async function refreshBundleHistoryMeta() {
    if (offline) return
    const result = await listPullBundles(serviceId)
    if (isApiError(result)) return
    setBundleHistoryMeta({
      count: result.length,
      latestCreatedAt: result[0]?.created_at ?? '',
    })
  }

  async function refreshAfterNodeSync(fallbackService: Service) {
    const [serviceSettled, scopeSettled, nodeViewerSettled, bundleSettled] = await Promise.allSettled([
      getService(serviceId),
      getServiceScope(serviceId),
      getNodeViewer(serviceId),
      listPullBundles(serviceId),
    ])
    const serviceResult = serviceSettled.status === 'fulfilled' ? serviceSettled.value : null
    const scopeResult = scopeSettled.status === 'fulfilled' ? scopeSettled.value : null
    const nodeViewerResult = nodeViewerSettled.status === 'fulfilled' ? nodeViewerSettled.value : null
    const bundleResult = bundleSettled.status === 'fulfilled' ? bundleSettled.value : null
    let nextService = fallbackService
    if (serviceResult && !isApiError(serviceResult)) {
      nextService = serviceResult
    }
    if (nodeViewerResult && !isApiError(nodeViewerResult)) {
      nextService = { ...nextService, node_viewer: nodeViewerResult.locations }
    }
    handleServiceUpdated(nextService)
    if (scopeResult && !isApiError(scopeResult)) {
      setScopeEntries(scopeResult.scope_entries)
      setScopeDraft(scopeResult.scope_entries.map((entry) => ({ ...entry })))
    }
    if (bundleResult && !isApiError(bundleResult)) {
      setBundleHistoryMeta({
        count: bundleResult.length,
        latestCreatedAt: bundleResult[0]?.created_at ?? '',
      })
    }
    setPullBundleRefreshKey((current) => current + 1)
  }

  const runtimeChecksByLocation = useMemo(() => {
    const map = new Map<string, RuntimeCheckResult>()
    for (const entry of service?.runtime_checks ?? []) {
      if (!map.has(entry.location_id)) map.set(entry.location_id, entry)
    }
    for (const entry of runResult?.runtime_checks ?? []) {
      if (!map.has(entry.location_id)) map.set(entry.location_id, entry)
    }
    return map
  }, [runResult?.runtime_checks, service?.runtime_checks])

  const nodeSyncByLocation = useMemo(() => {
    const map = new Map<string, NonNullable<Service['node_sync']>[number]>()
    for (const entry of service?.node_sync ?? []) {
      if (!map.has(entry.location_id)) map.set(entry.location_id, entry)
    }
    return map
  }, [service?.node_sync])

  const latestNodeDocIndex = useMemo(
    () => (service?.node_sync ?? []).find((entry) => entry.doc_index)?.doc_index,
    [service?.node_sync],
  )
  const nodeViewerByLocation = useMemo(() => {
    const map = new Map<string, NonNullable<Service['node_viewer']>[number]>()
    for (const entry of service?.node_viewer ?? []) {
      map.set(entry.location_id, entry)
    }
    return map
  }, [service?.node_viewer])

  const environmentMatchesByLocation = useMemo(() => {
    const map = new Map<string, ProjectEnvironmentView[]>()
    for (const environment of projectEnvironments) {
      for (const deployment of environment.deployments ?? []) {
        if (deployment.service_id !== service?.service_id) continue
        const key = deployment.location_id || '__service__'
        const current = map.get(key) ?? []
        current.push(environment)
        map.set(key, current)
      }
    }
    return map
  }, [projectEnvironments, service?.service_id])

  const hasNodeScope = useMemo(
    () =>
      (service?.scope_entries ?? []).some((entry) => entry.enabled && entry.path.endsWith('switchboard/node.manifest.json')),
    [service?.scope_entries],
  )

  const scopeSummary = useMemo(() => {
    const counts = { repo: 0, code: 0, doc: 0, log: 0, exclude: 0 }
    for (const entry of scopeEntries) {
      if (!entry.enabled) continue
      counts[entry.kind] += 1
    }
    return counts
  }, [scopeEntries])

  const latestTask = service?.task_ledger?.[0]
  const featuredTask = useMemo(
    () => (service?.task_ledger ?? []).find((entry) => !isFrameworkMaintenanceTask(entry)) ?? service?.task_ledger?.[0],
    [service?.task_ledger],
  )
  const latestTaskNotes = useMemo(() => {
    const notes = featuredTask?.notes
    return Array.isArray(notes) ? notes.filter(Boolean) : []
  }, [featuredTask?.notes])
  const latestTaskDependencies = featuredTask?.dependencies ?? []
  const latestTaskCrossDependencies = featuredTask?.cross_dependencies ?? []
  const latestTaskDiagram = useMemo(() => stripCodeFence(featuredTask?.diagram), [featuredTask?.diagram])

  const quickDocPreviews = useMemo(
    () =>
      [
        { id: 'readme', label: 'README', content: stripCodeFence(featuredTask?.readme) },
        { id: 'api', label: 'API', content: stripCodeFence(featuredTask?.api) },
        { id: 'changelog', label: 'CHANGELOG', content: stripCodeFence(featuredTask?.changelog) },
      ].filter((entry) => entry.content),
    [featuredTask?.api, featuredTask?.changelog, featuredTask?.readme],
  )

  const projectDocEntries = useMemo(() => {
    const seen = new Set<string>()
    const entries: Array<{ id: string; label: string; path: string; frameworkWritesEnabled: boolean; generatedAt?: string | null }> = []
    for (const entry of latestNodeDocIndex?.docs ?? []) {
      if (isFrameworkOverheadDoc(entry.path)) continue
      const key = `${entry.doc_id}:${entry.path}`
      if (seen.has(key)) continue
      seen.add(key)
      entries.push({
        id: entry.doc_id,
        label: entry.label ?? entry.doc_id.toUpperCase(),
        path: entry.path,
        frameworkWritesEnabled: Boolean(entry.enabled),
        generatedAt: entry.generated_at,
      })
    }
    for (const entry of service?.managed_docs ?? []) {
      if (isFrameworkOverheadDoc(entry.path)) continue
      const key = `${entry.doc_id}:${entry.path}`
      if (seen.has(key)) continue
      seen.add(key)
      entries.push({
        id: entry.doc_id,
        label: entry.doc_id.toUpperCase(),
        path: entry.path,
        frameworkWritesEnabled: Boolean(entry.enabled),
        generatedAt: entry.last_generated_at,
      })
    }
    return entries
  }, [latestNodeDocIndex?.docs, service?.managed_docs])

  const quickPreviewById = useMemo(
    () => Object.fromEntries(quickDocPreviews.map((entry) => [entry.id, entry.content])),
    [quickDocPreviews],
  )

  const runtimeAttentionCount = useMemo(
    () =>
      (service?.locations ?? []).filter((location) => {
        const nodeViewer = nodeViewerByLocation.get(location.location_id)
        const staleOrBlocked = Boolean(
          nodeViewer?.freshness_state &&
          nodeViewer.freshness_state !== 'Fresh' &&
          nodeViewer.freshness_state !== 'Unverified',
        )
        return Boolean(nodeViewer?.needs_install || nodeViewer?.needs_upgrade || nodeViewer?.needs_bootstrap || staleOrBlocked || nodeViewer?.refresh_action)
      }).length,
    [nodeViewerByLocation, service?.locations],
  )

  function togglePanel(key: ServicePanelKey) {
    setPanelOpen((current) => {
      const next = !current[key]
      sessionStorage.setItem(panelStorageKey(serviceId, key), String(next))
      return { ...current, [key]: next }
    })
  }

  function toggleLocationPanel(locationId: string) {
    setLocationPanels((current) => ({ ...current, [locationId]: !current[locationId] }))
  }

  function updateRuntimeDraftField(
    locationId: string,
    field: keyof ServiceLocationDraft['runtime'],
    value: string,
  ) {
    setRuntimeDraft((current) =>
      current.map((location) => {
        if (location.location_id !== locationId) return location
        if (field === 'expected_ports') {
          return {
            ...location,
            runtime: {
              ...location.runtime,
              expected_ports: parsePorts(value),
            },
          }
        }
        if (field === 'monitoring_mode') {
          return {
            ...location,
            runtime: {
              ...location.runtime,
              monitoring_mode: value as ServiceLocationDraft['runtime']['monitoring_mode'],
            },
          }
        }
        return {
          ...location,
          runtime: {
            ...location.runtime,
            [field]: value,
          },
        }
      }),
    )
  }

  async function handleSaveRuntime() {
    if (!service) return
    setSavingRuntime(true)
    setRuntimeMessage(null)
    const result = await updateService(service.service_id, {
      execution_mode: runtimeExecutionMode,
      locations: runtimeDraft,
    } as Partial<Service>)
    setSavingRuntime(false)
    if (isApiError(result)) {
      setRuntimeMessage(result.message)
      return
    }
    handleServiceUpdated(result)
    setEditingRuntime(false)
    setRuntimeMessage('Runtime config updated.')
  }

  function setNodeViewerEntry(entry: NonNullable<Service['node_viewer']>[number]) {
    setService((current) =>
      current
        ? {
            ...current,
            node_viewer: [entry, ...(current.node_viewer ?? []).filter((candidate) => candidate.location_id !== entry.location_id)],
          }
        : current,
    )
  }

  function recordLocationAction(
    locationId: string,
    event: LocationActionEvent,
  ) {
    setLocationActionEvents((current) => ({
      ...current,
      [locationId]: [event, ...(current[locationId] ?? [])].slice(0, 6),
    }))
  }

  async function refreshActionLocksSnapshot() {
    if (offline) return
    const result = await getActionLocks(serviceId)
    if (isApiError(result)) {
      setActionLockStatus('offline')
      setActiveLocks({})
      setPendingActions({})
      for (const key of Object.keys(sessionStorage)) {
        if (key.startsWith('pending:')) sessionStorage.removeItem(key)
        if (key.startsWith(`service-panel:${serviceId}:`)) sessionStorage.removeItem(key)
      }
      return
    }
    setActionLockStatus('online')
    setActiveLocks(Object.fromEntries(result.locks.map((lock) => [lock.action_key, lock])))
  }

  function setActionStartedAt(locationId: string, action: LocationActionKey, startedAt: string) {
    setActionStartTimes((current) => ({ ...current, [actionStartKey(locationId, action)]: startedAt }))
  }

  function clearActionStartedAt(locationId: string, action: LocationActionKey) {
    setActionStartTimes((current) => {
      const next = { ...current }
      delete next[actionStartKey(locationId, action)]
      return next
    })
  }

  function markPendingAction(actionKey: PersistedActionKey, locationId: string, startedAt: string) {
    const sessionKey = pendingSessionKey(actionKey, locationId)
    sessionStorage.setItem(sessionKey, 'true')
    setPendingActions((current) => ({ ...current, [sessionKey]: true }))
    setActionStartedAt(locationId, LOCK_KEY_TO_ACTION[actionKey], startedAt)
  }

  function clearPendingAction(actionKey: PersistedActionKey, locationId: string) {
    const sessionKey = pendingSessionKey(actionKey, locationId)
    sessionStorage.removeItem(sessionKey)
    setPendingActions((current) => {
      const next = { ...current }
      delete next[sessionKey]
      return next
    })
    clearActionStartedAt(locationId, LOCK_KEY_TO_ACTION[actionKey])
  }

  async function handleNodeAction(action: 'inspect' | 'deploy' | 'upgrade' | 'restart', locationId: string) {
    if (!service) return
    const startedAt = new Date().toISOString()
    const persistedActionKey = action === 'inspect' ? null : ACTION_LOCK_KEY[action]
    setNodeActionLoading((current) => ({ ...current, [locationId]: action }))
    setActionStartedAt(locationId, action, startedAt)
    if (persistedActionKey) markPendingAction(persistedActionKey, locationId, startedAt)
    recordLocationAction(locationId, {
      action,
      status: 'running',
      message:
        action === 'inspect'
          ? 'Inspecting node state and runtime.'
          : action === 'deploy'
            ? 'Registering this root with the Switchboard manager.'
            : action === 'upgrade'
            ? 'Refreshing this root under the Switchboard manager.'
            : 'Checking the Switchboard manager runtime.',
      timestamp: startedAt,
      started_at: startedAt,
    })
    try {
      const result =
        action === 'inspect'
          ? await inspectNode(service.service_id, locationId)
          : action === 'deploy'
            ? await deployNode(service.service_id, locationId)
            : action === 'upgrade'
              ? await upgradeNode(service.service_id, locationId)
              : await restartNode(service.service_id, locationId)
      if (isApiError(result)) {
        setRuntimeMessage(result.message)
        recordLocationAction(locationId, {
          action,
          status: 'error',
          message: result.message,
          timestamp: new Date().toISOString(),
          started_at: startedAt,
          duration_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)),
        })
        return
      }
      setNodeViewerEntry(result.node)
      setNodeActionResults((current) => ({ ...current, [locationId]: result }))
      const successMessage =
        result.message ||
        (action === 'inspect'
          ? 'Node viewer refreshed.'
          : action === 'deploy'
            ? 'Manager root registered.'
            : action === 'upgrade'
              ? 'Manager root refreshed.'
              : result.node.runtime_status === 'manager_running'
                ? 'Manager runtime is running.'
                : result.node.runtime_status === 'running'
                ? 'Node runtime started.'
                : 'Node restart command completed.')
      setRuntimeMessage(successMessage)
      recordLocationAction(locationId, {
        action,
        status: 'ok',
        message: successMessage,
        timestamp: new Date().toISOString(),
        started_at: startedAt,
        duration_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)),
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Node action failed unexpectedly.'
      setRuntimeMessage(message)
      recordLocationAction(locationId, {
        action,
        status: 'error',
        message,
        timestamp: new Date().toISOString(),
        started_at: startedAt,
        duration_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)),
      })
    } finally {
      setNodeActionLoading((current) => ({ ...current, [locationId]: null }))
      clearActionStartedAt(locationId, action)
      if (persistedActionKey) clearPendingAction(persistedActionKey, locationId)
      void refreshActionLocksSnapshot()
    }
  }

  function handleCancelRuntimeEdit() {
    setRuntimeDraft(service?.locations.map((location) => ({ ...location, runtime: { ...location.runtime } })) ?? [])
    setRuntimeExecutionMode(service?.execution_mode ?? 'networked')
    setEditingRuntime(false)
    setRuntimeMessage(null)
  }

  async function handleSaveManagedDocs() {
    if (!service) return
    setSavingManagedDocs(true)
    setManagedDocsMessage(null)
    const result = await updateService(service.service_id, {
      managed_docs: managedDocsDraft,
    } as Partial<Service>)
    setSavingManagedDocs(false)
    if (isApiError(result)) {
      setManagedDocsMessage(result.message)
      return
    }
    handleServiceUpdated(result)
    setEditingManagedDocs(false)
    setManagedDocsMessage('Managed docs updated.')
  }

  function handleCancelManagedDocsEdit() {
    setManagedDocsDraft(service?.managed_docs.map((entry) => ({ ...entry })) ?? [])
    setEditingManagedDocs(false)
    setManagedDocsMessage(null)
  }

  async function handleRuntimeCheck(locationId: string) {
    const startedAt = actionStartTimes[actionStartKey(locationId, 'runtime_check')] ?? new Date().toISOString()
    setCheckingRuntimeLocation(locationId)
    setRuntimeMessage(null)
    const result = await runRuntimeCheck(serviceId, { location_id: locationId })
    setCheckingRuntimeLocation(null)
    if (isApiError(result)) {
      setRuntimeMessage(result.message)
      recordLocationAction(locationId, {
        action: 'runtime_check',
        status: 'error',
        message: result.message,
        timestamp: new Date().toISOString(),
        started_at: startedAt,
        duration_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)),
      })
      return
    }
    setService((current) =>
      current
        ? {
            ...current,
            runtime_checks: [
              result,
              ...(current.runtime_checks ?? []).filter((entry) => entry.location_id !== result.location_id),
            ],
          }
        : current,
    )
    setRuntimeMessage('Runtime check completed.')
    recordLocationAction(locationId, {
      action: 'runtime_check',
      status: 'ok',
      message: 'Runtime snapshot refreshed.',
      timestamp: new Date().toISOString(),
      started_at: startedAt,
      duration_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)),
    })
  }

  async function handleSyncFromNode(locationId: string) {
    const startedAt = actionStartTimes[actionStartKey(locationId, 'sync_from_node')] ?? new Date().toISOString()
    setSyncingFromLocation(locationId)
    setRuntimeMessage(null)
    const result = await syncFromNode(serviceId, { location_id: locationId })
    setSyncingFromLocation(null)
    if (isApiError(result)) {
      setRuntimeMessage(result.message)
      recordLocationAction(locationId, {
        action: 'sync_from_node',
        status: 'error',
        message: result.message,
        timestamp: new Date().toISOString(),
        started_at: startedAt,
        duration_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)),
      })
      return
    }
    const syncedService = {
      ...result.service,
      node_sync: [result.sync, ...(result.service.node_sync ?? []).filter((entry) => entry.location_id !== result.sync.location_id)],
    }
    handleServiceUpdated(syncedService)
    await refreshAfterNodeSync(syncedService)
    setRuntimeMessage('Synced from node. Service, scope, node viewer, and pull-bundle state refreshed.')
    recordLocationAction(locationId, {
      action: 'sync_from_node',
      status: 'ok',
      message: 'Imported node scope and task ledger.',
      timestamp: new Date().toISOString(),
      started_at: startedAt,
      duration_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)),
    })
  }

  async function handleSyncToNode(locationId: string) {
    const startedAt = actionStartTimes[actionStartKey(locationId, 'sync_to_node')] ?? new Date().toISOString()
    setSyncingToLocation(locationId)
    setRuntimeMessage(null)
    const result = await syncToNode(serviceId, { location_id: locationId })
    setSyncingToLocation(null)
    if (isApiError(result)) {
      setRuntimeMessage(result.message)
      recordLocationAction(locationId, {
        action: 'sync_to_node',
        status: 'error',
        message: result.message,
        timestamp: new Date().toISOString(),
        started_at: startedAt,
        duration_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)),
      })
      return
    }
    setService((current) =>
      current
        ? {
            ...current,
            node_sync: [result.sync, ...(current.node_sync ?? []).filter((entry) => entry.location_id !== result.sync.location_id)],
          }
        : current,
    )
    setRuntimeMessage(result.node_manifest_path ? `Synced to node at ${result.node_manifest_path}.` : 'Synced to node.')
    recordLocationAction(locationId, {
      action: 'sync_to_node',
      status: 'ok',
      message: result.node_manifest_path ? `Synced to node at ${result.node_manifest_path}.` : 'Synced to node.',
      timestamp: new Date().toISOString(),
      started_at: startedAt,
      duration_seconds: Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)),
    })
  }

  function initiateAction(actionKey: ConfirmActionKey, locationId: string, details?: ConfirmDetails) {
    setConfirmAction(actionKey)
    setConfirmLocationId(locationId)
    setConfirmDetails(details ?? null)
    setConfirmOpen(true)
  }

  async function handleConfirmAction() {
    if (!confirmAction || !confirmLocationId) return
    const locationId = confirmLocationId
    setConfirmOpen(false)
    setConfirmDetails(null)

    if (confirmAction === 'node_inspect') {
      await handleNodeAction('inspect', locationId)
      setConfirmAction(null)
      setConfirmLocationId(null)
      return
    }
    if (confirmAction === 'node_deploy') {
      await handleNodeAction('deploy', locationId)
      setConfirmAction(null)
      setConfirmLocationId(null)
      return
    }
    if (confirmAction === 'node_upgrade') {
      await handleNodeAction('upgrade', locationId)
      setConfirmAction(null)
      setConfirmLocationId(null)
      return
    }
    if (confirmAction === 'node_restart') {
      await handleNodeAction('restart', locationId)
      setConfirmAction(null)
      setConfirmLocationId(null)
      return
    }

    const actionKey = confirmAction as Extract<LocationActionKey, 'runtime_check' | 'sync_from_node' | 'sync_to_node'>
    const lockKey = ACTION_LOCK_KEY[actionKey]
    const startedAt = new Date().toISOString()
    const requiresClientLock = actionKey === 'runtime_check'

    markPendingAction(lockKey, locationId, startedAt)
    recordLocationAction(locationId, {
      action: actionKey,
      status: 'running',
      message: ACTION_META[actionKey].running_label,
      timestamp: startedAt,
      started_at: startedAt,
    })

    if (requiresClientLock) {
      const lockRes = await acquireActionLock(serviceId, actionKey)
      if (isApiError(lockRes) || lockRes.status !== 'ok') {
        setRuntimeMessage((lockRes as any)?.message || 'Action is already in progress.')
        clearPendingAction(lockKey, locationId)
        void refreshActionLocksSnapshot()
        setConfirmAction(null)
        setConfirmLocationId(null)
        return
      }
    }

    try {
      if (actionKey === 'runtime_check') {
        await handleRuntimeCheck(locationId)
      } else if (actionKey === 'sync_from_node') {
        await handleSyncFromNode(locationId)
      } else if (actionKey === 'sync_to_node') {
        await handleSyncToNode(locationId)
      }
    } finally {
      if (requiresClientLock) {
        await releaseActionLock(serviceId, actionKey)
      }
      clearPendingAction(lockKey, locationId)
      void refreshActionLocksSnapshot()
      setConfirmAction(null)
      setConfirmLocationId(null)
    }
  }

  function addScopeEntry() {
    const trimmed = newScopePath.trim()
    if (!trimmed) return
    setScopeDraft((current) => [
      ...current,
      {
        kind: newScopeKind,
        path: trimmed,
        path_type: newScopePathType,
        source: 'user_added',
        enabled: true,
      },
    ])
    setNewScopePath('')
  }

  async function handleSaveScope() {
    if (!service) return
    setSavingScope(true)
    setScopeMessage(null)
    const result = await updateService(service.service_id, {
      scope_entries: scopeDraft,
    } as Partial<Service>)
    setSavingScope(false)
    if (isApiError(result)) {
      setScopeMessage(result.message)
      return
    }
    handleServiceUpdated(result)
    setEditingScope(false)
    setScopeMessage('Scope updated.')
  }

  function handleCancelScopeEdit() {
    setScopeDraft(scopeEntries.map((entry) => ({ ...entry })))
    setEditingScope(false)
    setScopeMessage(null)
  }

  return (
    <div>
      {/* Back + header */}
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
          <div className="flex items-center gap-3">
            <div>
              <h2 className="text-xl font-semibold text-white">
                {service?.display_name ?? serviceId}
              </h2>
              <div className="mt-0.5 flex items-center gap-2">
                <span className="text-xs text-gray-500">{serviceId}</span>
                {runResult && <StatusBadge status={runResult.status} />}
                {hasNodeScope && (
                  <span className="rounded-full border border-cyan-900 bg-cyan-950/60 px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-cyan-300">
                    Node Linked
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {service && (
            <div className="hidden md:flex items-center gap-2">
              <InfoDropdown
                label="Health Check Commands"
                title="Location Health Checks"
                lines={
                  service.locations.map(
                    (loc) => `[${loc.location_id}]: ${loc.runtime?.healthcheck_command || 'None'}`
                  ) || ['No locations configured']
                }
              />
              <InfoDropdown
                label="Project Context"
                title="Latest Project Context"
                lines={[
                  featuredTask?.title ? `Featured entry: ${featuredTask.title}` : 'No project task entry imported yet.',
                  featuredTask?.summary ? featuredTask.summary : '',
                  service.notes ? `Service note: ${service.notes}` : '',
                  ...(latestTaskCrossDependencies.slice(0, 3).map(
                    (dep) => `Cross dependency: ${dep.name}${dep.port ? `:${dep.port}` : ''} ${dep.notes ? `| ${dep.notes}` : ''}`,
                  )),
                ]}
              />
            </div>
          )}
          <button
            type="button"
            onClick={() => setDeleteConfirmOpen(true)}
            disabled={offline || deleting || !service}
            className="inline-flex items-center gap-2 rounded-lg border border-red-900 bg-red-950/70 px-3 py-2 text-sm font-medium text-red-200 transition-colors hover:border-red-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            {deleting ? 'Deleting…' : 'Delete Service'}
          </button>
        </div>
      </div>

      <div className="mb-6 flex md:hidden items-center gap-2 flex-wrap">
        {service && (
          <>
            <InfoDropdown
              label="Health Checks"
              title="Location Health Checks"
              lines={
                service.locations.map(
                  (loc) => `[${loc.location_id}]: ${loc.runtime?.healthcheck_command || 'None'}`
                ) || ['No locations configured']
              }
            />
            <InfoDropdown
              label="Project Context"
              title="Latest Project Context"
              lines={[
                featuredTask?.title ? `Featured entry: ${featuredTask.title}` : 'No project task entry imported yet.',
                featuredTask?.summary ? featuredTask.summary : '',
                service.notes ? `Service note: ${service.notes}` : '',
                ...(latestTaskCrossDependencies.slice(0, 3).map(
                  (dep) => `Cross dependency: ${dep.name}${dep.port ? `:${dep.port}` : ''} ${dep.notes ? `| ${dep.notes}` : ''}`,
                )),
              ]}
            />
          </>
        )}
      </div>

      {service && (
        <AccordionSection
          title="Port Health"
          icon={<Server className="h-4 w-4 text-cyan-400" />}
          open={Boolean(panelOpen.port_health)}
          onToggle={() => togglePanel('port_health')}
          summary={`Control Center :${CONTROL_CENTER_PORT} · manager target :${DEFAULT_MANAGER_PORT} · dev UI :${DEV_UI_PORT}`}
          className="border-cyan-900/40 bg-cyan-950/10"
        >
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-cyan-300">
                Port Health
              </div>
              <div className="mt-1 text-sm text-gray-300">
                Control Center <span className="font-mono text-cyan-200">:{CONTROL_CENTER_PORT}</span> pulls from the machine manager node <span className="font-mono text-cyan-200">:{DEFAULT_MANAGER_PORT}</span>. 8009 only proves the Control Center API; manager truth needs 8020. Product runtime ports stay separate.
              </div>
            </div>
            <div className="rounded-full border border-gray-800 bg-gray-950 px-3 py-1 text-xs text-gray-300">
              Dev UI <span className="font-mono text-cyan-200">:{DEV_UI_PORT}</span> is only this local frontend.
            </div>
          </div>

          <div className="mt-4 grid gap-3">
            <div className="rounded-xl border border-gray-800 bg-gray-950 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Control Center API</div>
                  <div className="mt-1 font-mono text-sm text-white">127.0.0.1:{CONTROL_CENTER_PORT}</div>
                </div>
                <StatusBadge status={offline ? 'unreachable' : 'ok'} />
              </div>
            </div>

            {service.locations.map((location) => {
              const latestRuntime = runtimeChecksByLocation.get(location.location_id)
              const nodeViewer = nodeViewerByLocation.get(location.location_id)
              const serverMeta = servers.find((server) => server.server_id === location.server_id)
              const managerPort = nodeViewer?.target_manager_port || DEFAULT_MANAGER_PORT
              const managerFreshness = nodeViewer?.freshness_state || 'Unverified'
              const managerFreshnessLabel = freshnessDisplayLabel(managerFreshness)
              const managerUnreachable = managerFreshness === 'Manager unreachable'
              const managerTruthSource = freshnessSourceLabel(nodeViewer?.freshness_source)
              const managerHealthCheckedAt = nodeViewer?.manager_health_checked_at || ''
              const managerLivePort = nodeViewer?.manager_health_runtime_port
              const managerLive = nodeViewer?.manager_health_status === 'ok' && managerLivePort === DEFAULT_MANAGER_PORT
              const managerManifestPort = nodeViewer?.manager_manifest_runtime_port
              const managerManifestUpdatedAt = nodeViewer?.manifest_updated_at || nodeViewer?.truth_as_of || ''
              const managerPortLabel =
                managerLive
                  ? `live :${managerLivePort}`
                  : managerPort === DEFAULT_MANAGER_PORT
                  ? `:${DEFAULT_MANAGER_PORT}`
                  : `cached :${managerPort} / target :${DEFAULT_MANAGER_PORT}`
              const configuredPorts = location.runtime.expected_ports ?? []
              const detectedPorts = new Set((latestRuntime?.detected_ports ?? []).map((port) => port.port))
              const missingPorts = new Set(latestRuntime?.missing_ports ?? [])
              const portCheckDetails: ConfirmDetails = {
                preflight: [
                  serverMeta?.vpn_required ? 'VPN is required for this host; a timeout means VPN/network blocked, not success.' : 'Server route should already be reachable.',
                  'This checks listeners and optional health output only. It does not start, stop, deploy, sync, or write files.',
                  'Control Center, manager node, dev UI, and product runtime ports are reported as separate roles.',
                ],
                commandPreview: [
                  `POST /services/${serviceId}/runtime/check {"location_id":"${location.location_id}"}`,
                  serverShellCommand(serverMeta, `ss -ltnp 2>/dev/null || lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null`),
                  location.runtime.healthcheck_command
                    ? serverShellCommand(serverMeta, location.runtime.healthcheck_command)
                    : 'Health check skipped because no command is configured.',
                ].filter(Boolean),
                followUp: [
                  'If the manager port is stale or stopped, inspect the node/manager state before trusting sync or pull bundles.',
                  'If product runtime ports are missing, fix the service runtime outside the Switchboard manager port.',
                ],
                confirmLabel: 'Check Ports',
              }
              const portRole = (port: number) => {
                if (port === CONTROL_CENTER_PORT) return 'control center'
                if (port === DEFAULT_MANAGER_PORT) return 'manager node'
                if (port === DEV_UI_PORT) return 'dev UI'
                return 'product runtime'
              }
              return (
                <div
                  key={location.location_id}
                  className={`rounded-xl border p-3 ${
                    managerUnreachable
                      ? 'border-amber-500/40 bg-amber-950/20'
                      : managerFreshness && managerFreshness !== 'Fresh'
                        ? 'border-amber-800/50 bg-gray-950'
                        : 'border-gray-800 bg-gray-950'
                  }`}
                >
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <div className="text-xs uppercase tracking-[0.16em] text-gray-500">{location.location_id}</div>
                      <div className="mt-1 text-sm text-white">
                        Manager node <span className="font-mono text-cyan-200">{managerPortLabel}</span>
                        <span className="text-gray-500"> · </span>
                        <span className={managerUnreachable ? 'text-amber-200' : 'text-gray-300'}>
                          {managerUnreachable ? 'Manager unreachable' : managerLive ? 'Manager live on 8020' : nodeViewer?.runtime_status?.replace('_', ' ') || 'not inspected'}
                        </span>
                      </div>
                      <div className="mt-1 font-mono text-xs text-gray-500 break-all">{location.server_id} · {location.root}</div>
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                        <span className={`rounded-full border px-2 py-1 ${
                          managerUnreachable
                            ? 'border-amber-500/40 bg-amber-500/10 text-amber-200'
                            : managerFreshness === 'Fresh'
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                              : 'border-gray-800 bg-gray-900 text-gray-300'
                        }`}>
                          {managerFreshnessLabel}
                        </span>
                        {nodeViewer?.legacy_runtime_port_label && (
                          <span className="rounded-full border border-amber-700/40 bg-amber-950/20 px-2 py-1 text-amber-200">
                            {nodeViewer.legacy_runtime_port_label}
                          </span>
                        )}
                        {managerManifestPort && managerManifestPort !== DEFAULT_MANAGER_PORT && (
                          <span className="rounded-full border border-amber-700/40 bg-amber-950/20 px-2 py-1 text-amber-200">
                            Manifest runtime port: {managerManifestPort}
                          </span>
                        )}
                        {(nodeViewer?.stale_reason || nodeViewer?.refresh_action) && (
                          <span className="rounded-full border border-gray-800 bg-gray-900 px-2 py-1 text-gray-400">
                            {nodeViewer.refresh_action || 'Inspect Node'}{nodeViewer.stale_reason ? ` · ${nodeViewer.stale_reason}` : ''}
                          </span>
                        )}
                        <span className="rounded-full border border-gray-800 bg-gray-900 px-2 py-1 text-gray-400">
                          Truth source: {managerTruthSource}
                        </span>
                        <span className="rounded-full border border-gray-800 bg-gray-900 px-2 py-1 text-gray-400">
                          Manager health checked: {formatTimestampLabel(managerHealthCheckedAt)}
                        </span>
                        <span className="rounded-full border border-gray-800 bg-gray-900 px-2 py-1 text-gray-400">
                          Manifest last updated: {formatTimestampLabel(managerManifestUpdatedAt)}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {configuredPorts.length === 0 ? (
                          <span className="rounded-full border border-gray-800 bg-gray-900 px-2 py-1 text-[11px] text-gray-500">
                            No product runtime ports configured
                          </span>
                        ) : (
                          configuredPorts.map((port) => {
                            const detected = detectedPorts.has(port)
                            const missing = missingPorts.has(port)
                            return (
                              <span
                                key={`${location.location_id}:${port}`}
                                className={`rounded-full border px-2 py-1 text-[11px] ${
                                  detected
                                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                                    : missing
                                      ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                                      : 'border-gray-800 bg-gray-900 text-gray-300'
                                }`}
                              >
                                <span className="font-mono">:{port}</span> {portRole(port)}
                              </span>
                            )
                          })
                        )}
                      </div>
                      <div className="mt-2 text-xs text-gray-500">
                        Last check: {latestRuntime ? `${latestRuntime.status} at ${new Date(latestRuntime.checked_at).toLocaleString()}` : 'not captured yet'}
                        {latestRuntime?.freshness_state && latestRuntime.freshness_state !== 'Fresh' ? ` · ${latestRuntime.freshness_state}` : ''}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => initiateAction('runtime_check', location.location_id, portCheckDetails)}
                      disabled={offline || checkingRuntimeLocation === location.location_id || Boolean(activeLocks.runtime_check)}
                      className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-100 transition-colors hover:border-cyan-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${checkingRuntimeLocation === location.location_id || activeLocks.runtime_check ? 'animate-spin' : ''}`} />
                      {checkingRuntimeLocation === location.location_id || activeLocks.runtime_check ? 'Checking...' : 'Check ports'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </AccordionSection>
      )}

      {deleteError && (
        <div className="mb-6 rounded-xl border border-red-900/70 bg-red-950/40 px-4 py-3 text-sm text-red-200">
          {deleteError}
        </div>
      )}

      {deleteConfirmOpen && service && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/70 px-4">
          <div className="w-full max-w-xl rounded-2xl border border-red-900/70 bg-gray-950 shadow-2xl">
            <div className="border-b border-gray-800 px-5 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-red-300">Warning</div>
              <h3 className="mt-2 text-lg font-semibold text-white">Delete {service.display_name}?</h3>
              <p className="mt-2 text-sm text-gray-400">
                This clears the current framework data for this service in one shot.
              </p>
            </div>

            <div className="grid gap-4 px-5 py-4 md:grid-cols-2">
              <section className="rounded-xl border border-gray-800 bg-gray-900/70 p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-red-300">Will Remove</div>
                <ul className="mt-3 space-y-2 text-sm text-gray-300">
                  <li>Service manifest entry and workspace link</li>
                  <li>Current docs, logs, repo, and secret-path evidence for this service</li>
                  <li>Downloaded bundle folders stored by the framework</li>
                </ul>
              </section>

              <section className="rounded-xl border border-gray-800 bg-gray-900/70 p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-cyan-300">Will Keep</div>
                <ul className="mt-3 space-y-2 text-sm text-gray-300">
                  <li>Other services in the workspace</li>
                  <li>Server definitions and workspace definitions</li>
                  <li>Archived workspace run files themselves, with this service removed from their active snapshot data</li>
                </ul>
              </section>
            </div>

            <div className="flex items-center justify-end gap-3 border-t border-gray-800 px-5 py-4">
              <button
                type="button"
                onClick={() => setDeleteConfirmOpen(false)}
                disabled={deleting}
                className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 transition-colors hover:border-gray-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="inline-flex items-center gap-2 rounded-lg border border-red-800 bg-red-950 px-4 py-2 text-sm font-medium text-red-200 transition-colors hover:border-red-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 className="h-4 w-4" />
                {deleting ? 'Deleting…' : 'Delete Service'}
              </button>
            </div>
          </div>
        </div>
      )}

      {service && (
        <AccordionSection
          title="Project Snapshot"
          icon={<FileStack className="h-4 w-4 text-cyan-400" />}
          open={Boolean(panelOpen.project)}
          onToggle={() => togglePanel('project')}
          summary={`${projectDocEntries.length} docs · ${latestTaskDependencies.length} deps · ${latestTaskCrossDependencies.length} cross`}
        >
          <div className="grid gap-4 xl:grid-cols-[1.2fr,0.8fr]">
            <div className="space-y-4">
              <div className="rounded-xl border border-gray-800 bg-gray-950 px-4 py-3">
                <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Featured Project Entry</div>
                <div className="mt-2 text-sm font-medium text-white">{featuredTask?.title || 'No imported project task yet.'}</div>
                {featuredTask?.summary && <div className="mt-2 text-sm text-gray-300">{featuredTask.summary}</div>}
                {featuredTask && latestTask && featuredTask.task_id !== latestTask.task_id && (
                  <div className="mt-2 text-xs text-gray-500">
                    Latest maintenance entry remains in the task ledger below.
                  </div>
                )}
                {service.notes && <div className="mt-3 text-sm text-cyan-100/80">{service.notes}</div>}
              </div>

              {latestTaskNotes.length > 0 && (
                <div className="rounded-xl border border-gray-800 bg-gray-950 px-4 py-3">
                  <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Operator Notes</div>
                  <div className="mt-2 space-y-2 text-sm text-gray-300">
                    {latestTaskNotes.map((note, index) => (
                      <div key={`${note}:${index}`} className="rounded-lg border border-gray-800 bg-black/20 px-3 py-2">
                        {note}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {quickDocPreviews.length > 0 && (
                <div className="rounded-xl border border-gray-800 bg-gray-950 px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Project Doc Quick View</div>
                    <div className="flex flex-wrap gap-2">
                      {quickDocPreviews.map((entry) => {
                        const selected = docPreviewId === entry.id || (!docPreviewId && quickDocPreviews[0]?.id === entry.id)
                        return (
                          <button
                            key={entry.id}
                            type="button"
                            onClick={() => setDocPreviewId((current) => (current === entry.id ? null : entry.id))}
                            className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                              selected
                                ? 'border-cyan-500 bg-cyan-500/10 text-cyan-100'
                                : 'border-gray-700 text-gray-300 hover:border-cyan-500 hover:text-white'
                            }`}
                          >
                            {entry.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                  <pre className="mt-3 max-h-80 overflow-auto rounded-lg border border-gray-800 bg-black/20 p-3 text-xs text-gray-200 whitespace-pre-wrap">
                    {quickPreviewById[docPreviewId || quickDocPreviews[0]?.id || ''] || 'No preview available.'}
                  </pre>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div className="rounded-xl border border-gray-800 bg-gray-950 px-4 py-3">
                <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Cross Dependencies</div>
                {latestTaskCrossDependencies.length === 0 ? (
                  <div className="mt-2 text-sm text-gray-500">No cross dependencies recorded yet.</div>
                ) : (
                  <div className="mt-2 space-y-2">
                    {latestTaskCrossDependencies.map((dependency, index) => (
                      <div key={`${dependency.name}:${index}`} className="rounded-lg border border-gray-800 bg-black/20 px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded border border-gray-700 px-1.5 py-0.5 text-[10px] uppercase text-gray-400">{dependency.kind}</span>
                          <span className="text-sm font-medium text-white">{dependency.name}</span>
                          {(dependency.host || dependency.port) && (
                            <span className="font-mono text-xs text-cyan-300">{dependency.host || '*'}:{dependency.port || 'any'}</span>
                          )}
                        </div>
                        {dependency.notes && <div className="mt-1 text-xs text-gray-400">{dependency.notes}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {latestTaskDiagram && (
                <div className="rounded-xl border border-gray-800 bg-gray-950 px-4 py-3">
                  <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Project Diagram</div>
                  <pre className="mt-2 overflow-auto rounded-lg border border-gray-800 bg-black/20 p-3 text-xs text-gray-200 whitespace-pre-wrap">
                    {latestTaskDiagram}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </AccordionSection>
      )}

      {service && service.task_ledger && service.task_ledger.length > 0 && (
        <AccordionSection
          title="Task Ledger"
          icon={<FileStack className="h-4 w-4 text-cyan-400" />}
          open={Boolean(panelOpen.task_ledger)}
          onToggle={() => togglePanel('task_ledger')}
          summary={`${service.task_ledger.length} entries · latest ${new Date(service.task_ledger[0].timestamp).toLocaleString()}`}
        >
          <TaskLedgerPanel tasks={service.task_ledger} />
        </AccordionSection>
      )}

      {service && (
        <AccordionSection
          title="Runtime"
          icon={<RefreshCw className="h-4 w-4 text-cyan-400" />}
          open={Boolean(panelOpen.runtime)}
          onToggle={() => togglePanel('runtime')}
          summary={`${service.locations.length} locations · ${runtimeAttentionCount} need attention`}
        >
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <div className="mt-1 text-xs text-gray-500">
                {service.execution_mode === 'networked'
                  ? 'Per-location ports, health checks, run-command hints, and node sync.'
                  : `Per-location deployment state, command hints, and node sync for ${service.execution_mode} services.`}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {editingRuntime ? (
                <>
                  <button
                    type="button"
                    onClick={handleCancelRuntimeEdit}
                    disabled={savingRuntime}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-300 transition-colors hover:border-gray-500 hover:text-white disabled:opacity-50"
                  >
                    <X className="h-3.5 w-3.5" />
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleSaveRuntime}
                    disabled={offline || savingRuntime}
                    className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-medium text-black transition-colors hover:bg-gray-200 disabled:opacity-50"
                  >
                    <Save className="h-3.5 w-3.5" />
                    {savingRuntime ? 'Saving…' : 'Save Runtime'}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setRuntimeDraft(service.locations.map((location) => ({ ...location, runtime: { ...location.runtime } })))
                    setRuntimeExecutionMode(service.execution_mode)
                    setEditingRuntime(true)
                    setRuntimeMessage(null)
                  }}
                  disabled={offline}
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-300 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit Runtime
                </button>
              )}
            </div>
          </div>

          {runtimeMessage && (
            <div className="mb-4 rounded-xl border border-gray-800 bg-gray-950 px-3 py-2 text-sm text-gray-300">
              {runtimeMessage}
            </div>
          )}

          <div className="mb-4 rounded-xl border border-gray-800 bg-gray-950 p-3">
            <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Execution Mode</div>
            {editingRuntime ? (
              <select
                value={runtimeExecutionMode}
                onChange={(event) => setRuntimeExecutionMode(event.target.value as Service['execution_mode'])}
                className="mt-2 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
              >
                <option value="networked">networked</option>
                <option value="batch">batch</option>
                <option value="lambda">lambda</option>
                <option value="docs_only">docs_only</option>
              </select>
            ) : (
              <div className="mt-2 inline-flex rounded-full border border-cyan-900/40 bg-cyan-950/20 px-3 py-1 text-sm text-cyan-200">
                {service.execution_mode}
              </div>
            )}
          </div>

          <div className="space-y-4">
            {(editingRuntime ? runtimeDraft : service.locations).map((location) => {
              const latestRuntime = runtimeChecksByLocation.get(location.location_id)
              const latestSync = nodeSyncByLocation.get(location.location_id)
              const nodeViewer = nodeViewerByLocation.get(location.location_id)
              const serverMeta = servers.find((server) => server.server_id === location.server_id)
              const nodeTransition = nodeActionResults[location.location_id]
              const nodeAction = nodeActionLoading[location.location_id]
              const recentLocationEvents = locationActionEvents[location.location_id] ?? []
              const locationOpen = Boolean(locationPanels[location.location_id])
              const portsValue = location.runtime.expected_ports.join(', ')
              const matchedEnvironments = environmentMatchesByLocation.get(location.location_id) ?? environmentMatchesByLocation.get('__service__') ?? []
              const apiLabEnvironment = matchedEnvironments[0] ?? null
              const managerManaged = Boolean(nodeViewer?.manager_managed)
              const remoteNodeActionBlocked = serverMeta?.connection_type === 'ssh'
              const rootManifestVersion = nodeViewer?.installed_version || ''
              const managerVersion = nodeViewer?.manager_version || ''
              const lastInspectedAt = nodeViewer?.last_inspected_at || ''
              const lastSyncedFromNodeAt = latestSync?.direction === 'from_node' ? latestSync.timestamp : ''
              const pullAuthorityUpdatedAt = lastSyncedFromNodeAt || latestSync?.timestamp || ''
              const savedScopeGeneratedAt = service.saved_scope_generated_at || ''
              const connectionStatus = nodeViewer?.connection_status ?? 'unverified'
              const managerHealthCheckedAt = nodeViewer?.manager_health_checked_at || ''
              const managerLivePort = nodeViewer?.manager_health_runtime_port
              const managerLive = nodeViewer?.manager_health_status === 'ok' && managerLivePort === DEFAULT_MANAGER_PORT
              const managerManifestPort = nodeViewer?.manager_manifest_runtime_port
              const manifestLastUpdatedAt = nodeViewer?.manifest_updated_at || nodeViewer?.truth_as_of || ''
              const nodeNeedsSync =
                connectionStatus === 'ok' &&
                Boolean(lastInspectedAt) &&
                isTimestampAfter(lastInspectedAt, lastSyncedFromNodeAt)
              const freshnessState =
                connectionStatus === 'vpn_or_network_blocked'
                  ? 'VPN/network blocked'
                  : nodeNeedsSync
                    ? 'Stale cache'
                    : nodeViewer?.freshness_state || 'Needs inspect'
              const freshnessLabel = freshnessDisplayLabel(freshnessState)
              const freshnessAction = nodeNeedsSync
                ? 'Sync From Node'
                : nodeViewer?.refresh_action || (freshnessState === 'Manager unreachable' ? 'Check 8020' : 'Inspect Node')
              const nodeTruthSource = freshnessSourceLabel(nodeViewer?.freshness_source)
              const nodeDataAsOf = nodeViewer?.data_as_of || lastInspectedAt || latestRuntime?.checked_at || ''
              const nodeTruthAsOf = nodeViewer?.truth_as_of || ''
              const nodeTruthFresh = freshnessState === 'Fresh' && connectionStatus === 'ok'
              const rootManifestStale = Boolean(nodeTruthFresh && managerManaged && managerVersion && rootManifestVersion && managerVersion !== rootManifestVersion)
              const managerRoot = nodeViewer?.manager_root || '/Users/p/Desktop/dashboard'
              const managerRootId = nodeViewer?.manager_root_id || serviceId
              const normalizeCommand = `switchboard node normalize-root --manager-root ${quoteShell(managerRoot)} --project-root ${quoteShell(location.root)} --root-id ${quoteShell(managerRootId)} --service-id ${quoteShell(serviceId)} --display-name ${quoteShell(service.display_name)}`
              const nodeControlLabel = remoteNodeActionBlocked
                ? 'Remote Manager Required'
                : managerManaged
                ? 'Normalize Root'
                : !nodeViewer?.node_present
                  ? 'Register Root'
                  : 'Normalize Root'
              const runtimeControlLabel = remoteNodeActionBlocked
                ? 'Remote Manager Required'
                : managerManaged
                ? 'Manager Status'
                : 'Normalize First'
              const syncBlocked = nodeViewer?.node_present === true && !nodeViewer.bootstrap_ready
              const nodePort = nodeViewer?.target_manager_port ?? DEFAULT_MANAGER_PORT
              const nodeStartCommand = managerManaged
                ? `switchboard node manager-status --manager-root ${quoteShell(managerRoot)} --port ${nodePort}`
                : normalizeCommand
              const nodeManifestPath = `${location.root}/switchboard/node.manifest.json`
              const runtimePidPath = `${location.root}/switchboard/runtime/node.pid`
              const runtimeScopePath = `${location.root}/switchboard/evidence/scope.snapshot.json`
              const inspectCommand = serverShellCommand(serverMeta, `test -f ${quoteShell(nodeManifestPath)} && cat ${quoteShell(nodeManifestPath)}; test -f ${quoteShell(runtimePidPath)} && ps -p "$(cat ${quoteShell(runtimePidPath)})" -o command=; ss -ltnp 2>/dev/null || lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null`)
              const deployAction = nodeViewer?.node_present ? 'node_upgrade' : 'node_deploy'
              const remoteManagerMessage = 'Remote service-level node runtime actions are blocked here. Run switchboard node normalize-root on the remote manager host after read-only preflight.'
              const deployCommandPreview = remoteNodeActionBlocked
                ? [
                    `POST /services/${serviceId}/node/${nodeViewer?.node_present ? 'upgrade' : 'deploy'} {"location_id":"${location.location_id}"}`,
                    remoteManagerMessage,
                  ]
                : [
                    `POST /services/${serviceId}/node/${nodeViewer?.node_present ? 'upgrade' : 'deploy'} {"location_id":"${location.location_id}"}`,
                    normalizeCommand,
                  ]
              const restartCommandPreview = remoteNodeActionBlocked
                ? [
                    `POST /services/${serviceId}/node/restart {"location_id":"${location.location_id}"}`,
                    remoteManagerMessage,
                  ]
                : [
                    `POST /services/${serviceId}/node/restart {"location_id":"${location.location_id}"}`,
                    managerManaged
                      ? `switchboard node manager-status --manager-root ${quoteShell(managerRoot)} --port ${nodePort}`
                      : normalizeCommand,
                  ]
              const runtimeCheckCommandPreview = [
                `POST /services/${serviceId}/runtime/check {"location_id":"${location.location_id}"}`,
                serverShellCommand(serverMeta, `ss -ltnp 2>/dev/null || lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null`),
                location.runtime.healthcheck_command
                  ? serverShellCommand(serverMeta, location.runtime.healthcheck_command)
                  : 'Health check skipped because no command is configured.',
              ].filter(Boolean)
              const syncFromCommandPreview = [
                `POST /services/${serviceId}/node/sync-from {"location_id":"${location.location_id}"}`,
                serverShellCommand(serverMeta, `cat ${quoteShell(nodeManifestPath)}; test -f ${quoteShell(runtimeScopePath)} && cat ${quoteShell(runtimeScopePath)}`),
              ].filter(Boolean)
              const syncToCommandPreview = [
                `POST /services/${serviceId}/node/sync-to {"location_id":"${location.location_id}"}`,
                serverShellCommand(serverMeta, `mkdir -p ${quoteShell(`${location.root}/switchboard/evidence`)} && cat > ${quoteShell(nodeManifestPath)} && cat > ${quoteShell(runtimeScopePath)}`),
              ].filter(Boolean)
              const inspectDetails: ConfirmDetails = {
                preflight: [
                  serverMeta?.vpn_required ? 'VPN is off or network blocked if this times out. Turn VPN on for live verification.' : 'Server route should already be reachable.',
                  'Inspect Node is read-only: it reads node state only and does not import saved scope.',
                  nodeViewer?.node_present ? `Tracked node manifest already exists at ${nodeManifestPath}.` : 'No tracked node manifest is cached yet; inspect will confirm whether one exists on disk.',
                ],
                commandPreview: [`POST /services/${serviceId}/node/inspect {"location_id":"${location.location_id}"}`, inspectCommand].filter(Boolean),
                followUp: [
                  'Check the refreshed Node Viewer block for actual runtime port, pid, bootstrap state, and errors.',
                  'If the node port changed, later restart actions will reuse the discovered port instead of blindly defaulting.',
                ],
                confirmLabel: 'Inspect Server State',
              }
              const deployDetails: ConfirmDetails = {
                preflight: [
                  serverMeta?.vpn_required ? 'VPN is off or network blocked if this times out. Turn VPN on for live verification.' : 'Server route should already be reachable.',
                  remoteNodeActionBlocked
                    ? 'Remote service-level node actions are blocked; use that machine’s manager workflow.'
                    : managerManaged
                    ? 'This root is manager-owned; the action refreshes the root registration and canonical Switchboard files without starting a separate node.'
                    : 'This will register the project root under the local manager and write the canonical Switchboard files.',
                  'Make sure this project root is the correct owner before writing control-center files under switchboard/.',
                ],
                commandPreview: deployCommandPreview,
                followUp: [
                  managerManaged
                    ? 'The single local manager remains the only Switchboard runtime for this machine.'
                    : 'Run Inspect State afterward to confirm the root is manager-owned.',
                  'Bootstrap can still remain not ready until the first task-ledger/bootstrap write happens.',
                ],
                confirmLabel: nodeControlLabel,
              }
              const restartDetails: ConfirmDetails = {
                preflight: [
                  serverMeta?.vpn_required ? 'VPN is off or network blocked if this times out. Turn VPN on for live verification.' : 'Server route should already be reachable.',
                  remoteNodeActionBlocked
                    ? 'Remote service-level node runtime actions are blocked; use that machine’s manager workflow.'
                    : managerManaged
                    ? `This checks the single manager port ${nodePort}; it will not start a project-specific node.`
                    : 'This local root must be normalized before runtime checks; no project-specific node will be started.',
                  managerManaged ? 'Manager-owned roots use the machine manager node on port 8020.' : 'This page does not start per-project manager nodes.',
                ],
                commandPreview: restartCommandPreview,
                followUp: [
                  'Check the action timeline for live elapsed time and ETA while restart runs.',
                  'If restart still fails, inspect node logs immediately from the refreshed Node Viewer.',
                ],
                confirmLabel: runtimeControlLabel,
              }
              const runtimeCheckDetails: ConfirmDetails = {
                preflight: [
                  serverMeta?.vpn_required ? 'VPN is off or network blocked if this times out. Turn VPN on for live verification.' : 'Server route should already be reachable.',
                  'Snapshot reads listeners, exposure, process ownership, and optional health output.',
                  location.runtime.healthcheck_command ? 'A health command is configured and will be executed as part of this snapshot.' : 'No health command is configured, so health will stay skipped.',
                ],
                commandPreview: runtimeCheckCommandPreview,
                followUp: [
                  'Use the refreshed ownership list below to see which tracked service/location each detected port belongs to.',
                  'Unexpected public listeners should be investigated before any new deploy or restart step.',
                ],
                confirmLabel: 'Refresh Runtime Snapshot',
              }
              const syncFromDetails: ConfirmDetails = {
                preflight: [
                  serverMeta?.vpn_required ? 'VPN is off or network blocked if this times out. Turn VPN on for live verification.' : 'Server route should already be reachable.',
                  syncBlocked ? 'Bootstrap is still not ready, so sync from node is blocked until the node writes its first bootstrap/task-ledger entry.' : 'Node bootstrap is ready, so manifest and scope data can be imported.',
                  'Sync From Node imports node state into Control Center and refreshes service, scope, node viewer, and pull-bundle panels.',
                ],
                commandPreview: syncFromCommandPreview,
                followUp: [
                  'Review imported runtime config, scope, and managed-doc metadata after the sync completes.',
                  'If the node is stale, refresh or redeploy it before trusting imported state.',
                ],
                confirmLabel: 'Sync From Node',
              }
              const syncToDetails: ConfirmDetails = {
                preflight: [
                  serverMeta?.vpn_required ? 'VPN is off or network blocked if this times out. Turn VPN on for live verification.' : 'Server route should already be reachable.',
                  syncBlocked ? 'Bootstrap is still not ready, so sync to node is blocked until the node writes its first bootstrap/task-ledger entry.' : 'Node bootstrap is ready, so scope and runtime metadata can be mirrored.',
                  'This writes the control-center service scope and runtime metadata into the selected project root.',
                ],
                commandPreview: syncToCommandPreview,
                followUp: [
                  'Inspect the node again if you want to verify the written manifest and scope snapshot immediately.',
                  'Use the dedicated API Lab page separately for environment-level runtime review and API flow runs.',
                ],
                confirmLabel: 'Sync To Node',
              }
              const persistedActionKey = (Object.keys(LOCK_KEY_TO_ACTION) as PersistedActionKey[]).find((actionKey) =>
                Boolean(activeLocks[actionKey]),
              ) ?? null
              const localAction: LocationActionKey | null =
                nodeAction ??
                (checkingRuntimeLocation === location.location_id
                  ? 'runtime_check'
                  : syncingFromLocation === location.location_id
                    ? 'sync_from_node'
                    : syncingToLocation === location.location_id
                      ? 'sync_to_node'
                      : null)
              const activeAction = localAction ?? (persistedActionKey ? LOCK_KEY_TO_ACTION[persistedActionKey] : null)
              const activeActionStartedAt =
                activeAction === null
                  ? null
                  : actionStartTimes[actionStartKey(location.location_id, activeAction)] ??
                    (persistedActionKey ? activeLocks[persistedActionKey]?.started_at : null) ??
                    new Date().toISOString()
              const activeActionMeta = activeAction ? ACTION_META[activeAction] : null
              const activeActionProgress =
                activeAction && activeActionStartedAt && activeActionMeta
                  ? getActionProgress(activeActionStartedAt, activeActionMeta.eta_seconds, nowMs)
                  : null
              const locationBusy = activeAction !== null
              return (
                <div key={location.location_id} className="rounded-xl border border-gray-800 bg-gray-950 p-4">
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <button
                        type="button"
                        onClick={() => toggleLocationPanel(location.location_id)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="text-xs uppercase tracking-[0.16em] text-gray-500">{location.location_id}</div>
                        <div className="mt-1 text-sm font-medium text-white">{location.server_id}</div>
                        <div className="mt-1 font-mono text-xs text-gray-400 break-all">{location.root}</div>
                        <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.16em]">
                          {serverMeta && (
                            <>
                              <span className={`rounded-full border px-2 py-1 ${serverMeta.vpn_required ? 'border-amber-400/30 bg-amber-400/10 text-amber-200' : 'border-gray-700 bg-gray-900 text-gray-400'}`}>
                                {serverMeta.vpn_required ? 'VPN required' : 'No VPN needed'}
                              </span>
                              <span className={`rounded-full border px-2 py-1 ${serverMeta.deployment_mode === 'local_bundle_only' ? 'border-cyan-400/30 bg-cyan-400/10 text-cyan-200' : 'border-gray-700 bg-gray-900 text-gray-400'}`}>
                                {serverMeta.deployment_mode === 'local_bundle_only' ? 'Local bundle only' : 'Native agent allowed'}
                              </span>
                            </>
                          )}
                          <span className={`rounded-full border px-2 py-1 ${
                            freshnessState === 'Fresh'
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                              : freshnessState === 'VPN/network blocked'
                                ? 'border-orange-500/30 bg-orange-500/10 text-orange-200'
                                : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                          }`}>
                            {freshnessLabel}
                          </span>
                          {nodeTruthFresh ? (
                            <span className="rounded-full border border-gray-700 bg-gray-900 px-2 py-1 text-gray-300">
                              {managerLive
                                ? `Manager live :${managerLivePort}`
                                : managerManaged
                                  ? `manager ${managerVersion || 'active'}`
                                  : `node ${rootManifestVersion || 'not installed'}`}
                            </span>
                          ) : (
                            <span className="rounded-full border border-amber-700/40 bg-amber-950/20 px-2 py-1 text-amber-200">
                              {freshnessAction}
                            </span>
                          )}
                          <span className="rounded-full border border-gray-700 bg-gray-900 px-2 py-1 text-gray-300">
                            Truth source: {nodeTruthSource}
                          </span>
                          <span className="rounded-full border border-gray-700 bg-gray-900 px-2 py-1 text-gray-300">
                            Manager health checked: {formatTimestampLabel(managerHealthCheckedAt)}
                          </span>
                          {rootManifestStale && (
                            <span className="rounded-full border border-amber-700 bg-amber-950/30 px-2 py-1 text-amber-200">
                              root manifest {rootManifestVersion}
                            </span>
                          )}
                          {nodeTruthFresh && (
                            <span className="rounded-full border border-gray-700 bg-gray-900 px-2 py-1 text-gray-300">
                              bootstrap {nodeViewer?.bootstrap_ready ? 'ready' : 'not ready'}
                            </span>
                          )}
                          {nodeViewer?.legacy_runtime_port_label && (
                            <span className="rounded-full border border-amber-700/40 bg-amber-950/20 px-2 py-1 text-amber-200">
                              {nodeViewer.legacy_runtime_port_label}
                            </span>
                          )}
                          {managerManifestPort && managerManifestPort !== DEFAULT_MANAGER_PORT && (
                            <span className="rounded-full border border-amber-700/40 bg-amber-950/20 px-2 py-1 text-amber-200">
                              Manifest runtime port: {managerManifestPort}
                            </span>
                          )}
                          <span className="rounded-full border border-gray-700 bg-gray-900 px-2 py-1 text-gray-300">
                            {managerLive ? 'manager runtime' : nodeTruthFresh ? 'runtime' : 'cached runtime'} {nodeViewer?.runtime_status || 'missing'}
                          </span>
                        </div>
                      </button>
                      <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => initiateAction('node_inspect', location.location_id, inspectDetails)}
                        disabled={offline || locationBusy}
                        className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-200 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
                      >
                        {activeAction === 'inspect' ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : null}
                        {activeAction === 'inspect' ? 'Inspecting…' : 'Inspect State'}
                      </button>
                      <button
                        type="button"
                        onClick={() => initiateAction(deployAction, location.location_id, deployDetails)}
                        disabled={offline || remoteNodeActionBlocked || locationBusy}
                        data-attention={nodeViewer?.needs_install ? 'true' : 'false'}
                        className={`inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs transition-colors disabled:opacity-50 ${
                          nodeViewer?.needs_install
                            ? 'border-amber-700 text-amber-200 shadow-[0_0_0_1px_rgba(250,204,21,0.2),0_0_18px_rgba(250,204,21,0.12)]'
                            : 'border-gray-700 text-gray-200 hover:border-cyan-500 hover:text-white'
                        }`}
                      >
                        {activeAction === 'deploy' || activeAction === 'upgrade' ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : null}
                        {activeAction === 'deploy'
                          ? 'Registering…'
                          : activeAction === 'upgrade'
                            ? 'Refreshing…'
                            : nodeControlLabel}
                      </button>
                      <button
                        type="button"
                        onClick={() => initiateAction('node_restart', location.location_id, restartDetails)}
                        disabled={offline || remoteNodeActionBlocked || !managerManaged || locationBusy}
                        className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-200 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
                      >
                        {activeAction === 'restart' ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : null}
                        {activeAction === 'restart' ? 'Checking…' : runtimeControlLabel}
                      </button>
                      <button
                        type="button"
                        onClick={() => initiateAction('runtime_check', location.location_id, runtimeCheckDetails)}
                        disabled={offline || locationBusy}
                        className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-200 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${checkingRuntimeLocation === location.location_id || activeLocks.runtime_check ? 'animate-spin' : ''}`} />
                        {checkingRuntimeLocation === location.location_id || activeLocks.runtime_check ? 'Refreshing…' : actionLockStatus === 'offline' ? 'Backend Offline' : 'Runtime Snapshot'}
                      </button>
                      <button
                        type="button"
                        onClick={() => initiateAction('sync_from_node', location.location_id, syncFromDetails)}
                        disabled={offline || locationBusy || syncBlocked}
                        className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-200 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
                      >
                        {syncingFromLocation === location.location_id || activeLocks.sync_from_node ? 'Syncing…' : actionLockStatus === 'offline' ? 'Backend Offline' : 'Sync From Node'}
                      </button>
                      <button
                        type="button"
                        onClick={() => initiateAction('sync_to_node', location.location_id, syncToDetails)}
                        disabled={offline || locationBusy || syncBlocked}
                        className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-200 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
                      >
                        {syncingToLocation === location.location_id || activeLocks.sync_to_node ? 'Syncing…' : actionLockStatus === 'offline' ? 'Backend Offline' : 'Sync To Node'}
                      </button>
                    </div>
                    </div>

                    {actionLockStatus === 'offline' && (
                      <div className="rounded-xl border border-rose-700/40 bg-rose-950/20 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-rose-300">Backend Offline</div>
                        <div className="mt-1 text-sm text-rose-100">
                          Action locks could not be refreshed from the control-center backend. Stale session progress was cleared instead of being treated as real runtime activity.
                        </div>
                      </div>
                    )}

                    {connectionStatus === 'vpn_or_network_blocked' && (
                      <div className="rounded-xl border border-orange-700/40 bg-orange-950/20 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-orange-300">VPN / Network Blocked</div>
                        <div className="mt-1 text-sm text-orange-100">
                          VPN is off or network blocked. Turn VPN on for live verification. Switchboard is not inferring freshness from this timeout.
                        </div>
                      </div>
                    )}

                    {freshnessState === 'Manager unreachable' && (
                      <div className="rounded-xl border border-amber-700/40 bg-amber-950/20 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-amber-300">Manager unreachable</div>
                        <div className="mt-1 text-sm text-amber-100">
                          Check 8020 before trusting cached runtime, repo, docs, scope, or pull authority. 8009 only proves the Control Center API is alive.
                        </div>
                      </div>
                    )}

                    {nodeViewer?.needs_bootstrap && (
                      <div className="rounded-xl border border-amber-700/40 bg-amber-950/20 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-amber-300">Bootstrap Still Missing</div>
                        <div className="mt-1 text-sm text-amber-100">
                          The node runtime is up, but bootstrap metadata has not been written yet.
                        </div>
                        <div className="mt-2 text-xs text-amber-200/80">
                          Current state: {managerManaged ? `manager ${managerVersion || 'active'}` : `node ${rootManifestVersion || 'not installed'}`} · runtime {nodeViewer.runtime_status} · bootstrap not ready. Sync actions stay blocked until the first task-ledger/bootstrap entry is produced.
                        </div>
                      </div>
                    )}

                    {(activeAction !== null || recentLocationEvents.length > 0) && (
                      <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Action Timeline</div>
                          {activeAction !== null && activeActionMeta && activeActionProgress && activeActionStartedAt && (
                            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-900/40 bg-cyan-950/20 px-2 py-1 text-[11px] uppercase tracking-[0.14em] text-cyan-200">
                              <LoaderCircle className="h-3 w-3 animate-spin" />
                              {activeActionMeta.running_label}
                            </div>
                          )}
                        </div>
                        {activeAction !== null && activeActionMeta && activeActionProgress && activeActionStartedAt && (
                          <div className="mt-3 rounded-lg border border-cyan-900/30 bg-cyan-950/20 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-cyan-100">
                              <div>{activeActionMeta.running_label}</div>
                              <div className="text-xs text-cyan-100/70">
                                Started {new Date(activeActionStartedAt).toLocaleTimeString()} · elapsed {formatDurationLabel(activeActionProgress.elapsedSeconds)}
                              </div>
                            </div>
                            <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-900">
                              <div
                                className="h-full rounded-full bg-cyan-400 transition-[width]"
                                style={{ width: `${Math.max(8, activeActionProgress.percent)}%` }}
                              />
                            </div>
                            <div className="mt-2 flex flex-wrap items-center justify-between gap-3 text-xs text-gray-400">
                              <span>
                                {activeActionProgress.overrunSeconds > 0
                                  ? `Past estimate by ${formatDurationLabel(activeActionProgress.overrunSeconds)}`
                                  : `ETA about ${formatDurationLabel(activeActionProgress.remainingSeconds)} remaining`}
                              </span>
                              {persistedActionKey && activeLocks[persistedActionKey]?.expires_at && (
                                <span>Lock expires {new Date(activeLocks[persistedActionKey].expires_at).toLocaleTimeString()}</span>
                              )}
                            </div>
                          </div>
                        )}
                        <div className="mt-3 space-y-2">
                          {recentLocationEvents.map((event, index) => (
                            <div key={`${event.timestamp}:${event.action}:${index}`} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-gray-800 bg-black/20 px-3 py-2 text-xs">
                              <div className="min-w-0">
                                <div className={`uppercase tracking-[0.14em] ${
                                  event.status === 'error'
                                    ? 'text-red-300'
                                    : event.status === 'running'
                                      ? 'text-cyan-300'
                                      : 'text-emerald-300'
                                }`}>
                                  {event.action.split('_').join(' ')}
                                </div>
                                <div className="mt-1 text-gray-300">{event.message}</div>
                                {event.duration_seconds !== undefined && (
                                  <div className="mt-1 text-gray-500">Duration {formatDurationLabel(event.duration_seconds)}</div>
                                )}
                              </div>
                              <div className="text-gray-500">{new Date(event.timestamp).toLocaleTimeString()}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {apiLabEnvironment && (
                      <div className="rounded-xl border border-cyan-900/40 bg-cyan-950/20 p-3">
                        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                          <div>
                            <div className="text-xs uppercase tracking-[0.16em] text-cyan-300">Dedicated API Lab</div>
                            <div className="mt-1 text-sm text-cyan-100">
                              {apiLabEnvironment.display_name} opens as its own full-page environment viewer.
                            </div>
                            <div className="mt-1 text-xs text-cyan-100/70">
                              Use it for runtime snapshots, API flows, dependency review, and run history outside this runtime card.
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => onOpenEnvironmentLab(apiLabEnvironment.environment_id)}
                            className="inline-flex items-center gap-1 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100 transition-colors hover:border-cyan-400 hover:text-white"
                          >
                            Open Full Page
                          </button>
                        </div>
                      </div>
                    )}

                    {locationOpen && (
                      <>

                  <div className="mt-4 rounded-xl border border-gray-800 bg-gray-900 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Node Viewer</div>
                    {nodeViewer ? (
                      <div className="mt-2 grid gap-2 text-sm text-gray-300 md:grid-cols-2">
                        <div className="flex items-center gap-2"><span className="text-gray-500">Connection:</span> <StatusBadge status={connectionStatus} /></div>
                        <div><span className="text-gray-500">Freshness:</span> {freshnessLabel}</div>
                        <div><span className="text-gray-500">Truth source:</span> {nodeTruthSource}</div>
                        <div><span className="text-gray-500">Data as of:</span> {formatTimestampLabel(nodeDataAsOf)}</div>
                        <div><span className="text-gray-500">Truth as of:</span> {formatTimestampLabel(nodeTruthAsOf)}</div>
                        <div><span className="text-gray-500">Manager health checked:</span> {formatTimestampLabel(managerHealthCheckedAt)}</div>
                        <div><span className="text-gray-500">Last inspected:</span> {formatTimestampLabel(lastInspectedAt)}</div>
                        <div><span className="text-gray-500">Last synced from node:</span> {formatTimestampLabel(lastSyncedFromNodeAt)}</div>
                        <div><span className="text-gray-500">Saved scope updated:</span> {formatTimestampLabel(savedScopeGeneratedAt)}</div>
                        <div><span className="text-gray-500">Pull authority updated:</span> {formatTimestampLabel(pullAuthorityUpdatedAt)}</div>
                        <div><span className="text-gray-500">Manifest last updated:</span> {formatTimestampLabel(manifestLastUpdatedAt)}</div>
                        <div><span className="text-gray-500">Root manifest:</span> {rootManifestVersion || 'not installed'}</div>
                        <div><span className="text-gray-500">Manager version:</span> {managerManaged ? managerVersion || 'active' : 'not manager-owned'}</div>
                        <div><span className="text-gray-500">Manager live port:</span> {managerLivePort ? `:${managerLivePort}` : 'unknown'}</div>
                        <div><span className="text-gray-500">Manifest runtime port:</span> {managerManifestPort ? `:${managerManifestPort}` : 'unknown'}</div>
                        <div><span className="text-gray-500">Bootstrap:</span> {nodeViewer.bootstrap_version || 'not ready'}</div>
                        <div><span className="text-gray-500">Manager owned:</span> {nodeViewer.manager_managed ? 'yes' : 'no'}</div>
                        <div><span className="text-gray-500">Manager root:</span> {nodeViewer.manager_root_id || 'unregistered'}</div>
                        <div><span className="text-gray-500">Runtime:</span> {nodeViewer.runtime_status}</div>
                        <div><span className="text-gray-500">Manifest:</span> <span className="font-mono text-xs">{nodeViewer.manifest_path}</span></div>
                        <div><span className="text-gray-500">Port:</span> {nodeViewer.runtime_port}</div>
                        <div><span className="text-gray-500">Runtime ready:</span> {nodeViewer.runtime_ready ? 'yes' : 'no'}</div>
                        {nodeViewer.last_error && <div className="md:col-span-2 text-amber-200">{nodeViewer.last_error}</div>}
                        {nodeNeedsSync && (
                          <div className="md:col-span-2 text-xs text-amber-200">
                            Inspect is newer than the last Sync From Node. Run Sync From Node with VPN on before trusting pull bundles.
                          </div>
                        )}
                        {nodeViewer.manager_managed && (
                          <div className="md:col-span-2 text-xs text-cyan-200">
                            This root is owned by the local Switchboard manager; service actions do not install or start a per-project node runtime.
                          </div>
                        )}
                        {rootManifestStale && (
                          <div className="md:col-span-2 text-xs text-amber-200">
                            Root manifest version trails the manager. Normalize Root refreshes the manifest through the manager path.
                          </div>
                        )}
                        {nodeViewer.node_present && !nodeViewer.manager_managed && !nodeViewer.installed_release_asset_id && (
                          <div className="md:col-span-2 text-xs text-amber-200">
                            Exact GitHub release identity is not recorded on this node yet. Inspect can confirm package version, but release-asset equality stays unknown until the node is installed from a tracked GitHub release.
                          </div>
                        )}
                        {nodeViewer.node_present && !nodeViewer.bootstrap_ready && (
                          <div className="md:col-span-2 text-xs text-amber-200">
                            Node scaffold is present, but sync stays blocked until bootstrap writes the first task entry.
                          </div>
                        )}
                        <div className="md:col-span-2 rounded-lg border border-gray-800 bg-black/20 px-3 py-2">
                          <div className="text-[11px] uppercase tracking-[0.14em] text-gray-500">{managerManaged ? 'Manager Command' : 'Normalize Command'}</div>
                          <pre className="mt-2 overflow-x-auto text-xs text-cyan-200">{nodeStartCommand}</pre>
                          <div className="mt-2 text-xs text-gray-500">
                            Switchboard runtime ownership stays on the machine manager node. Project roots are normalized, snapshotted, and verified under that manager instead of running separate project node listeners.
                          </div>
                        </div>
                        {nodeTransition?.before && nodeTransition?.after && (
                          <div className="md:col-span-2 mt-2 rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-100">
                            <div className="uppercase tracking-[0.14em] text-amber-300">Latest action delta</div>
                            <div className="mt-1 flex flex-wrap gap-4">
                              <span>Root manifest: {nodeTransition.before.installed_version || 'none'} → {nodeTransition.after.installed_version || 'none'}</span>
                              <span>Bootstrap: {nodeTransition.before.bootstrap_ready ? 'ready' : 'not ready'} → {nodeTransition.after.bootstrap_ready ? 'ready' : 'not ready'}</span>
                              <span>Runtime: {nodeTransition.before.runtime_status} → {nodeTransition.after.runtime_status}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="mt-2 text-sm text-gray-500">No node viewer data cached yet. Use Inspect State.</div>
                    )}
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {(runtimeExecutionMode === 'networked' || location.runtime.expected_ports.length > 0 || (service?.task_ledger?.[0]?.runtime_services?.length ?? 0) > 0) && (
                    <div className="text-sm text-gray-300">
                      <div className="mb-1">Expected ports</div>
                      {editingRuntime ? (
                        <input
                          value={portsValue}
                          onChange={(event) => updateRuntimeDraftField(location.location_id, 'expected_ports', event.target.value)}
                          className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                        />
                      ) : (
                        <div className="rounded-lg border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-gray-200 min-h-[38px]">
                          {service?.task_ledger?.[0]?.runtime_services?.length ? (
                            <div className="space-y-1">
                              {service.task_ledger[0].runtime_services.map((rs, idx) => (
                                <div key={idx} className="flex flex-wrap items-center gap-2">
                                  <span className="font-mono text-cyan-300">{rs.port || 'any'}</span>
                                  <span className="text-gray-300">{rs.name}</span>
                                  {rs.purpose && <span className="text-xs text-gray-500">({rs.purpose})</span>}
                                </div>
                              ))}
                            </div>
                          ) : (
                            portsValue || 'Not configured'
                          )}
                        </div>
                      )}
                    </div>
                    )}

                    <label className="text-sm text-gray-300">
                      <div className="mb-1">Monitoring mode</div>
                      {editingRuntime ? (
                        <select
                          value={location.runtime.monitoring_mode}
                          onChange={(event) => updateRuntimeDraftField(location.location_id, 'monitoring_mode', event.target.value)}
                          className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                        >
                          <option value="manual">manual</option>
                          <option value="detect">detect</option>
                          <option value="node_managed">node_managed</option>
                        </select>
                      ) : (
                        <div className="rounded-lg border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-gray-200">
                          {location.runtime.monitoring_mode}
                        </div>
                      )}
                    </label>
                  </div>

                  {runtimeExecutionMode !== 'docs_only' && (
                  <label className="mt-3 block text-sm text-gray-300">
                    <div className="mb-1">Health check command</div>
                    {editingRuntime ? (
                      <input
                        value={location.runtime.healthcheck_command}
                        onChange={(event) => updateRuntimeDraftField(location.location_id, 'healthcheck_command', event.target.value)}
                        className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                      />
                    ) : (
                      <pre className="rounded-lg border border-gray-800 bg-gray-900 p-3 text-xs text-cyan-200 overflow-x-auto">
                        {location.runtime.healthcheck_command || 'Not configured'}
                      </pre>
                    )}
                  </label>
                  )}

                  <label className="mt-3 block text-sm text-gray-300">
                    <div className="mb-1">Run command hint</div>
                    {editingRuntime ? (
                      <input
                        value={location.runtime.run_command_hint}
                        onChange={(event) => updateRuntimeDraftField(location.location_id, 'run_command_hint', event.target.value)}
                        className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                      />
                    ) : (
                      <pre className="rounded-lg border border-gray-800 bg-gray-900 p-3 text-xs text-cyan-200 overflow-x-auto">
                        {location.runtime.run_command_hint || 'Not configured'}
                      </pre>
                    )}
                  </label>

                  <label className="mt-3 block text-sm text-gray-300">
                    <div className="mb-1">Runtime notes</div>
                    {editingRuntime ? (
                      <textarea
                        value={location.runtime.notes}
                        onChange={(event) => updateRuntimeDraftField(location.location_id, 'notes', event.target.value)}
                        className="min-h-24 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                      />
                    ) : (
                      <div className="rounded-lg border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-gray-200">
                        {location.runtime.notes || 'No notes'}
                      </div>
                    )}
                  </label>

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <div className="rounded-xl border border-gray-800 bg-gray-900 p-3">
                      <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Latest Runtime Check</div>
                      {latestRuntime ? (
                        <div className="mt-2 space-y-2 text-sm text-gray-300">
                          <div className="flex items-center gap-2">
                            <StatusBadge status={latestRuntime.status} />
                            <span className="text-xs text-gray-500">{new Date(latestRuntime.checked_at).toLocaleString()}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Detected ports:</span>{' '}
                            {runtimeExecutionMode !== 'networked' && latestRuntime.detected_ports.length === 0
                              ? 'not required'
                              : latestRuntime.detected_ports.length > 0
                              ? latestRuntime.detected_ports.map((port) => `:${port.port}`).join(', ')
                              : 'none'}
                          </div>
                          <div>
                            <span className="text-gray-500">Missing ports:</span>{' '}
                            {runtimeExecutionMode !== 'networked' && latestRuntime.missing_ports.length === 0
                              ? 'not required'
                              : latestRuntime.missing_ports.length > 0
                                ? latestRuntime.missing_ports.join(', ')
                                : 'none'}
                          </div>
                          <div>
                            <span className="text-gray-500">Health:</span> {latestRuntime.healthcheck_status}
                          </div>
                          <div>
                            <span className="text-gray-500">Detected command:</span>{' '}
                            {latestRuntime.detected_process_command || 'Not detected'}
                          </div>
                          <div>
                            <span className="text-gray-500">Node present:</span> {latestRuntime.node_present ? 'yes' : 'no'}
                          </div>
                          {latestRuntime.process_findings && latestRuntime.process_findings.length > 0 && (
                            <div className="rounded-lg border border-gray-800 bg-black/20 p-2">
                              <div className="text-xs uppercase tracking-[0.14em] text-gray-500">Port ownership</div>
                              <div className="mt-2 space-y-2">
                                {latestRuntime.process_findings.map((finding, index) => {
                                  const exposure = latestRuntime.exposed_ports?.find((entry) => entry.port === finding.port)
                                  const ownerLabel = finding.owner_display_name || finding.owner_root || finding.process_name || 'Untracked process'
                                  return (
                                    <div key={`${finding.port ?? 'na'}:${finding.pid ?? index}`} className="rounded-lg border border-gray-800 px-3 py-2">
                                      <div className="flex flex-wrap items-center gap-2 text-sm text-gray-200">
                                        <span className="font-mono text-cyan-300">:{finding.port ?? 'unknown'}</span>
                                        <span>{ownerLabel}</span>
                                        {exposure && (
                                          <span className="rounded-full border border-gray-700 bg-gray-900 px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-gray-300">
                                            {exposure.exposure}
                                          </span>
                                        )}
                                      </div>
                                      <div className="mt-1 text-xs text-gray-500">
                                        {finding.owner_service_id ? `service ${finding.owner_service_id}` : finding.process_name || 'unknown process'}
                                        {finding.owner_root ? ` · ${finding.owner_root}` : ''}
                                        {finding.pid ? ` · pid ${finding.pid}` : ''}
                                        {finding.bind_address ? ` · ${finding.bind_address}` : ''}
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          )}
                          {latestRuntime.exposed_ports && latestRuntime.exposed_ports.length > 0 && (
                            <div>
                              <span className="text-gray-500">Exposed ports:</span>{' '}
                              {latestRuntime.exposed_ports.map((port) => `${port.port}:${port.exposure}`).join(', ')}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="mt-2 text-sm text-gray-500">No runtime check captured yet.</div>
                      )}
                    </div>

                    <div className="rounded-xl border border-gray-800 bg-gray-900 p-3">
                      <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Latest Node Sync</div>
                      {latestSync ? (
                        <div className="mt-2 space-y-2 text-sm text-gray-300">
                          <div className="flex items-center gap-2">
                            <StatusBadge status={latestSync.status} />
                            <span className="text-xs text-gray-500">{new Date(latestSync.timestamp).toLocaleString()}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Direction:</span> {latestSync.direction}
                          </div>
                          <div>
                            <span className="text-gray-500">Source:</span> {latestSync.source}
                          </div>
                          <div>
                            <span className="text-gray-500">Target:</span> {latestSync.target}
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 text-sm text-gray-500">No node sync recorded yet.</div>
                      )}
                    </div>
                  </div>
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </AccordionSection>
      )}

      <AccordionSection
        title="Repositories"
        icon={<FolderTree className="h-4 w-4 text-cyan-400" />}
        open={Boolean(panelOpen.repositories)}
        onToggle={() => togglePanel('repositories')}
        summary={`${repos.length} tracked repositories`}
      >
        <RepoSummary
          serviceId={serviceId}
          repos={repos}
          allowedPaths={service?.allowed_git_pull_paths}
          disabled={offline}
        />
      </AccordionSection>

      <AccordionSection
        title="Project Files"
        icon={<FolderTree className="h-4 w-4 text-cyan-400" />}
        open={Boolean(panelOpen.scope)}
        onToggle={() => togglePanel('scope')}
        summary={`${projectDocEntries.length} project docs · ${scopeSummary.repo} repo · ${scopeSummary.code} code · ${scopeSummary.doc} doc · ${scopeSummary.log} log`}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="text-xs text-gray-500">Project docs, quick previews, managed-doc controls, and saved scope live in one compact place. Root project docs stay in scope; framework local/evidence overhead stays out.</div>
          <div className="flex items-center gap-2">
            {editingScope ? (
              <>
                <button
                  type="button"
                  onClick={handleCancelScopeEdit}
                  disabled={savingScope}
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-300 transition-colors hover:border-gray-500 hover:text-white disabled:opacity-50"
                >
                  <X className="h-3.5 w-3.5" />
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveScope}
                  disabled={offline || savingScope || !service}
                  className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-medium text-black transition-colors hover:bg-gray-200 disabled:opacity-50"
                >
                  <Save className="h-3.5 w-3.5" />
                  {savingScope ? 'Saving…' : 'Save Scope'}
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setScopeDraft(scopeEntries.map((entry) => ({ ...entry })))
                  setEditingScope(true)
                  setScopeMessage(null)
                }}
                disabled={offline}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-300 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
              >
                <Pencil className="h-3.5 w-3.5" />
                Edit Scope
              </button>
            )}
          </div>
        </div>
        <div className="mb-4 rounded-xl border border-gray-800 bg-gray-950 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Project Docs</div>
              <div className="mt-1 text-xs text-gray-500">
                README/API/CHANGELOG and other project-facing docs synced from the node. These should be included in quick review and pull bundles.
              </div>
            </div>
            <div className="flex items-center gap-2">
              {editingManagedDocs ? (
                <>
                  <button
                    type="button"
                    onClick={handleCancelManagedDocsEdit}
                    disabled={savingManagedDocs}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-300 transition-colors hover:border-gray-500 hover:text-white disabled:opacity-50"
                  >
                    <X className="h-3.5 w-3.5" />
                    Cancel Docs
                  </button>
                  <button
                    type="button"
                    onClick={handleSaveManagedDocs}
                    disabled={offline || savingManagedDocs}
                    className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-medium text-black transition-colors hover:bg-gray-200 disabled:opacity-50"
                  >
                    <Save className="h-3.5 w-3.5" />
                    {savingManagedDocs ? 'Saving…' : 'Save Docs'}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setManagedDocsDraft(service?.managed_docs.map((entry) => ({ ...entry })) ?? [])
                    setEditingManagedDocs(true)
                    setManagedDocsMessage(null)
                  }}
                  disabled={offline}
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-300 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit Docs
                </button>
              )}
            </div>
          </div>
          {managedDocsMessage && (
            <div className="mt-3 rounded-xl border border-gray-800 bg-black/20 px-3 py-2 text-sm text-gray-300">
              {managedDocsMessage}
            </div>
          )}
          <div className="mt-3 space-y-2">
            {projectDocEntries.length === 0 ? (
              <div className="text-sm text-gray-500">No project-facing docs have been synced yet.</div>
            ) : (
              projectDocEntries.map((entry) => {
                const hasPreview = Boolean(quickPreviewById[entry.id])
                const selected = docPreviewId === entry.id || (!docPreviewId && quickDocPreviews[0]?.id === entry.id && hasPreview)
                return (
                  <div key={`${entry.id}:${entry.path}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-800 bg-black/20 px-3 py-2 text-sm">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-white">{entry.label}</span>
                        <span className="rounded-full border border-cyan-900 bg-cyan-950/60 px-2 py-0.5 text-[11px] uppercase tracking-[0.14em] text-cyan-300">
                          tracked
                        </span>
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-[0.14em] ${entry.frameworkWritesEnabled ? 'border-emerald-900 bg-emerald-950/60 text-emerald-300' : 'border-gray-700 text-gray-500'}`}>
                          {entry.frameworkWritesEnabled ? 'framework writes on' : 'project-owned'}
                        </span>
                      </div>
                      <div className="mt-1 font-mono text-[11px] text-gray-400 break-all">{entry.path}</div>
                    </div>
                    {hasPreview && (
                      <button
                        type="button"
                        onClick={() => setDocPreviewId((current) => (current === entry.id ? null : entry.id))}
                        className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                          selected
                            ? 'border-cyan-500 bg-cyan-500/10 text-cyan-100'
                            : 'border-gray-700 text-gray-300 hover:border-cyan-500 hover:text-white'
                        }`}
                      >
                        {selected ? 'Hide Preview' : 'Quick View'}
                      </button>
                    )}
                  </div>
                )
              })
            )}
          </div>
          {(editingManagedDocs ? managedDocsDraft : service?.managed_docs ?? []).filter((entry) => !isFrameworkOverheadDoc(entry.path)).length > 0 && (
            <div className="mt-4 space-y-2">
              <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Framework Write Policy</div>
              <div className="text-xs text-gray-500">
                These entries only control whether Switchboard may rewrite the root file. They do not decide whether the project doc exists, shows up in quick view, or gets included in scope and pull bundles.
              </div>
              {(editingManagedDocs ? managedDocsDraft : service?.managed_docs ?? [])
                .filter((entry) => !isFrameworkOverheadDoc(entry.path))
                .map((entry, index) => (
                  <div key={`${entry.doc_id}:${entry.path}:${index}`} className="grid gap-2 rounded-lg border border-gray-800 bg-black/20 px-3 py-2 md:grid-cols-[auto,1fr,auto] md:items-center">
                    <div className="text-xs font-medium uppercase tracking-[0.14em] text-gray-300">{entry.doc_id}</div>
                    {editingManagedDocs ? (
                      <input
                        value={entry.path}
                        onChange={(event) =>
                          setManagedDocsDraft((current) =>
                            current.map((candidate, candidateIndex) =>
                              candidateIndex === index ? { ...candidate, path: event.target.value } : candidate,
                            ),
                          )
                        }
                        className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs text-white outline-none focus:border-cyan-500"
                      />
                    ) : (
                      <div className="font-mono text-[11px] text-gray-400 break-all">{entry.path}</div>
                    )}
                    {editingManagedDocs ? (
                      <label className="inline-flex items-center gap-2 text-xs text-gray-300">
                        <input
                          type="checkbox"
                          checked={entry.enabled}
                          onChange={(event) =>
                            setManagedDocsDraft((current) =>
                              current.map((candidate, candidateIndex) =>
                                candidateIndex === index ? { ...candidate, enabled: event.target.checked } : candidate,
                              ),
                            )
                          }
                        />
                        Enabled
                      </label>
                    ) : (
                      <div className="text-[11px] text-gray-500">
                        {entry.enabled
                          ? entry.last_generated_at
                            ? `Framework last wrote ${new Date(entry.last_generated_at).toLocaleString()}`
                            : 'Framework writes enabled for this file'
                          : 'Project-owned source file. Framework writes disabled.'}
                      </div>
                    )}
                  </div>
                ))}
            </div>
          )}
          {quickDocPreviews.length > 0 && (
            <pre className="mt-4 max-h-80 overflow-auto rounded-lg border border-gray-800 bg-black/20 p-3 text-xs text-gray-200 whitespace-pre-wrap">
              {quickPreviewById[docPreviewId || quickDocPreviews[0]?.id || ''] || 'No preview available.'}
            </pre>
          )}
        </div>
        {scopeMessage && (
          <div className="mb-3 rounded-xl border border-gray-800 bg-gray-950 px-3 py-2 text-sm text-gray-300">
            {scopeMessage}
          </div>
        )}
        {(editingScope ? scopeDraft : scopeEntries).length === 0 ? (
          <div className="text-sm text-gray-500">No saved scope entries yet.</div>
        ) : (
          <div className="space-y-2">
            {(editingScope ? scopeDraft : scopeEntries).map((entry, index) => (
              <div key={`${entry.entry_id ?? entry.kind}:${entry.path}:${index}`} className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2.5">
                {editingScope ? (
                  <div className="space-y-3">
                    <input
                      value={entry.path}
                      onChange={(event) =>
                        setScopeDraft((current) =>
                          current.map((candidate, candidateIndex) =>
                            candidateIndex === index ? { ...candidate, path: event.target.value } : candidate,
                          ),
                        )
                      }
                      className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs text-white outline-none focus:border-cyan-500"
                    />
                    <div className="grid gap-2 md:grid-cols-[1fr,1fr,auto,auto]">
                      <select
                        value={entry.kind}
                        onChange={(event) =>
                          setScopeDraft((current) =>
                            current.map((candidate, candidateIndex) =>
                              candidateIndex === index
                                ? { ...candidate, kind: event.target.value as ScopeEntry['kind'] }
                                : candidate,
                            ),
                          )
                        }
                        className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs text-white outline-none focus:border-cyan-500"
                      >
                        <option value="repo">Repo</option>
                        <option value="code">Code</option>
                        <option value="doc">Doc</option>
                        <option value="log">Log</option>
                        <option value="exclude">Exclude</option>
                      </select>
                      <select
                        value={entry.path_type}
                        onChange={(event) =>
                          setScopeDraft((current) =>
                            current.map((candidate, candidateIndex) =>
                              candidateIndex === index
                                ? { ...candidate, path_type: event.target.value as ScopeEntry['path_type'] }
                                : candidate,
                            ),
                          )
                        }
                        className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-xs text-white outline-none focus:border-cyan-500"
                      >
                        <option value="file">File</option>
                        <option value="dir">Dir</option>
                        <option value="glob">Glob</option>
                      </select>
                      <label className="inline-flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-300">
                        <input
                          type="checkbox"
                          checked={entry.enabled}
                          onChange={(event) =>
                            setScopeDraft((current) =>
                              current.map((candidate, candidateIndex) =>
                                candidateIndex === index
                                  ? { ...candidate, enabled: event.target.checked }
                                  : candidate,
                              ),
                            )
                          }
                        />
                        Enabled
                      </label>
                      <button
                        type="button"
                        onClick={() =>
                          setScopeDraft((current) => current.filter((_, candidateIndex) => candidateIndex !== index))
                        }
                        className="rounded-lg border border-red-900 px-3 py-2 text-xs text-red-300 transition-colors hover:border-red-700 hover:text-red-200"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full border border-gray-700 px-2 py-0.5 text-[11px] uppercase tracking-[0.16em] text-cyan-300">
                          {entry.kind}
                        </span>
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] uppercase tracking-[0.16em] ${entry.enabled ? 'border-emerald-900 text-emerald-300' : 'border-gray-700 text-gray-500'}`}>
                          {entry.enabled ? 'enabled' : 'disabled'}
                        </span>
                        <span className="text-[11px] uppercase tracking-[0.16em] text-gray-500">
                          {entry.path_type} · {entry.source}
                        </span>
                      </div>
                      <div className="mt-1 font-mono text-xs text-gray-300 break-all">{entry.path}</div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {editingScope && (
          <div className="mt-4 rounded-xl border border-gray-800 bg-gray-950 p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Add scope entry</div>
            <div className="mt-3 grid gap-3 md:grid-cols-[2fr,1fr,1fr,auto]">
              <input
                value={newScopePath}
                onChange={(event) => setNewScopePath(event.target.value)}
                className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                placeholder="/path/to/folder/or/file"
              />
              <select
                value={newScopeKind}
                onChange={(event) => setNewScopeKind(event.target.value as ScopeEntry['kind'])}
                className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
              >
                <option value="repo">Repo</option>
                <option value="code">Code</option>
                <option value="doc">Doc</option>
                <option value="log">Log</option>
                <option value="exclude">Exclude</option>
              </select>
              <select
                value={newScopePathType}
                onChange={(event) => setNewScopePathType(event.target.value as ScopeEntry['path_type'])}
                className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
              >
                <option value="file">File</option>
                <option value="dir">Dir</option>
                <option value="glob">Glob</option>
              </select>
              <button
                type="button"
                onClick={addScopeEntry}
                className="rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-200 transition-colors hover:border-cyan-500 hover:text-white"
              >
                Add
              </button>
            </div>
          </div>
        )}
        <div className="mt-4 rounded-xl border border-gray-800 bg-gray-950 p-4">
          <div className="mb-3 text-xs uppercase tracking-[0.16em] text-gray-500">Collected Files</div>
          <div className="mb-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-gray-800 bg-gray-900 px-3 py-3">
              <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Repositories</div>
              <div className="mt-1 text-lg font-medium text-white">{repos.length}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900 px-3 py-3">
              <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Documents</div>
              <div className="mt-1 text-lg font-medium text-white">{docs.length}</div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900 px-3 py-3">
              <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Logs</div>
              <div className="mt-1 text-lg font-medium text-white">{logs.length}</div>
            </div>
          </div>
          <DownloadPanel serviceId={serviceId} docs={docs} logs={logs} disabled={offline} />
        </div>
      </AccordionSection>

      {service && (
        <AccordionSection
          title="Pull Bundles"
          icon={<FileStack className="h-4 w-4 text-cyan-400" />}
          open={Boolean(panelOpen.pull_bundles)}
          onToggle={() => togglePanel('pull_bundles')}
          summary={bundleHistoryMeta.count > 0 ? `${bundleHistoryMeta.count} bundles · latest ${new Date(bundleHistoryMeta.latestCreatedAt).toLocaleString()}` : 'No bundle history yet'}
        >
          <PullBundlePanel service={service} disabled={offline} refreshKey={pullBundleRefreshKey} />
        </AccordionSection>
      )}

      <AccordionSection
        title="Secret Paths"
        icon={<FileStack className="h-4 w-4 text-cyan-400" />}
        open={Boolean(panelOpen.secret_paths)}
        onToggle={() => togglePanel('secret_paths')}
        summary="Protected path exposure checks"
      >
        <SecretPathGuard serviceId={serviceId} disabled={offline} />
      </AccordionSection>

      <AccordionSection
        title="Run History"
        icon={<RefreshCw className="h-4 w-4 text-cyan-400" />}
        open={Boolean(panelOpen.run_history)}
        onToggle={() => togglePanel('run_history')}
        summary={runs.length > 0 ? `${runs.length} runs · latest ${new Date(runs[0].timestamp).toLocaleString()}` : 'No run history yet'}
      >
        {runs.length > 0 ? (
          <ul className="space-y-2">
            {runs.slice(0, 5).map((r) => (
              <li key={r.run_id} className="flex items-center justify-between text-sm">
                <span className="text-gray-500 font-mono text-xs">
                  {new Date(r.timestamp).toLocaleString()}
                </span>
                <StatusBadge status={r.status} />
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-gray-500">No run history captured yet.</div>
        )}
      </AccordionSection>

      {confirmOpen && confirmAction && ACTION_EXPLAIN[confirmAction] && (
        <ConfirmationModal
          open={confirmOpen}
          title={ACTION_EXPLAIN[confirmAction].title}
          willDo={ACTION_EXPLAIN[confirmAction].happens}
          willNotChange={ACTION_EXPLAIN[confirmAction].untouched}
          writesTo={ACTION_EXPLAIN[confirmAction].writesTo}
          preflight={confirmDetails?.preflight}
          followUp={confirmDetails?.followUp}
          commandPreview={confirmDetails?.commandPreview}
          confirmLabel={confirmDetails?.confirmLabel}
          onConfirm={handleConfirmAction}
          onCancel={() => {
            setConfirmOpen(false)
            setConfirmAction(null)
            setConfirmLocationId(null)
            setConfirmDetails(null)
          }}
        />
      )}
    </div>
  )
}
