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
  onLatestUpdated?: (workspaceId: string, latest: WorkspaceLatest) => void
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

export function WorkspacePage({ workspaceId, offline, onSelectService, onLatestUpdated }: Props) {
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
  const workspaceFreshness = latest?.summary ?? latest?.freshness
  const workspaceFreshnessState = loading ? '' : workspaceFreshness?.freshness_state || 'Unverified'
  const workspaceFreshnessLabel = freshnessDisplayLabel(workspaceFreshnessState)
  const workspaceFreshnessStale = Boolean(workspaceFreshnessState && workspaceFreshnessState !== 'Fresh')
  const workspaceRefreshAction =
    workspaceFreshness?.refresh_action ||
    (workspaceFreshnessState === 'Manager unreachable' ? 'Check 8020' : workspaceFreshnessStale ? 'Collect' : '')

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
        {workspaceFreshnessState && (
          <div className={`mt-3 border-t pt-3 text-xs ${
            workspaceFreshnessStale
              ? 'border-amber-900/40 text-amber-100'
              : 'border-gray-800 text-gray-400'
          }`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-2 py-1 ${
                workspaceFreshnessStale
                  ? 'border-amber-700/50 bg-amber-950/20 text-amber-200'
                  : 'border-emerald-900/40 bg-emerald-950/20 text-emerald-200'
              }`}>
                {workspaceFreshnessLabel}
              </span>
              {workspaceRefreshAction && (
                <span className="rounded-full border border-gray-700 bg-gray-950 px-2 py-1 text-gray-300">
                  {workspaceRefreshAction}
                </span>
              )}
              <span className="text-gray-500">
                Snapshot data as of: {formatTimestampLabel(workspaceFreshness?.data_as_of || latest?.summary?.timestamp)}
              </span>
            </div>
            <details className="mt-2">
              <summary className="cursor-pointer text-[11px] uppercase tracking-[0.14em] text-gray-500">
                Freshness details
              </summary>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500">
                <span>Truth source: {freshnessSourceLabel(workspaceFreshness?.freshness_source)}</span>
                <span>Data as of: {formatTimestampLabel(workspaceFreshness?.data_as_of || latest?.summary?.timestamp)}</span>
                <span>Truth as of: {formatTimestampLabel(workspaceFreshness?.truth_as_of)}</span>
                <span>Snapshot data as of: {formatTimestampLabel(workspaceFreshness?.data_as_of || latest?.summary?.timestamp)}</span>
              </div>
            </details>
          </div>
        )}
      </div>

      <div className="mb-6">
        <ProjectsPanel
          workspaceId={workspaceId}
          offline={offline}
          workspaceName={workspace?.display_name}
          workspaceNotes={workspace?.notes}
          services={services}
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
        <details className="mt-8">
          <summary className="cursor-pointer px-1 py-3 text-sm font-medium text-gray-300">
            Task Ledger (Cross-Node Summary)
          </summary>
          <div className="pt-2">
            <TaskLedgerPanel tasks={allTasks} title="Task Ledger (Cross-Node Summary)" showServiceLabel />
          </div>
        </details>
      )}
    </div>
  )
}
