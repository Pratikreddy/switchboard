import { useEffect, useState } from 'react'
import { ArrowRight, FolderKanban, Server, Shield } from 'lucide-react'
import type { Workspace, WorkspaceLatest, ServerRecord } from '../types/switchboard'
import { StatusBadge } from '../components/StatusBadge'
import { CONTROL_CENTER_PANEL_GROUPS, type ControlCenterPanelRegistryContext } from '../components/controlCenterPanelRegistry'
import { TECH_STACK_LINES, HOW_TO_USE_LINES } from '../App'
import { getControlCenterContext, listServers } from '../api/client'
import type { ControlCenterContext } from '../types/switchboard'

interface Props {
  workspaces: Workspace[]
  latestResults: Record<string, WorkspaceLatest>
  online: boolean | null
  onOpenWorkspace: (workspaceId: string) => void
  onReloadCompanies: () => void
}

export function ControlCenterPage({
  workspaces,
  latestResults,
  online,
  onOpenWorkspace,
  onReloadCompanies,
}: Props) {
  const [servers, setServers] = useState<ServerRecord[]>([])
  const [dashboardContext, setDashboardContext] = useState<ControlCenterContext | null>(null)
  const [selectedBranch, setSelectedBranch] = useState('')

  useEffect(() => {
    if (online) {
      loadServers()
      loadDashboardContext()
    }
  }, [online])

  useEffect(() => {
    if (online && selectedBranch) {
      loadDashboardContext(selectedBranch)
    }
  }, [selectedBranch])

  async function loadServers() {
    const res = await listServers()
    if (Array.isArray(res)) {
      setServers(res)
    }
  }

  async function loadDashboardContext(branch?: string) {
    const res = await getControlCenterContext(branch)
    if (!('status' in res && 'message' in res)) {
      setDashboardContext(res)
      if (!selectedBranch) {
        setSelectedBranch(res.branch_metadata.active_branch)
      }
    }
  }

  const panelContext: ControlCenterPanelRegistryContext = {
    dashboardContext,
    selectedBranch,
    online,
    servers,
    workspaces,
    techStackLines: TECH_STACK_LINES,
    howToUseLines: HOW_TO_USE_LINES,
    onBranchChange: setSelectedBranch,
    onReloadCompanies,
    onReloadServers: loadServers,
  }

  return (
    <div className="space-y-8">
      {CONTROL_CENTER_PANEL_GROUPS.map((group) => (
        <section
          key={group.id}
          className={group.layoutClassName}
          data-testid={`control-center-panel-group-${group.id}`}
          aria-label={group.title}
        >
          {group.id === 'activity' && (
            <div className="flex justify-end text-xs text-gray-500" data-testid="backend-status-compact">
              Backend: {online === null ? 'checking' : online ? 'live' : 'offline fallback'}
            </div>
          )}
          {group.panels.map((panel) => (
            <div key={panel.id} data-panel-id={panel.id} data-panel-priority={panel.priority} data-panel-subgroup={panel.subgroup}>
              {panel.render(panelContext)}
            </div>
          ))}
        </section>
      ))}

      <section className="grid gap-4 md:grid-cols-2">
        {workspaces.map((workspace) => {
          const latest = latestResults[workspace.workspace_id]
          const serverCount = workspace.server_count ?? workspace.server_ids.length
          const serviceCount = workspace.service_count ?? workspace.services.length
          const status = serviceCount === 0 ? 'unverified' : latest?.summary.status ?? 'unverified'
          const freshnessState = latest?.summary.freshness_state || latest?.freshness?.freshness_state || ''
          const stale = serviceCount > 0 && Boolean(freshnessState && freshnessState !== 'Fresh')
          const refreshAction = latest?.summary.refresh_action || latest?.freshness?.refresh_action || (stale ? 'Collect' : '')
          return (
            <button
              key={workspace.workspace_id}
              onClick={() => onOpenWorkspace(workspace.workspace_id)}
              className={`group rounded-2xl border p-5 text-left transition-colors ${
                stale
                  ? 'border-amber-800/50 bg-gray-900/70 hover:border-amber-500/70'
                  : 'border-gray-800 bg-gray-900 hover:border-cyan-500/60 hover:bg-gray-900/80'
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-gray-500">
                    Company · {workspace.workspace_id}
                  </div>
                  <div className="mt-1 text-xl font-semibold text-white">{workspace.display_name}</div>
                </div>
                <StatusBadge status={status} />
              </div>

              <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
                <div className="rounded-xl border border-gray-800 bg-gray-950 px-3 py-3">
                  <div className="flex items-center gap-2 text-gray-400">
                    <FolderKanban className="h-4 w-4 text-cyan-400" />
                    Services
                  </div>
                  <div className="mt-2 text-2xl font-semibold text-white">{serviceCount}</div>
                </div>
                <div className="rounded-xl border border-gray-800 bg-gray-950 px-3 py-3">
                  <div className="flex items-center gap-2 text-gray-400">
                    <Server className="h-4 w-4 text-cyan-400" />
                    Servers
                  </div>
                  <div className="mt-2 text-2xl font-semibold text-white">{serverCount}</div>
                </div>
                <div className="rounded-xl border border-gray-800 bg-gray-950 px-3 py-3">
                  <div className="flex items-center gap-2 text-gray-400">
                    <Shield className="h-4 w-4 text-cyan-400" />
                    State
                  </div>
                  <div className="mt-2 text-sm font-medium capitalize text-white">{status}</div>
                  {stale && (
                    <div className="mt-1 text-[11px] uppercase tracking-[0.14em] text-amber-300">
                      {freshnessState}
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-5 flex items-center justify-between text-sm">
                <span className="text-gray-500">
                  {(() => {
                    const ts = latest?.summary.timestamp
                    const d = ts ? new Date(ts) : null
                    return d && !isNaN(d.getTime()) && serviceCount > 0
                      ? `Last run ${d.toLocaleString()}`
                      : 'No live run captured yet'
                  })()}
                </span>
                <span className={`flex items-center gap-2 transition-transform group-hover:translate-x-0.5 ${stale ? 'text-amber-300' : 'text-cyan-400'}`}>
                  {stale ? refreshAction || 'Needs Collect' : 'Open company'}
                  <ArrowRight className="h-4 w-4" />
                </span>
              </div>
            </button>
          )
        })}
      </section>
    </div>
  )
}
