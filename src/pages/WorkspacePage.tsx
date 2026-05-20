import { useEffect, useState, useMemo } from 'react'
import type { Workspace, WorkspaceLatest, Service, ServiceRunResult } from '../types/switchboard'
import { getWorkspace, getWorkspaceLatest, triggerCollect } from '../api/client'
import { isApiError } from '../types/switchboard'
import { ServiceCard } from '../components/ServiceCard'
import { RunStatus } from '../components/RunStatus'
import { loadFallbackWorkspaceList } from '../data/fallback'
import { ProjectOnboardingPanel } from '../components/ProjectOnboardingPanel'
import { ProjectsPanel } from '../components/ProjectsPanel'
import { TaskLedgerPanel } from '../components/TaskLedgerPanel'
import { InfoDropdown } from '../components/InfoDropdown'
import { TECH_STACK_LINES, HOW_TO_USE_LINES } from '../App'
import type { TaskLedgerEntry } from '../types/switchboard'

interface Props {
  workspaceId: string
  offline: boolean
  onSelectService: (id: string) => void
  onOpenEnvironmentLab: (environmentId: string) => void
  onLatestUpdated?: (workspaceId: string, latest: WorkspaceLatest) => void
}

export function WorkspacePage({ workspaceId, offline, onSelectService, onOpenEnvironmentLab, onLatestUpdated }: Props) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [latest, setLatest] = useState<WorkspaceLatest | null>(null)
  const [collecting, setCollecting] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    if (offline) {
      loadFallbackWorkspaceList().then((wss) => {
        const ws = wss.find((w) => w.workspace_id === workspaceId) ?? null
        setWorkspace(ws)
        setLoading(false)
      })
      return
    }
    Promise.all([getWorkspace(workspaceId), getWorkspaceLatest(workspaceId)]).then(
      ([ws, lat]) => {
        if (!isApiError(ws)) setWorkspace(ws)
        if (!isApiError(lat)) {
          setLatest(lat)
          onLatestUpdated?.(workspaceId, lat)
        }
        setLoading(false)
      },
    )
  }, [workspaceId, offline, onLatestUpdated])

  async function handleCollect() {
    setCollecting(true)
    const result = await triggerCollect(workspaceId, { include_node_sync: true })
    if (!isApiError(result)) {
      setLatest(result)
      onLatestUpdated?.(workspaceId, result)
    }
    const [workspaceResult, latestResult] = await Promise.all([
      getWorkspace(workspaceId),
      getWorkspaceLatest(workspaceId),
    ])
    if (!isApiError(workspaceResult)) setWorkspace(workspaceResult)
    if (!isApiError(latestResult)) {
      setLatest(latestResult)
      onLatestUpdated?.(workspaceId, latestResult)
    }
    setCollecting(false)
  }

  function handleCreated(service: Service) {
    setWorkspace((current) =>
      current
        ? {
            ...current,
            services: [...current.services, service].sort(
              (a, b) => (a.favorite_tier ?? 99) - (b.favorite_tier ?? 99),
            ),
          }
        : current,
    )
  }

  // Build a map from service_id → run result for quick lookup
  const resultMap: Record<string, ServiceRunResult> = {}
  latest?.services.forEach((r) => {
    resultMap[r.service_id] = r
  })

  const services = (workspace?.services ?? []).sort(
    (a, b) => (a.favorite_tier ?? 99) - (b.favorite_tier ?? 99),
  )

  const allTasks = useMemo(() => {
    let list: TaskLedgerEntry[] = []
    services.forEach(s => {
      if (s.task_ledger) {
        const enriched = s.task_ledger.map(t => ({ ...t, service_name: s.display_name }))
        list = list.concat(enriched)
      }
    })
    return list.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, 50)
  }, [services])

  return (
    <div>
      <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">
            {workspace?.display_name ?? workspaceId}
          </h2>
          <div className="mt-1 text-xs text-gray-500">
            Company · {workspaceId}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <InfoDropdown label="Tech" title="Framework Stack" lines={TECH_STACK_LINES} />
          <InfoDropdown label="How To" title="Control Center Usage" lines={HOW_TO_USE_LINES} />
        </div>
      </div>

      {/* Run status bar */}
      <div className="mb-2 bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
        <RunStatus
          summary={latest?.summary}
          onCollect={handleCollect}
          collecting={collecting}
          offline={offline}
        />
      </div>

      <div className="mb-6">
        <ProjectsPanel
          workspaceId={workspaceId}
          offline={offline}
          workspaceName={workspace?.display_name}
          workspaceNotes={workspace?.notes}
          services={services}
          onOpenEnvironmentLab={onOpenEnvironmentLab}
        />
      </div>

      <details className="mb-6">
        <summary className="cursor-pointer px-1 py-3 text-sm font-medium text-gray-300">
          Advanced Service Inventory
        </summary>
        <div className="pt-2">
          <ProjectOnboardingPanel
            workspaceId={workspaceId}
            serverIds={workspace?.server_ids ?? []}
            disabled={offline}
            onCreated={handleCreated}
          />
        </div>
      </details>

      {/* Service grid */}
      {loading ? (
        <div className="text-gray-500 text-sm">Loading…</div>
      ) : services.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-800 bg-gray-900 px-4 py-6 text-gray-500 text-sm italic">
          No services found. {offline ? 'Backend offline.' : 'Use Advanced Service Inventory to seed this workspace manually.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {services.map((svc: Service) => (
            <ServiceCard
              key={svc.service_id}
              service={svc}
              result={resultMap[svc.service_id]}
              onClick={() => onSelectService(svc.service_id)}
            />
          ))}
        </div>
      )}

      {allTasks.length > 0 && (
        <div className="mt-8">
          <TaskLedgerPanel tasks={allTasks} title="Task Ledger (Cross-Node Summary)" showServiceLabel />
        </div>
      )}
    </div>
  )
}
