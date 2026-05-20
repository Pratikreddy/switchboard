import { useEffect, useMemo, useState } from 'react'
import type { ReactElement } from 'react'
import {
  ChevronDown,
  ChevronRight,
  FolderPlus,
  LoaderCircle,
  RefreshCw,
  Search,
} from 'lucide-react'
import { addService, browseTree, getWorkspace, listProjects, listServers, updateProject } from '../api/client'
import type {
  CreateServiceRequest,
  ProjectManifest,
  RepoPolicy,
  RuntimeConfig,
  ScopeEntry,
  ServerRecord,
  Service,
  TreeNodeEntry,
} from '../types/switchboard'
import { isApiError } from '../types/switchboard'

interface Props {
  workspaceId: string
  serverIds: string[]
  disabled?: boolean
  onCreated: (service: Service) => void
}

interface TreeNodeState extends TreeNodeEntry {
  parent_path: string | null
}

type ScopeKind = ScopeEntry['kind']

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

function displayFromPath(path: string) {
  const clean = path.replace(/[\\/]+$/, '')
  const parts = clean.split(/[\\/]/).filter(Boolean)
  const tail = parts[parts.length - 1] ?? clean
  return tail
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function inferRepoPolicy(path: string): RepoPolicy {
  const token = path.toLowerCase()
  const secretHeavy = token.includes('lambda') || token.includes('secret') || token.includes('credential')
  return {
    repo_path: path,
    push_mode: secretHeavy ? 'blocked' : 'allowed',
    safety_profile: secretHeavy ? 'secret_heavy' : 'generic_python',
    allowed_branches: [],
    allowed_remotes: [],
  }
}

function uniqueScope(entries: ScopeEntry[]) {
  const seen = new Set<string>()
  return entries.filter((entry) => {
    const key = `${entry.kind}:${entry.path}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function parsePorts(value: string): number[] {
  return value
    .split(',')
    .map((token) => Number(token.trim()))
    .filter((port) => Number.isFinite(port) && port > 0 && port <= 65535)
}

function pathTypeForNode(node: TreeNodeState): ScopeEntry['path_type'] {
  return node.node_type === 'dir' ? 'dir' : 'file'
}

function TreeRow({
  node,
  level,
  selected,
  kind,
  expanded,
  loading,
  disabled,
  childPaths,
  onToggleExpand,
  onToggleSelected,
  onChangeKind,
  renderChild,
}: {
  node: TreeNodeState
  level: number
  selected: boolean
  kind: ScopeKind
  expanded: boolean
  loading: boolean
  disabled?: boolean
  childPaths: string[]
  onToggleExpand: (path: string) => void
  onToggleSelected: (path: string, checked: boolean) => void
  onChangeKind: (path: string, kind: ScopeKind) => void
  renderChild: (path: string, level: number) => ReactElement | null
}) {
  const indent = 12 + level * 18
  return (
    <div>
      <div
        className="grid grid-cols-[auto,auto,minmax(0,1fr),auto] items-center gap-3 border-b border-gray-800 px-3 py-2 text-sm"
        style={{ paddingLeft: indent }}
      >
        <button
          type="button"
          aria-label={expanded ? 'Collapse node' : 'Expand node'}
          aria-expanded={expanded}
          onClick={() => onToggleExpand(node.path)}
          disabled={!node.has_children || disabled}
          className="flex h-7 w-7 items-center justify-center rounded-md text-gray-400 hover:bg-gray-800 hover:text-white disabled:cursor-default disabled:opacity-40"
        >
          {loading ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : expanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </button>

        <input
          type="checkbox"
          checked={selected}
          onChange={(event) => onToggleSelected(node.path, event.target.checked)}
          className="h-4 w-4 rounded border-gray-600 bg-gray-950 text-cyan-500 focus:ring-cyan-500"
          disabled={disabled}
        />

        <div className="min-w-0">
          <div className="truncate font-mono text-xs text-gray-200">{node.path}</div>
          <div className="mt-1 flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-gray-500">
            <span>{node.node_type}</span>
            {node.has_children && <span>{expanded ? 'expanded' : 'collapsed'}</span>}
          </div>
        </div>

        <select
          value={kind}
          onChange={(event) => onChangeKind(node.path, event.target.value as ScopeKind)}
          className="rounded-lg border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-white outline-none focus:border-cyan-500"
          disabled={disabled}
        >
          <option value="repo">Repo</option>
          <option value="code">Code</option>
          <option value="doc">Doc</option>
          <option value="log">Log</option>
          <option value="exclude">Exclude</option>
        </select>
      </div>

      {expanded &&
        childPaths.map((childPath) => renderChild(childPath, level + 1))}
    </div>
  )
}

export function ProjectOnboardingPanel({ workspaceId, serverIds, disabled, onCreated }: Props) {
  const [open, setOpen] = useState(false)
  const [servers, setServers] = useState<ServerRecord[]>([])
  const [serverId, setServerId] = useState('')
  const [root, setRoot] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [serviceId, setServiceId] = useState('')
  const [nodesByPath, setNodesByPath] = useState<Record<string, TreeNodeState>>({})
  const [childPathsByParent, setChildPathsByParent] = useState<Record<string, string[]>>({})
  const [expandedPaths, setExpandedPaths] = useState<Record<string, boolean>>({})
  const [selectionMap, setSelectionMap] = useState<Record<string, boolean>>({})
  const [kindMap, setKindMap] = useState<Record<string, ScopeKind>>({})
  const [loadingPath, setLoadingPath] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [rootPathLoaded, setRootPathLoaded] = useState<string | null>(null)
  const [expectedPorts, setExpectedPorts] = useState('')
  const [healthcheckCommand, setHealthcheckCommand] = useState('')
  const [runCommandHint, setRunCommandHint] = useState('')
  const [monitoringMode, setMonitoringMode] = useState<RuntimeConfig['monitoring_mode']>('manual')
  const [runtimeNotes, setRuntimeNotes] = useState('')
  const [executionMode, setExecutionMode] = useState<CreateServiceRequest['execution_mode']>('networked')
  const [projects, setProjects] = useState<ProjectManifest[]>([])
  const [workspaceServices, setWorkspaceServices] = useState<Service[]>([])
  const [workspaceServicesLoaded, setWorkspaceServicesLoaded] = useState(false)
  const [selectedProjectId, setSelectedProjectId] = useState('')

  useEffect(() => {
    if (disabled) return
    listServers().then((result) => {
      if (isApiError(result)) return
      setServers(result)
      if (!serverId) {
        const first = result.find((server) => serverIds.includes(server.server_id)) ?? result[0]
        if (first) setServerId(first.server_id)
      }
    })
  }, [disabled, serverId, serverIds])

  useEffect(() => {
    if (disabled || !open) return
    let cancelled = false
    Promise.all([listProjects(workspaceId), getWorkspace(workspaceId)]).then(([projectResult, workspaceResult]) => {
      if (cancelled) return
      const messages: string[] = []
      if (isApiError(projectResult)) {
        setProjects([])
        messages.push(projectResult.message)
      } else {
        setProjects(projectResult.projects)
      }
      if (isApiError(workspaceResult)) {
        setWorkspaceServices([])
        setWorkspaceServicesLoaded(false)
        messages.push(workspaceResult.message)
      } else {
        setWorkspaceServices(workspaceResult.services)
        setWorkspaceServicesLoaded(true)
      }
      if (messages.length > 0) setMessage(messages.join(' '))
    })
    return () => {
      cancelled = true
    }
  }, [disabled, open, workspaceId])

  useEffect(() => {
    if (selectedProjectId && !projects.some((project) => project.project_id === selectedProjectId)) {
      setSelectedProjectId('')
    }
  }, [projects, selectedProjectId])

  const availableServers = useMemo(() => {
    if (serverIds.length === 0) return servers
    const filtered = servers.filter((server) => serverIds.includes(server.server_id))
    return filtered.length > 0 ? filtered : servers
  }, [serverIds, servers])

  const rootNode = rootPathLoaded ? nodesByPath[rootPathLoaded] ?? null : null
  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  )

  function resetTreeState() {
    setNodesByPath({})
    setChildPathsByParent({})
    setExpandedPaths({})
    setSelectionMap({})
    setKindMap({})
    setRootPathLoaded(null)
  }

  function setNodeBatch(parentPath: string | null, currentNode: TreeNodeEntry, entries: TreeNodeEntry[]) {
    setNodesByPath((current) => {
      const next = { ...current }
      next[currentNode.path] = {
        ...currentNode,
        parent_path: parentPath,
      }
      for (const entry of entries) {
        next[entry.path] = {
          ...entry,
          parent_path: currentNode.path,
        }
      }
      return next
    })
    setChildPathsByParent((current) => ({
      ...current,
      [currentNode.path]: entries.map((entry) => entry.path),
    }))
    setKindMap((current) => {
      const next = { ...current }
      if (!next[currentNode.path]) next[currentNode.path] = currentNode.suggested_kind
      for (const entry of entries) {
        if (!next[entry.path]) next[entry.path] = entry.suggested_kind
      }
      return next
    })
  }

  async function loadNode(targetPath?: string, expandAfter = true) {
    if (!serverId || !root.trim()) {
      setMessage('Choose a server and root path first.')
      return
    }
    const requestRoot = root.trim()
    const nodePath = targetPath ?? requestRoot
    setLoadingPath(nodePath)
    const result = await browseTree({
      server_id: serverId,
      root: requestRoot,
      node_path: targetPath,
    })
    setLoadingPath(null)
    if (isApiError(result) || !result.current_node) {
      if (!targetPath) resetTreeState()
      setMessage(isApiError(result) ? result.message : result.message ?? `Tree load failed: ${result.status}.`)
      return
    }
    const currentNode = result.current_node
    setNodeBatch(
      currentNode.path === requestRoot ? null : nodesByPath[currentNode.path]?.parent_path ?? null,
      currentNode,
      result.entries,
    )
    if (!rootPathLoaded || currentNode.path === requestRoot) {
      setRootPathLoaded(currentNode.path)
      setExpandedPaths((current) => ({ ...current, [currentNode.path]: true }))
      const defaultName = displayFromPath(currentNode.path)
      if (!displayName) setDisplayName(defaultName)
      if (!serviceId) setServiceId(slugify(defaultName))
    } else if (expandAfter) {
      setExpandedPaths((current) => ({ ...current, [currentNode.path]: true }))
    }
    setMessage(`Loaded ${result.entries.length} entries from ${currentNode.path}.`)
  }

  function isSelected(path: string): boolean {
    const explicit = selectionMap[path]
    if (explicit !== undefined) return explicit
    const node = nodesByPath[path]
    if (!node?.parent_path) return true
    return isSelected(node.parent_path)
  }

  function currentKind(path: string): ScopeKind {
    return kindMap[path] ?? nodesByPath[path]?.suggested_kind ?? 'repo'
  }

  function cascadeSelection(path: string, checked: boolean, next: Record<string, boolean>) {
    next[path] = checked
    for (const childPath of childPathsByParent[path] ?? []) {
      cascadeSelection(childPath, checked, next)
    }
  }

  function cascadeKind(path: string, kind: ScopeKind, next: Record<string, ScopeKind>) {
    next[path] = kind
    for (const childPath of childPathsByParent[path] ?? []) {
      cascadeKind(childPath, kind, next)
    }
  }

  function handleToggleSelected(path: string, checked: boolean) {
    setSelectionMap((current) => {
      const next = { ...current }
      cascadeSelection(path, checked, next)
      return next
    })
  }

  function handleChangeKind(path: string, kind: ScopeKind) {
    setKindMap((current) => {
      const next = { ...current }
      cascadeKind(path, kind, next)
      return next
    })
  }

  async function handleToggleExpand(path: string) {
    const node = nodesByPath[path]
    if (!node || node.node_type !== 'dir' || !node.has_children) return
    if (!childPathsByParent[path]) {
      await loadNode(path)
      return
    }
    setExpandedPaths((current) => ({ ...current, [path]: !current[path] }))
  }

  function resetSuggestions() {
    setSelectionMap({})
    setKindMap((current) => {
      const next: Record<string, ScopeKind> = {}
      Object.values(nodesByPath).forEach((node) => {
        next[node.path] = node.suggested_kind
      })
      return { ...current, ...next }
    })
  }

  function renderNode(path: string, level: number): ReactElement | null {
    const node = nodesByPath[path]
    if (!node) return null
    return (
      <TreeRow
        key={path}
        node={node}
        level={level}
        selected={isSelected(path)}
        kind={currentKind(path)}
        expanded={Boolean(expandedPaths[path])}
        loading={loadingPath === path}
        disabled={disabled}
        childPaths={childPathsByParent[path] ?? []}
        onToggleExpand={handleToggleExpand}
        onToggleSelected={handleToggleSelected}
        onChangeKind={handleChangeKind}
        renderChild={renderNode}
      />
    )
  }

  function buildScopeEntries(): ScopeEntry[] {
    if (!rootNode) return []
    const entries: ScopeEntry[] = []

    const visit = (path: string, parentPath: string | null) => {
      const node = nodesByPath[path]
      if (!node) return
      const selected = isSelected(path)
      const kind = currentKind(path)
      const parentSelected = parentPath ? isSelected(parentPath) : false
      const parentKind = parentPath ? currentKind(parentPath) : null

      if (parentPath === null) {
        if (selected) {
          entries.push({
            kind,
            path: node.path,
            path_type: pathTypeForNode(node),
            source: 'user_added',
            enabled: true,
          })
        }
      } else if (!selected && parentSelected) {
        entries.push({
          kind: 'exclude',
          path: node.path,
          path_type: pathTypeForNode(node),
          source: 'user_added',
          enabled: true,
        })
      } else if (selected && (!parentSelected || parentKind !== kind)) {
        entries.push({
          kind,
          path: node.path,
          path_type: pathTypeForNode(node),
          source: 'user_added',
          enabled: true,
        })
      }

      for (const childPath of childPathsByParent[path] ?? []) {
        visit(childPath, path)
      }
    }

    visit(rootNode.path, null)
    return uniqueScope(entries)
  }

  async function handleCreate() {
    if (!rootNode || !serverId || !root.trim()) {
      setMessage('Load a root path first.')
      return
    }
    const nextDisplayName = displayName.trim() || displayFromPath(rootNode.path)
    const nextServiceId = slugify(serviceId || nextDisplayName)
    const scopeEntries = buildScopeEntries()
    const repoPaths = scopeEntries.filter((entry) => entry.kind === 'repo').map((entry) => entry.path)
    const docsPaths = scopeEntries.filter((entry) => entry.kind === 'doc').map((entry) => entry.path)
    const logPaths = scopeEntries.filter((entry) => entry.kind === 'log').map((entry) => entry.path)
    const excludeGlobs = scopeEntries.filter((entry) => entry.kind === 'exclude').map((entry) => entry.path)

    if (!nextServiceId || scopeEntries.filter((entry) => entry.kind !== 'exclude').length === 0) {
      setMessage('Select at least one included folder or file before saving.')
      return
    }

    const payload: CreateServiceRequest = {
      service_id: nextServiceId,
      display_name: nextDisplayName,
      execution_mode: executionMode,
      locations: [
        {
          location_id: `${nextServiceId}-${serverId}-primary`,
          server_id: serverId,
          access_mode:
            availableServers.find((server) => server.server_id === serverId)?.connection_type ?? 'ssh',
          root: root.trim(),
          role: 'primary',
          is_primary: true,
          path_aliases: [],
          runtime: {
            expected_ports: parsePorts(expectedPorts),
            healthcheck_command: healthcheckCommand.trim(),
            run_command_hint: runCommandHint.trim(),
            monitoring_mode: monitoringMode,
            notes: runtimeNotes.trim(),
          },
        },
      ],
      scope_entries: scopeEntries,
      repo_paths: repoPaths,
      docs_paths: docsPaths,
      log_paths: logPaths,
      allowed_git_pull_paths: repoPaths,
      exclude_globs: excludeGlobs,
      repo_policies: repoPaths.map((path) => inferRepoPolicy(path)),
    }

    setSaving(true)
    const result = await addService(workspaceId, payload)
    if (isApiError(result)) {
      setSaving(false)
      setMessage(result.message)
      return
    }
    let completionMessage = `Created ${result.display_name}.`
    if (selectedProject) {
      const knownServiceIds = new Set(workspaceServices.map((service) => service.service_id))
      knownServiceIds.add(result.service_id)
      const missingExistingRefs = workspaceServicesLoaded
        ? (selectedProject.service_ids ?? []).filter((serviceId) => !knownServiceIds.has(serviceId))
        : []
      if (missingExistingRefs.length > 0) {
        completionMessage = `Created ${result.display_name}, but project assignment is blocked by missing service references: ${missingExistingRefs.join(', ')}.`
      } else {
        const nextServiceIds = Array.from(new Set([...(selectedProject.service_ids ?? []), result.service_id]))
        const assignResult = await updateProject(selectedProject.project_id, { service_ids: nextServiceIds })
        if (isApiError(assignResult)) {
          completionMessage = `Created ${result.display_name}, but project assignment failed: ${assignResult.message}`
        } else {
          setProjects((current) =>
            current.map((project) =>
              project.project_id === assignResult.project.project_id ? assignResult.project : project,
            ),
          )
          completionMessage = `Created and assigned ${result.display_name} to ${assignResult.project.display_name}.`
        }
      }
    }
    setSaving(false)
    onCreated(result)
    setMessage(completionMessage)
    setOpen(false)
    setDisplayName('')
    setServiceId('')
    setRoot('')
    setExpectedPorts('')
    setHealthcheckCommand('')
    setRunCommandHint('')
    setMonitoringMode('manual')
    setRuntimeNotes('')
    setExecutionMode('networked')
    setSelectedProjectId('')
    resetTreeState()
  }

  return (
    <section className="rounded-2xl border border-gray-800 bg-gray-900">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <div>
          <div className="text-sm font-medium text-white">Add Service</div>
          <div className="text-xs text-gray-500">
            Open one project path, inspect everything inside it, and save only the scope you want.
          </div>
        </div>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-200 transition-colors hover:border-cyan-500 hover:text-white"
        >
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {open ? 'Collapse' : 'Expand'}
        </button>
      </div>

      {open && (
        <div className="border-t border-gray-800 px-4 py-4">
          <div className="mb-4 rounded-xl border border-cyan-900/30 bg-cyan-950/20 px-4 py-3 text-sm text-cyan-100">
            This creates one tracked service from a filesystem root. Assign it to a project now or leave it at company root.
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.3fr,1fr,1.2fr,auto]">
            <label className="text-sm text-gray-300">
              <div className="mb-1">Tracked service name</div>
              <input
                value={displayName}
                onChange={(event) => {
                  const next = event.target.value
                  setDisplayName(next)
                  if (!serviceId) setServiceId(slugify(next))
                }}
                className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                placeholder="AI Chat"
                disabled={disabled}
              />
            </label>
            <label className="text-sm text-gray-300">
              <div className="mb-1">Tracked service id</div>
              <input
                value={serviceId}
                onChange={(event) => setServiceId(slugify(event.target.value))}
                className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                placeholder="aichat"
                disabled={disabled}
              />
            </label>
            <label className="text-sm text-gray-300">
              <div className="mb-1">Server</div>
              <select
                value={serverId}
                onChange={(event) => setServerId(event.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                disabled={disabled}
              >
                <option value="">Select a server</option>
                {availableServers.map((server) => (
                  <option key={server.server_id} value={server.server_id}>
                    {server.name} · {server.host}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex items-end">
              <button
                onClick={() => loadNode()}
                disabled={disabled || loadingPath !== null}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-black transition-colors hover:bg-gray-200 disabled:opacity-50"
              >
                {loadingPath ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                Open path
              </button>
            </div>
          </div>

          <label className="mt-3 block text-sm text-gray-300">
            <div className="mb-1">Root path</div>
            <input
              value={root}
              onChange={(event) => {
                setRoot(event.target.value)
                resetTreeState()
              }}
              className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
              placeholder="/home/pesu/aichat"
              disabled={disabled}
            />
          </label>

          <label className="mt-3 block text-sm text-gray-300">
            <div className="mb-1">Assign to Project</div>
            <select
              value={selectedProjectId}
              onChange={(event) => setSelectedProjectId(event.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
              disabled={disabled || projects.length === 0}
            >
              <option value="">Company root / unassigned service</option>
              {projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.display_name} ({project.project_id})
                </option>
              ))}
            </select>
            {projects.length === 0 && (
              <div className="mt-1 text-xs text-gray-500">No projects available yet.</div>
            )}
          </label>

          <div className="mt-4 rounded-xl border border-gray-800 bg-gray-950 p-4">
            <div className="text-sm font-medium text-white">Runtime Setup</div>
            <div className="mt-1 text-xs text-gray-500">
              Store the expected ports, health check command, and run-command hint for this location.
            </div>

            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <label className="text-sm text-gray-300">
                <div className="mb-1">Execution mode</div>
                <select
                  value={executionMode}
                  onChange={(event) => setExecutionMode(event.target.value as CreateServiceRequest['execution_mode'])}
                  className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                  disabled={disabled}
                >
                  <option value="networked">networked</option>
                  <option value="batch">batch</option>
                  <option value="lambda">lambda</option>
                  <option value="docs_only">docs_only</option>
                </select>
              </label>
              <label className="text-sm text-gray-300">
                <div className="mb-1">Expected ports</div>
                <input
                  value={expectedPorts}
                  onChange={(event) => setExpectedPorts(event.target.value)}
                  className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                  placeholder="8000, 8506"
                  disabled={disabled}
                />
              </label>
              <label className="text-sm text-gray-300">
                <div className="mb-1">Monitoring mode</div>
                <select
                  value={monitoringMode}
                  onChange={(event) => setMonitoringMode(event.target.value as RuntimeConfig['monitoring_mode'])}
                  className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                  disabled={disabled}
                >
                  <option value="manual">manual</option>
                  <option value="detect">detect</option>
                  <option value="node_managed">node_managed</option>
                </select>
              </label>
            </div>

            <label className="mt-3 block text-sm text-gray-300">
              <div className="mb-1">Health check command</div>
              <input
                value={healthcheckCommand}
                onChange={(event) => setHealthcheckCommand(event.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                placeholder="curl -fsS http://127.0.0.1:8000/health"
                disabled={disabled}
              />
            </label>

            <label className="mt-3 block text-sm text-gray-300">
              <div className="mb-1">Run command hint</div>
              <input
                value={runCommandHint}
                onChange={(event) => setRunCommandHint(event.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                placeholder="uvicorn main:app --host 0.0.0.0 --port 8000"
                disabled={disabled}
              />
            </label>

            <label className="mt-3 block text-sm text-gray-300">
              <div className="mb-1">Runtime notes</div>
              <textarea
                value={runtimeNotes}
                onChange={(event) => setRuntimeNotes(event.target.value)}
                className="min-h-24 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                placeholder="Manual runtime notes for this location."
                disabled={disabled}
              />
            </label>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => {
                if (!rootNode) return
                handleToggleSelected(rootNode.path, true)
              }}
              className="rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-200 transition-colors hover:border-cyan-500"
              disabled={disabled || !rootNode}
            >
              Select all
            </button>
            <button
              type="button"
              onClick={() => {
                if (!rootNode) return
                handleToggleSelected(rootNode.path, false)
              }}
              className="rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-200 transition-colors hover:border-cyan-500"
              disabled={disabled || !rootNode}
            >
              Clear all
            </button>
            <button
              type="button"
              onClick={resetSuggestions}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-200 transition-colors hover:border-cyan-500"
              disabled={disabled || !rootNode}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Reset suggestions
            </button>
            <div className="ml-auto text-xs text-gray-500">{message || 'Tree loads lazily. Everything starts selected.'}</div>
          </div>

          <div className="mt-4 rounded-xl border border-gray-800 bg-gray-950">
            {!rootNode ? (
              <div className="px-4 py-8 text-sm text-gray-500">
                Open a root path to browse folders and files.
              </div>
            ) : (
              <div role="tree" aria-label="Service scope tree" className="max-h-[34rem] overflow-auto">
                {renderNode(rootNode.path, 0)}
              </div>
            )}
          </div>

          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="text-sm text-gray-400">
              Save the selected folders/files now. You can later pull full folders and exclude nested dump paths.
            </div>
            <button
              onClick={handleCreate}
              disabled={disabled || saving || !rootNode}
              className="inline-flex items-center gap-2 rounded-lg bg-cyan-500/90 px-4 py-2 text-sm font-medium text-black transition-colors hover:bg-cyan-400 disabled:opacity-50"
            >
              {saving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <FolderPlus className="h-4 w-4" />}
              {saving ? 'Saving' : 'Create service'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
