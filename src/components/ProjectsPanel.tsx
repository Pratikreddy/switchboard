import React, { useEffect, useMemo, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  FolderGit2,
  Pencil,
  Plus,
  Save,
  X,
} from 'lucide-react'
import {
  createProject,
  createProjectEnvironment,
  listProjects,
  updateProject,
  updateProjectEnvironment,
} from '../api/client'
import { isApiError } from '../types/switchboard'
import type {
  ProjectDeploymentRef,
  ProjectEnvironmentKind,
  ProjectEnvironmentView,
  ProjectManifest,
  Service,
} from '../types/switchboard'

interface Props {
  workspaceId: string
  offline: boolean
  workspaceName?: string
  workspaceNotes?: string
  services: Service[]
  onOpenEnvironmentLab: (environmentId: string) => void
}

type ProjectFormState = {
  project_id: string
  display_name: string
  parent_project_id: string
  service_ids: string
  tags: string
  notes: string
}

type EnvironmentFormState = {
  environment_id: string
  display_name: string
  kind: ProjectEnvironmentKind
  tags: string
  notes: string
  deployments: ProjectDeploymentRef[]
}

const EMPTY_PROJECT_FORM: ProjectFormState = {
  project_id: '',
  display_name: '',
  parent_project_id: '',
  service_ids: '',
  tags: '',
  notes: '',
}

const EMPTY_ENV_FORM: EnvironmentFormState = {
  environment_id: '',
  display_name: '',
  kind: 'custom',
  tags: '',
  notes: '',
  deployments: [],
}

function blankDeployment(): ProjectDeploymentRef {
  return {
    service_id: '',
    location_id: '',
    server_id: '',
    root: '',
    version: '',
    notes: '',
  }
}

function parseCsv(value: string): string[] {
  return value.split(',').map((entry) => entry.trim()).filter(Boolean)
}

function normalizeParentProjectId(value: string): string | null {
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

export function ProjectsPanel({ workspaceId, offline, workspaceName, workspaceNotes, services, onOpenEnvironmentLab }: Props) {
  const [projects, setProjects] = useState<ProjectManifest[]>([])
  const [environments, setEnvironments] = useState<ProjectEnvironmentView[]>([])
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openProjects, setOpenProjects] = useState<Record<string, boolean>>({})
  const [openProjectAdvanced, setOpenProjectAdvanced] = useState<Record<string, boolean>>({})
  const [openEnvironments, setOpenEnvironments] = useState<Record<string, boolean>>({})

  const [addingProject, setAddingProject] = useState(false)
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null)
  const [projectForm, setProjectForm] = useState<ProjectFormState>(EMPTY_PROJECT_FORM)

  const [addingEnvironmentFor, setAddingEnvironmentFor] = useState<string | null>(null)
  const [editingEnvironmentId, setEditingEnvironmentId] = useState<string | null>(null)
  const [environmentForm, setEnvironmentForm] = useState<EnvironmentFormState>(EMPTY_ENV_FORM)
  const [serviceFilter, setServiceFilter] = useState('')

  useEffect(() => {
    if (offline || !expanded) return
    void load()
  }, [expanded, offline, workspaceId])

  async function load() {
    setLoading(true)
    setError(null)
    const result = await listProjects(workspaceId)
    setLoading(false)
    if (isApiError(result)) {
      setError(result.message)
      return
    }
    setProjects(result.projects)
    setEnvironments(result.environments ?? [])
  }

  const childProjectsByParent = useMemo(() => {
    const map: Record<string, ProjectManifest[]> = {}
    for (const project of projects) {
      const parentId = project.parent_project_id || ''
      if (!map[parentId]) map[parentId] = []
      map[parentId].push(project)
    }
    return map
  }, [projects])

  const environmentsByProject = useMemo(() => {
    const map: Record<string, ProjectEnvironmentView[]> = {}
    for (const environment of environments) {
      if (!map[environment.project_id]) map[environment.project_id] = []
      map[environment.project_id].push(environment)
    }
    return map
  }, [environments])

  const rootProjects = childProjectsByParent[''] ?? []
  const serviceOwnerById = useMemo(() => {
    const map = new Map<string, string>()
    for (const project of projects) {
      for (const serviceId of project.service_ids ?? []) {
        map.set(serviceId, project.project_id)
      }
    }
    return map
  }, [projects])
  const projectNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const project of projects) {
      map.set(project.project_id, project.display_name)
    }
    return map
  }, [projects])
  const servicesById = useMemo(() => {
    const map = new Map<string, Service>()
    for (const service of services) {
      map.set(service.service_id, service)
    }
    return map
  }, [services])
  const unassignedServiceCount = useMemo(
    () => services.filter((service) => !serviceOwnerById.has(service.service_id)).length,
    [serviceOwnerById, services],
  )
  const projectServiceIds = useMemo(() => parseCsv(projectForm.service_ids), [projectForm.service_ids])
  const selectableParentProjects = useMemo(
    () => projects.filter((project) => project.project_id !== editingProjectId),
    [editingProjectId, projects],
  )
  const selectableServices = useMemo(
    () => services,
    [services],
  )

  function resetProjectForm() {
    setAddingProject(false)
    setEditingProjectId(null)
    setProjectForm(EMPTY_PROJECT_FORM)
    setServiceFilter('')
  }

  function resetEnvironmentForm() {
    setAddingEnvironmentFor(null)
    setEditingEnvironmentId(null)
    setEnvironmentForm(EMPTY_ENV_FORM)
  }

  function beginAddProject() {
    resetEnvironmentForm()
    setAddingProject(true)
    setEditingProjectId(null)
    setProjectForm(EMPTY_PROJECT_FORM)
    setError(null)
  }

  function beginEditProject(project: ProjectManifest) {
    resetEnvironmentForm()
    setAddingProject(false)
    setEditingProjectId(project.project_id)
    setProjectForm({
      project_id: project.project_id,
      display_name: project.display_name,
      parent_project_id: project.parent_project_id || '',
      service_ids: (project.service_ids ?? []).join(', '),
      tags: (project.tags ?? []).join(', '),
      notes: project.notes ?? '',
    })
    setError(null)
  }

  function toggleProjectService(serviceId: string) {
    setProjectForm((current) => {
      const selected = parseCsv(current.service_ids)
      const next = selected.includes(serviceId)
        ? selected.filter((candidate) => candidate !== serviceId)
        : [...selected, serviceId]
      return { ...current, service_ids: next.join(', ') }
    })
  }

  function addProjectService(serviceId: string) {
    if (!serviceId) return
    setProjectForm((current) => {
      const existing = new Set(parseCsv(current.service_ids))
      existing.add(serviceId)
      return { ...current, service_ids: Array.from(existing).join(', ') }
    })
  }

  function dropProjectServiceSelection(serviceId: string) {
    setProjectForm((current) => ({
      ...current,
      service_ids: parseCsv(current.service_ids)
        .filter((candidate) => candidate !== serviceId)
        .join(', '),
    }))
  }

  const availableProjectServices = useMemo(
    () => selectableServices.filter((service) => !projectServiceIds.includes(service.service_id)),
    [projectServiceIds, selectableServices],
  )
  const visibleSelectableServices = useMemo(() => {
    const token = serviceFilter.trim().toLowerCase()
    if (!token) return selectableServices
    return selectableServices.filter((service) =>
      `${service.display_name} ${service.service_id} ${service.execution_mode}`.toLowerCase().includes(token),
    )
  }, [selectableServices, serviceFilter])

  function projectOwnerLabel(serviceId: string, selected: boolean) {
    if (selected) return 'Selected for this project'
    const ownerId = serviceOwnerById.get(serviceId)
    if (!ownerId) return 'Unassigned'
    return `Owned by ${projectNameById.get(ownerId) ?? ownerId}`
  }

  function projectMoveHint(serviceId: string, selected: boolean) {
    const ownerId = serviceOwnerById.get(serviceId)
    if (!selected || !ownerId || ownerId === editingProjectId) return ''
    return `Will move from ${projectNameById.get(ownerId) ?? ownerId}`
  }

  function beginAddEnvironment(projectId: string) {
    resetProjectForm()
    setAddingEnvironmentFor(projectId)
    setEditingEnvironmentId(null)
    setEnvironmentForm({
      ...EMPTY_ENV_FORM,
      kind: 'test',
      deployments: [blankDeployment()],
    })
    setOpenProjects((current) => ({ ...current, [projectId]: true }))
    setOpenProjectAdvanced((current) => ({ ...current, [projectId]: true }))
    setError(null)
  }

  function beginEditEnvironment(environment: ProjectEnvironmentView) {
    resetProjectForm()
    setAddingEnvironmentFor(environment.project_id)
    setEditingEnvironmentId(environment.environment_id)
    setEnvironmentForm({
      environment_id: environment.environment_id,
      display_name: environment.display_name,
      kind: environment.kind,
      tags: (environment.tags ?? []).join(', '),
      notes: environment.notes ?? '',
      deployments:
        environment.deployments?.map((deployment) => ({
          service_id: deployment.service_id,
          location_id: deployment.location_id ?? '',
          server_id: deployment.server_id ?? '',
          root: deployment.root ?? '',
          version: deployment.version ?? '',
          notes: deployment.notes ?? '',
        })) ?? [],
    })
    setOpenProjects((current) => ({ ...current, [environment.project_id]: true }))
    setOpenProjectAdvanced((current) => ({ ...current, [environment.project_id]: true }))
    setOpenEnvironments((current) => ({ ...current, [environment.environment_id]: true }))
    setError(null)
  }

  async function saveProject() {
    if (!projectForm.project_id.trim() || !projectForm.display_name.trim()) {
      setError('Project ID and display name are required.')
      return
    }
    const payload = {
      project_id: projectForm.project_id.trim(),
      display_name: projectForm.display_name.trim(),
      parent_project_id: normalizeParentProjectId(projectForm.parent_project_id),
      service_ids: parseCsv(projectForm.service_ids),
      tags: projectForm.tags.split(',').map((value) => value.trim()).filter(Boolean),
      notes: projectForm.notes.trim(),
    }
    const result = addingProject
      ? await createProject(workspaceId, payload)
      : await updateProject(editingProjectId!, payload)
    if (isApiError(result)) {
      setError(result.message)
      return
    }
    resetProjectForm()
    await load()
  }

  async function saveEnvironment() {
    if (!addingEnvironmentFor) return
    if (!environmentForm.environment_id.trim() || !environmentForm.display_name.trim()) {
      setError('Environment ID and display name are required.')
      return
    }
    const payload = {
      environment_id: environmentForm.environment_id.trim(),
      display_name: environmentForm.display_name.trim(),
      kind: environmentForm.kind,
      tags: environmentForm.tags.split(',').map((value) => value.trim()).filter(Boolean),
      notes: environmentForm.notes.trim(),
      deployments: environmentForm.deployments
        .filter((deployment) => deployment.service_id?.trim())
        .map((deployment) => ({
          service_id: deployment.service_id.trim(),
          location_id: deployment.location_id?.trim() || undefined,
          server_id: deployment.server_id?.trim() || undefined,
          root: deployment.root?.trim() || undefined,
          version: deployment.version?.trim() || '',
          notes: deployment.notes?.trim() || '',
        })),
    }
    const result = editingEnvironmentId
      ? await updateProjectEnvironment(editingEnvironmentId, payload)
      : await createProjectEnvironment(addingEnvironmentFor, payload)
    if (isApiError(result)) {
      setError(result.message)
      return
    }
    resetEnvironmentForm()
    await load()
  }

  function updateDeployment(index: number, field: keyof ProjectDeploymentRef, value: string) {
    setEnvironmentForm((current) => ({
      ...current,
      deployments: current.deployments.map((deployment, deploymentIndex) =>
        deploymentIndex === index ? { ...deployment, [field]: value } : deployment,
      ),
    }))
  }

  function renderEnvironmentForm(projectId: string) {
    if (addingEnvironmentFor !== projectId) return null
    return (
      <div className="mt-3 rounded-xl border border-cyan-900/30 bg-gray-950 p-4">
        <div className="mb-3 text-sm font-medium text-gray-200">
          {editingEnvironmentId ? 'Edit Environment' : 'Add Environment'}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-xs text-gray-400">
            Environment ID
            <input
              value={environmentForm.environment_id}
              onChange={(event) => setEnvironmentForm((current) => ({ ...current, environment_id: event.target.value }))}
              className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
            />
          </label>
          <label className="text-xs text-gray-400">
            Display Name
            <input
              value={environmentForm.display_name}
              onChange={(event) => setEnvironmentForm((current) => ({ ...current, display_name: event.target.value }))}
              className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
            />
          </label>
          <label className="text-xs text-gray-400">
            Kind
            <select
              value={environmentForm.kind}
              onChange={(event) => setEnvironmentForm((current) => ({ ...current, kind: event.target.value as ProjectEnvironmentKind }))}
              className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
            >
              <option value="dev">dev</option>
              <option value="test">test</option>
              <option value="staging">staging</option>
              <option value="qa">qa</option>
              <option value="prod">prod</option>
              <option value="custom">custom</option>
            </select>
          </label>
          <label className="text-xs text-gray-400">
            Tags
            <input
              value={environmentForm.tags}
              onChange={(event) => setEnvironmentForm((current) => ({ ...current, tags: event.target.value }))}
              className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
              placeholder="test, vpn, local"
            />
          </label>
        </div>
        <label className="mt-3 block text-xs text-gray-400">
          Notes
          <textarea
            value={environmentForm.notes}
            onChange={(event) => setEnvironmentForm((current) => ({ ...current, notes: event.target.value }))}
            className="mt-1 min-h-20 w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
            placeholder="What makes this environment different, who uses it, or what to watch for."
          />
        </label>

        <div className="mt-4">
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Deployments</div>
            <button
              type="button"
              onClick={() =>
                setEnvironmentForm((current) => ({
                  ...current,
                  deployments: [...current.deployments, blankDeployment()],
                }))
              }
              className="rounded-lg border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:border-cyan-500 hover:text-white"
            >
              Add deployment
            </button>
          </div>
          <div className="mt-3 space-y-3">
            {environmentForm.deployments.map((deployment, index) => (
              <div key={`${index}:${deployment.service_id}`} className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
                <div className="grid gap-3 md:grid-cols-3">
                  <label className="text-xs text-gray-400">
                    Service
                    <select
                      value={deployment.service_id}
                      onChange={(event) => updateDeployment(index, 'service_id', event.target.value)}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                    >
                      <option value="">Select service</option>
                      {services.map((service) => (
                        <option key={service.service_id} value={service.service_id}>
                          {service.display_name} ({service.execution_mode})
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs text-gray-400">
                    Location ID
                    <input
                      value={deployment.location_id ?? ''}
                      onChange={(event) => updateDeployment(index, 'location_id', event.target.value)}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                    />
                  </label>
                  <label className="text-xs text-gray-400">
                    Server ID
                    <input
                      value={deployment.server_id ?? ''}
                      onChange={(event) => updateDeployment(index, 'server_id', event.target.value)}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                    />
                  </label>
                  <label className="text-xs text-gray-400">
                    Root
                    <input
                      value={deployment.root ?? ''}
                      onChange={(event) => updateDeployment(index, 'root', event.target.value)}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                    />
                  </label>
                  <label className="text-xs text-gray-400">
                    Version
                    <input
                      value={deployment.version ?? ''}
                      onChange={(event) => updateDeployment(index, 'version', event.target.value)}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                    />
                  </label>
                  <label className="text-xs text-gray-400">
                    Notes
                    <input
                      value={deployment.notes ?? ''}
                      onChange={(event) => updateDeployment(index, 'notes', event.target.value)}
                      className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                    />
                  </label>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button onClick={resetEnvironmentForm} className="px-3 py-1.5 text-xs text-gray-400 hover:text-white">
            Cancel
          </button>
          <button
            onClick={() => void saveEnvironment()}
            className="inline-flex items-center gap-1 rounded-lg bg-cyan-600 px-3 py-1.5 text-xs text-white hover:bg-cyan-500"
          >
            <Save className="h-3 w-3" />
            Save Environment
          </button>
        </div>
      </div>
    )
  }

  function renderEnvironment(environment: ProjectEnvironmentView) {
    const open = Boolean(openEnvironments[environment.environment_id])
    const pull = environment.pull_summary
    const depCount = environment.dependency_summary?.dependencies.length ?? 0
    const crossDepCount = environment.dependency_summary?.cross_dependencies.length ?? 0
    const composition = environment.dependency_summary?.composition
    return (
      <div key={environment.environment_id} className="rounded-xl border border-gray-800 bg-gray-950/70">
        <button
          type="button"
          onClick={() => setOpenEnvironments((current) => ({ ...current, [environment.environment_id]: !current[environment.environment_id] }))}
          className="flex w-full items-start justify-between gap-3 p-3 text-left"
        >
          <div>
            <div className="text-sm font-medium text-gray-100">{environment.display_name}</div>
            <div className="mt-1 text-[10px] font-mono text-gray-500">{environment.environment_id}</div>
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.14em]">
              <span className="rounded-full border border-cyan-900/30 bg-cyan-950/20 px-2 py-1 text-cyan-200">{environment.kind}</span>
              <span className="rounded-full border border-gray-800 px-2 py-1 text-gray-400">{environment.deployments.length} deployments</span>
              <span className="rounded-full border border-gray-800 px-2 py-1 text-gray-400">{environment.api_flow_count ?? 0} flows</span>
              <span className="rounded-full border border-amber-900/30 bg-amber-950/20 px-2 py-1 text-amber-200">
                {pull?.added_count ?? 0}+ / {pull?.removed_count ?? 0}- / {pull?.changed_count ?? 0}~
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right text-[11px] text-gray-500">
              <div>{depCount} deps</div>
              <div>{crossDepCount} cross</div>
            </div>
            {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
          </div>
        </button>
        {open && (
          <div className="border-t border-gray-800 p-3">
            <div className="mb-3 text-sm text-gray-300">
              {environment.notes || 'No environment notes yet.'}
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
                <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Dependency Summary</div>
                <div className="mt-2 text-xs text-gray-300">
                  Direct: {depCount} · Cross: {crossDepCount}
                </div>
                {composition && (
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                    {composition.language_percentages.slice(0, 3).map((item) => (
                      <span key={item.name} className="rounded-full border border-gray-800 px-2 py-1 text-gray-300">
                        {item.name} {item.percentage}%
                      </span>
                    ))}
                    <span className="rounded-full border border-cyan-900/40 bg-cyan-950/20 px-2 py-1 text-cyan-200">
                      AI {composition.ai_percentage}%
                    </span>
                    <span className="rounded-full border border-gray-800 px-2 py-1 text-gray-300">
                      LLM {composition.llm_percentage}%
                    </span>
                    <span className="rounded-full border border-gray-800 px-2 py-1 text-gray-300">
                      Embedding {composition.embedding_percentage}%
                    </span>
                  </div>
                )}
                <div className="mt-2 space-y-1">
                  {(environment.dependency_summary?.dependencies ?? []).slice(0, 6).map((dependency, index) => (
                    <div key={`${environment.environment_id}:dep:${index}`} className="text-xs text-gray-400">
                      {dependency.kind} · {dependency.name} · {dependency.host || 'local'}{dependency.port ? `:${dependency.port}` : ''}
                    </div>
                  ))}
                  {(environment.dependency_summary?.cross_dependencies ?? []).slice(0, 6).map((dependency, index) => (
                    <div key={`${environment.environment_id}:cross:${index}`} className="text-xs text-amber-200/80">
                      {dependency.kind} · {dependency.name} · {dependency.host || 'local'}{dependency.port ? `:${dependency.port}` : ''}
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
                <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Pull Rollup</div>
                <div className="mt-2 text-sm text-gray-300">{pull?.summary || 'No project pull history yet.'}</div>
                <div className="mt-2 text-xs text-gray-500">
                  {pull?.latest_created_at ? `Latest ${new Date(pull.latest_created_at).toLocaleString()}` : 'No bundles yet'}
                </div>
              </div>
              <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-3 md:col-span-2">
                <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Runtime Snapshot</div>
                <div className="mt-2 text-sm text-gray-300">
                  {environment.runtime_snapshot_summary?.captured_at
                    ? `${environment.runtime_snapshot_summary.open_port_count} open ports · ${environment.runtime_snapshot_summary.exposed_port_count} exposed · firewall ${environment.runtime_snapshot_summary.firewall_status}`
                    : 'No runtime snapshot yet.'}
                </div>
              </div>
            </div>
            <div className="mt-3 space-y-2">
              {(environment.service_summaries ?? []).map((summary) => (
                <div key={`${environment.environment_id}:${summary.service_id}:${summary.location_id ?? ''}`} className="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-gray-100">{summary.display_name}</div>
                      <div className="mt-1 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.14em]">
                        <span className="rounded-full border border-cyan-900/30 bg-cyan-950/20 px-2 py-1 text-cyan-200">{summary.execution_mode}</span>
                        {summary.server_id && <span className="rounded-full border border-gray-800 px-2 py-1 text-gray-400">{summary.server_id}</span>}
                        {summary.version && <span className="rounded-full border border-gray-800 px-2 py-1 text-gray-400">version {summary.version}</span>}
                      </div>
                    </div>
                    <div className="text-xs text-amber-200">
                      {summary.pull_summary?.added_count ?? 0}+ / {summary.pull_summary?.removed_count ?? 0}- / {summary.pull_summary?.changed_count ?? 0}~
                    </div>
                  </div>
                  {summary.root && <div className="mt-2 font-mono text-xs text-gray-500 break-all">{summary.root}</div>}
                  {summary.notes && <div className="mt-2 text-xs text-gray-400">{summary.notes}</div>}
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-lg border border-cyan-900/40 bg-cyan-950/20 p-3">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="text-[11px] uppercase tracking-[0.16em] text-cyan-300">Dedicated API Lab</div>
                  <div className="mt-1 text-sm text-cyan-100">
                    Open the full environment viewer for runtime snapshots, API flows, dependencies, and run history.
                  </div>
                </div>
                <button
                  onClick={() => onOpenEnvironmentLab(environment.environment_id)}
                  className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-100 hover:border-cyan-400 hover:text-white"
                >
                  Open Full Page
                </button>
              </div>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              {!offline && (
                <button onClick={() => beginEditEnvironment(environment)} className="p-1 text-gray-500 hover:text-cyan-300">
                  <Pencil className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  function renderProject(project: ProjectManifest) {
    const open = Boolean(openProjects[project.project_id])
    const advancedOpen = Boolean(openProjectAdvanced[project.project_id])
    const children = childProjectsByParent[project.project_id] ?? []
    const projectEnvironments = environmentsByProject[project.project_id] ?? []
    const projectServiceIds = project.service_ids ?? []
    const ownedServices = projectServiceIds
      .map((serviceId) => servicesById.get(serviceId))
      .filter((service): service is Service => Boolean(service))
    const missingServiceIds = projectServiceIds.filter((serviceId) => !servicesById.has(serviceId))
    const serviceCountLabel =
      missingServiceIds.length > 0
        ? `${ownedServices.length} current · ${missingServiceIds.length} missing ref${missingServiceIds.length === 1 ? '' : 's'}`
        : `${ownedServices.length} service${ownedServices.length === 1 ? '' : 's'}`
    return (
      <div key={project.project_id} className="rounded-xl border border-gray-800 bg-gray-950 overflow-hidden">
        <div className="flex items-center justify-between gap-3 p-3">
          <button
            type="button"
            onClick={() => setOpenProjects((current) => ({ ...current, [project.project_id]: !current[project.project_id] }))}
            className="flex min-w-0 items-center gap-3 text-left"
          >
            {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
            <div>
              <div className="text-sm font-medium text-gray-200">{project.display_name}</div>
              <div className="mt-0.5 text-[10px] font-mono text-gray-500">{project.project_id}</div>
            </div>
          </button>
          <div className="flex items-center gap-3">
            <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">
              {serviceCountLabel}
            </div>
            {!offline && (
              <div className="flex items-center gap-2">
                <button onClick={() => beginEditProject(project)} className="p-1 text-gray-500 hover:text-cyan-300">
                  <Pencil className="h-4 w-4" />
                </button>
              </div>
            )}
          </div>
        </div>
        {open && (
          <div className="border-t border-gray-800 p-3">
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
                <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Parent</div>
                <div className="mt-2 text-sm text-gray-300">{project.parent_project_id || 'Company root'}</div>
              </div>
              <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
                <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Services</div>
                <div className="mt-2 text-sm text-gray-300">{ownedServices.length} current</div>
                {missingServiceIds.length > 0 && (
                  <div className="mt-1 text-xs text-amber-200">
                    {missingServiceIds.length} missing reference{missingServiceIds.length === 1 ? '' : 's'}
                  </div>
                )}
              </div>
              <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
                <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Tags</div>
                <div className="mt-2 text-sm text-gray-300">{project.tags.join(', ') || 'None'}</div>
              </div>
            </div>
            <div className="mt-3 text-sm text-gray-400">{project.notes || 'No project notes yet.'}</div>
            <div className="mt-3 rounded-lg border border-gray-800 bg-gray-900/40 p-3">
              <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Owned Services</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {ownedServices.length === 0 ? (
                  <span className="text-xs text-gray-500">No current services owned by this project.</span>
                ) : (
                  ownedServices.map((service) => (
                    <span key={service.service_id} className="rounded-full border border-cyan-900/40 bg-cyan-950/20 px-2 py-1 text-[11px] text-cyan-200">
                      {service.display_name}
                    </span>
                  ))
                )}
                {missingServiceIds.map((serviceId) => (
                  <span key={`${project.project_id}:missing:${serviceId}`} className="rounded-full border border-amber-900/40 bg-amber-950/20 px-2 py-1 text-[11px] text-amber-200">
                    Missing reference: {serviceId}
                  </span>
                ))}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gray-800 bg-gray-900/30 px-3 py-2">
              <div className="text-xs text-gray-500">
                Main view stops at company, project, and owned services. Environment metadata is secondary.
              </div>
              <button
                type="button"
                onClick={() => setOpenProjectAdvanced((current) => ({ ...current, [project.project_id]: !current[project.project_id] }))}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-300 transition-colors hover:border-cyan-500 hover:text-white"
              >
                {advancedOpen ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
                Secondary setup · {projectEnvironments.length} env · {children.length} child
              </button>
            </div>
            {advancedOpen && (
              <div className="mt-3 rounded-lg border border-gray-800 bg-gray-900/40 p-3">
                <div className="mb-3 text-xs uppercase tracking-[0.16em] text-gray-500">
                  Secondary setup
                </div>
                  {!offline && (
                    <button onClick={() => beginAddEnvironment(project.project_id)} className="mb-3 rounded-lg border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:border-cyan-500 hover:text-white">
                      Add Environment
                    </button>
                  )}
                  {renderEnvironmentForm(project.project_id)}
                  <div className="space-y-3">
                    {projectEnvironments.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-gray-800 px-3 py-4 text-sm text-gray-500">
                        No environments yet. Add test, prod, staging, or a custom deployment view here.
                      </div>
                    ) : (
                      projectEnvironments.map(renderEnvironment)
                    )}
                  </div>
                  {children.length > 0 && (
                    <div className="mt-4 rounded-lg border border-gray-800 bg-gray-900/40 p-3">
                      <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Child Projects</div>
                      <div className="mt-3 space-y-2">
                        {children.map((child) => (
                          <div key={child.project_id} className="rounded border border-gray-800 px-3 py-2 text-sm text-gray-300">
                            {child.display_name} <span className="ml-2 font-mono text-[10px] text-gray-500">{child.project_id}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 mb-6">
      <button
        onClick={() => setExpanded((current) => !current)}
        className="w-full flex items-center justify-between p-4 focus:outline-none"
      >
        <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
          <FolderGit2 className="h-4 w-4 text-cyan-400" />
          Projects
        </div>
        {expanded ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
      </button>

      {expanded && (
        <div className="border-t border-gray-800 p-4">
          <div className="flex justify-between items-center mb-4 gap-3">
            <p className="text-xs text-gray-500">
              Company → project grouping for tracked services. Environments stay available but are secondary.
            </p>
            {!offline && !addingProject && !editingProjectId && (
              <button
                onClick={beginAddProject}
                className="flex items-center gap-1 bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 text-xs px-3 py-1.5 rounded-lg transition-colors"
              >
                <Plus className="h-3 w-3" /> Add Project
              </button>
            )}
          </div>

          {error && <div className="mb-4 text-xs text-red-400 bg-red-950/30 p-2 rounded">{error}</div>}

          {(addingProject || editingProjectId) && (
            <div className="mb-6 bg-gray-950 border border-gray-800 p-4 rounded-xl">
              <div className="mb-3">
                <h4 className="text-sm font-medium text-gray-300">{addingProject ? 'Add Project' : 'Edit Project'}</h4>
                <div className="mt-1 text-xs text-gray-500">This edits grouping only. It does not scan paths or deploy nodes.</div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="text-xs text-gray-400">
                  Project ID
                  <input
                    value={projectForm.project_id}
                    onChange={(event) => setProjectForm((current) => ({ ...current, project_id: event.target.value }))}
                    className="mt-1 w-full bg-gray-900 border border-gray-800 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                  />
                  {!addingProject && (
                    <span className="mt-1 block text-[11px] text-gray-500">
                      Renaming updates child projects and environments.
                    </span>
                  )}
                </label>
                <label className="text-xs text-gray-400">
                  Display Name
                  <input
                    value={projectForm.display_name}
                    onChange={(event) => setProjectForm((current) => ({ ...current, display_name: event.target.value }))}
                    className="mt-1 w-full bg-gray-900 border border-gray-800 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                  />
                </label>
                <label className="text-xs text-gray-400">
                  Parent Project
                  <select
                    value={projectForm.parent_project_id}
                    onChange={(event) => setProjectForm((current) => ({ ...current, parent_project_id: event.target.value }))}
                    className="mt-1 w-full bg-gray-900 border border-gray-800 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                  >
                    <option value="">Company root</option>
                    {selectableParentProjects.map((project) => (
                      <option key={project.project_id} value={project.project_id}>
                        {project.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs text-gray-400">
                  Tags
                  <input
                    value={projectForm.tags}
                    onChange={(event) => setProjectForm((current) => ({ ...current, tags: event.target.value }))}
                    className="mt-1 w-full bg-gray-900 border border-gray-800 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                    placeholder="payments, docs, backend"
                  />
                </label>
                <label className="text-xs text-gray-400 md:col-span-2">
                  Notes
                  <textarea
                    value={projectForm.notes}
                    onChange={(event) => setProjectForm((current) => ({ ...current, notes: event.target.value }))}
                    className="mt-1 min-h-20 w-full bg-gray-900 border border-gray-800 rounded px-2 py-2 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                    placeholder="What this project group owns, why it exists, deployment caveats, or who to ask."
                  />
                </label>
              </div>
              <div className="mt-4 rounded-xl border border-gray-800 bg-gray-900/60 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Project Services</div>
                    <div className="mt-1 text-xs text-gray-400">
                      Search and select existing services; no raw JSON editing needed.
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      value={serviceFilter}
                      onChange={(event) => setServiceFilter(event.target.value)}
                      className="max-w-56 rounded-lg border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-300 outline-none hover:border-cyan-500 focus:border-cyan-500"
                      placeholder="Search services"
                    />
                    <select
                      value=""
                      onChange={(event) => addProjectService(event.target.value)}
                      className="max-w-56 rounded-lg border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-300 outline-none hover:border-cyan-500 focus:border-cyan-500 disabled:opacity-50"
                      disabled={availableProjectServices.length === 0}
                    >
                      <option value="">
                        {availableProjectServices.length === 0 ? 'All services selected' : 'Add service'}
                      </option>
                      {availableProjectServices.map((service) => (
                        <option key={service.service_id} value={service.service_id}>
                          {service.display_name} · {projectOwnerLabel(service.service_id, false)}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => setProjectForm((current) => ({ ...current, service_ids: '' }))}
                      className="rounded-lg border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:border-cyan-500 hover:text-white"
                    >
                      Clear
                    </button>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {projectServiceIds.length === 0 ? (
                    <div className="text-xs text-gray-500">No services selected yet.</div>
                  ) : (
                    projectServiceIds.map((serviceId) => {
                      const missing = !servicesById.has(serviceId)
                      return (
                        <span
                          key={serviceId}
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[11px] ${
                            missing
                              ? 'border-amber-900/40 bg-amber-950/20 text-amber-200'
                              : 'border-cyan-900/40 bg-cyan-950/20 text-cyan-200'
                          }`}
                        >
                          {missing ? `Missing ref: ${serviceId}` : serviceId}
                          <button
                            type="button"
                            onClick={() => dropProjectServiceSelection(serviceId)}
                            aria-label={`Remove ${serviceId}`}
                            className="rounded-full p-0.5 text-current opacity-70 hover:bg-black/20 hover:opacity-100"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      )
                    })
                  )}
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                  {visibleSelectableServices.map((service) => {
                    const selected = projectServiceIds.includes(service.service_id)
                    const moveHint = projectMoveHint(service.service_id, selected)
                    return (
                      <button
                        key={service.service_id}
                        type="button"
                        onClick={() => toggleProjectService(service.service_id)}
                        className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                          selected
                            ? 'border-cyan-500 bg-cyan-500/10 text-cyan-100'
                            : 'border-gray-800 bg-gray-950 text-gray-300 hover:border-cyan-500 hover:text-white'
                        }`}
                      >
                        <div className="text-sm font-medium">{service.display_name}</div>
                        <div className="mt-1 font-mono text-[11px] text-gray-500">{service.service_id}</div>
                        <div className={`mt-2 text-[10px] uppercase tracking-[0.16em] ${selected ? 'text-cyan-200' : 'text-gray-500'}`}>
                          {projectOwnerLabel(service.service_id, selected)}
                        </div>
                        {moveHint && <div className="mt-1 text-[11px] text-amber-200">{moveHint}</div>}
                        <div className="mt-1 text-[10px] uppercase tracking-[0.16em] text-gray-600">{service.execution_mode}</div>
                      </button>
                    )
                  })}
                </div>
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <button onClick={resetProjectForm} className="px-3 py-1.5 text-xs text-gray-400 hover:text-white transition-colors">Cancel</button>
                <button onClick={() => void saveProject()} className="flex items-center gap-1 bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1.5 rounded text-xs transition-colors">
                  <Save className="h-3 w-3" /> Save
                </button>
              </div>
            </div>
          )}

          <div className="space-y-4">
            <div className="border border-amber-900/40 bg-amber-950/10 rounded-xl overflow-hidden">
              <div className="p-3 flex items-center justify-between bg-amber-950/20">
                <div>
                  <div className="text-sm font-medium text-amber-100">{workspaceName || workspaceId}</div>
                  <div className="text-[10px] text-amber-300/70 font-mono mt-0.5">{workspaceId}</div>
                </div>
                <div className="text-[10px] uppercase tracking-[0.16em] text-amber-300">
                  company root
                </div>
              </div>
              <div className="px-3 pb-3 text-xs text-amber-100/80">
                {workspaceNotes || `No company notes yet. ${services.length} services tracked · ${unassignedServiceCount} not grouped into a project yet.`}
              </div>
            </div>

            {loading ? (
              <div className="text-xs text-gray-500">Loading...</div>
            ) : rootProjects.length === 0 && !addingProject ? (
              <div className="text-xs text-gray-600 italic">No project groups found yet.</div>
            ) : (
              rootProjects.map(renderProject)
            )}
          </div>
        </div>
      )}
    </div>
  )
}
