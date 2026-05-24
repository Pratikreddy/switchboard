import { useEffect, useState } from 'react'
import type { Workspace } from '../types/switchboard'
import { CONTROL_CENTER_PANEL_GROUPS, type ControlCenterPanelRegistryContext } from '../components/controlCenterPanelRegistry'
import { TECH_STACK_LINES, HOW_TO_USE_LINES } from '../App'
import { getControlCenterContext } from '../api/client'
import type { ControlCenterContext } from '../types/switchboard'

interface Props {
  workspaces: Workspace[]
  online: boolean | null
  onOpenWorkspace: (workspaceId: string) => void
  onReloadCompanies: () => void
}

export function ControlCenterPage({
  workspaces,
  online,
  onOpenWorkspace,
  onReloadCompanies,
}: Props) {
  const [dashboardContext, setDashboardContext] = useState<ControlCenterContext | null>(null)
  const [selectedBranch, setSelectedBranch] = useState('')

  useEffect(() => {
    if (online) {
      loadDashboardContext()
    }
  }, [online])

  useEffect(() => {
    if (online && selectedBranch) {
      loadDashboardContext(selectedBranch)
    }
  }, [selectedBranch])

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
    workspaces,
    techStackLines: TECH_STACK_LINES,
    howToUseLines: HOW_TO_USE_LINES,
    onBranchChange: setSelectedBranch,
    onReloadCompanies,
    onOpenWorkspace,
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
          {group.panels.map((panel) => (
            <div key={panel.id} data-panel-id={panel.id} data-panel-priority={panel.priority} data-panel-subgroup={panel.subgroup}>
              {panel.render(panelContext)}
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}
