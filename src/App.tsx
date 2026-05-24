import { useCallback, useEffect, useState } from 'react'
import type { Workspace, ServiceRunResult, WorkspaceLatest } from './types/switchboard'
import { getHealth, listWorkspaces, getWorkspaceLatest } from './api/client'
import { isApiError } from './types/switchboard'
import { WorkspaceSwitcher } from './components/WorkspaceSwitcher'
import { WorkspacePage } from './pages/WorkspacePage'
import { ServiceDetailPage } from './pages/ServiceDetailPage'
import { ControlCenterPage } from './pages/ControlCenterPage'
import { loadFallbackWorkspaceList } from './data/fallback'

export const TECH_STACK_LINES = [
  'Backend: FastAPI, Pydantic Settings, Paramiko SSH/SFTP, file-based evidence JSON.',
  'Frontend: React 19, Vite, TypeScript, Tailwind, Lucide icons.',
  'Versioning: Git for repo status/pull/push actions and commit metadata.',
  'Operations: local path walking plus remote SSH/SFTP collection from declared servers.',
  'Runtime: per-location snapshots, exposure hints, and generated operator commands.',
  'Node sync: manual, control-center initiated only. Nodes do not call back into the control center.',
  'Testing: Vitest for frontend contract checks and Python unittest for backend regressions.',
]

export const HOW_TO_USE_LINES = [
  'Pick a company, then run Collect to sync node truth first, then refresh saved scope, pull authority, ports, repo state, docs, and logs.',
  'Use Advanced Service Inventory to add one root path, expand the tree, and uncheck dump paths you do not want.',
  'Category rules are simple: repo, doc, log, or exclude. You can override the auto-suggestion.',
  'Create service saves the chosen scope and per-location runtime config into the manifest.',
  'Use Projects to group tracked services into business projects; environment details stay in advanced views.',
  'Servers belong to a company and can be marked VPN-required plus either native-agent or local-bundle-only.',
  'Pull Bundles create a new timestamped local copy while preserving the source tree.',
  'Service detail pages handle runtime snapshots plus Sync From Node and Sync To Node.',
  'Node-side agents should read switchboard/core/playbook.md and update only switchboard/local/tasks-completed.md.',
  'Root project docs like README.md, API.md, and CHANGELOG.md stay tracked in scope; the service page only controls whether Switchboard may rewrite them.',
  'Repo actions stay per service: git status, safety check, git pull, git push.',
]

export default function App() {
  const [online, setOnline] = useState<boolean | null>(null)
  const [apiVersion, setApiVersion] = useState<string | null>(null)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [activeWorkspace, setActiveWorkspace] = useState<string | null>(null)
  const [selectedService, setSelectedService] = useState<string | null>(null)
  const [latestResults, setLatestResults] = useState<Record<string, WorkspaceLatest>>({})

  function loadCompanies() {
    listWorkspaces().then((res) => {
      if (!isApiError(res) && res.length > 0) {
        setWorkspaces(res)
      }
    })
  }

  // Check backend health
  useEffect(() => {
    getHealth().then((res) => {
      if (!isApiError(res)) {
        setOnline(true)
        if (res.version) setApiVersion(res.version)
      } else {
        setOnline(false)
      }
    })
  }, [])

  // Load companies/workspaces
  useEffect(() => {
    if (online === null) return
    if (!online) {
      loadFallbackWorkspaceList().then((wss) => {
        if (wss.length > 0) {
          setWorkspaces(wss)
        }
      })
      return
    }
    loadCompanies()
  }, [online])

  // Load latest for active workspace
  useEffect(() => {
    if (!online || workspaces.length === 0) return
    const missing = workspaces
      .map((workspace) => workspace.workspace_id)
      .filter((workspaceId) => !latestResults[workspaceId])
    if (missing.length === 0) return
    missing.forEach((workspaceId) => {
      getWorkspaceLatest(workspaceId).then((res) => {
        if (!isApiError(res)) {
          setLatestResults((prev) => ({ ...prev, [workspaceId]: res }))
        }
      })
    })
  }, [workspaces, online, latestResults])

  const currentLatest = activeWorkspace ? latestResults[activeWorkspace] : undefined

  const handleLatestUpdated = useCallback((workspaceId: string, latest: WorkspaceLatest) => {
    setLatestResults((prev) => ({ ...prev, [workspaceId]: latest }))
  }, [])

  function handleServiceDeleted(serviceId: string, workspaceId: string) {
    setSelectedService(null)
    setWorkspaces((current) =>
      current.map((workspace) =>
        workspace.workspace_id === workspaceId
          ? {
              ...workspace,
              services: workspace.services.filter((service) => service.service_id !== serviceId),
              service_count: Math.max(
                0,
                (workspace.service_count ?? workspace.services.length) - 1,
              ),
            }
          : workspace,
      ),
    )
    setLatestResults((current) => {
      if (!current[workspaceId]) return current
      const next = { ...current }
      delete next[workspaceId]
      return next
    })
  }

  // Find run result for a service
  function getServiceResult(serviceId: string): ServiceRunResult | undefined {
    return currentLatest?.services.find((s) => s.service_id === serviceId)
  }

  const offline = online === false

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Top bar */}
      <header className="border-b border-gray-800 bg-gray-950 sticky top-0 z-10">
        <div className="mx-auto flex w-full max-w-[1800px] items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <button
            onClick={() => {
              setSelectedService(null)
              setActiveWorkspace(null)
            }}
            className="text-lg font-bold text-white tracking-tight"
          >
            Switchboard Control Center
          </button>

          {workspaces.length > 0 && (
              <WorkspaceSwitcher
                workspaces={workspaces}
                active={activeWorkspace ?? ''}
                onChange={(id) => {
                  setSelectedService(null)
                  setActiveWorkspace(id)
                }}
              />
          )}

          <div className="ml-auto flex items-center gap-3">
            {apiVersion && (
              <span className="text-xs font-mono text-gray-600 bg-gray-900 border border-gray-800 px-2 py-0.5 rounded">
                v{apiVersion}
              </span>
            )}
            <span
              className={`w-2 h-2 rounded-full ${
                online === null ? 'bg-gray-600' : online ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-xs text-gray-500">
              {online === null ? 'Connecting…' : online ? 'Live' : 'Offline'}
            </span>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto w-full max-w-[1800px] px-4 py-6 sm:px-6 lg:px-8">
        {selectedService && activeWorkspace ? (
          <ServiceDetailPage
            serviceId={selectedService}
            runResult={getServiceResult(selectedService)}
            offline={offline}
            onBack={() => setSelectedService(null)}
            onDeleted={handleServiceDeleted}
          />
        ) : activeWorkspace ? (
          <WorkspacePage
            workspaceId={activeWorkspace}
            offline={offline}
            onSelectService={setSelectedService}
            onLatestUpdated={handleLatestUpdated}
          />
        ) : (
          <ControlCenterPage
            workspaces={workspaces}
            online={online}
            onReloadCompanies={loadCompanies}
            onOpenWorkspace={(workspaceId) => {
              setSelectedService(null)
              setActiveWorkspace(workspaceId)
            }}
          />
        )}
      </main>
    </div>
  )
}
