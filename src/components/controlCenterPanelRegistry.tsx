import { useState } from 'react'
import type { ReactElement } from 'react'
import { BookOpen, ChevronDown, ChevronRight, HelpCircle } from 'lucide-react'
import { CompaniesPanel } from './CompaniesPanel'
import { ActivityMapPanel } from './ControlCenterInsightPanels'
import type { ControlCenterContext, Workspace } from '../types/switchboard'

export type ControlCenterPanelGroupId = 'activity' | 'overview'

export interface ControlCenterPanelRegistryContext {
  dashboardContext: ControlCenterContext | null
  selectedBranch: string
  online: boolean | null
  workspaces: Workspace[]
  techStackLines: string[]
  howToUseLines: string[]
  onBranchChange: (branch: string) => void
  onReloadCompanies: () => void
  onOpenWorkspace: (workspaceId: string) => void
}

export interface ControlCenterPanelDefinition {
  id: string
  title: string
  priority: number
  subgroup: string
  defaultOpen?: boolean
  render: (context: ControlCenterPanelRegistryContext) => ReactElement
}

export interface ControlCenterPanelGroup {
  id: ControlCenterPanelGroupId
  title: string
  priority: number
  layoutClassName: string
  panels: ControlCenterPanelDefinition[]
}

function RegisteredTextPanel({
  title,
  lines,
  icon,
}: {
  title: string
  lines: string[]
  icon: 'book' | 'help'
}) {
  const [open, setOpen] = useState(false)
  const Icon = icon === 'book' ? BookOpen : HelpCircle
  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900">
      <button
        className="flex w-full items-center justify-between px-5 py-4 text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
          <Icon className="h-4 w-4 text-cyan-400" />
          {title}
        </div>
        {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
      </button>
      {open && (
        <ul className="space-y-2 border-t border-gray-800 px-5 py-4">
          {lines.map((line, index) => (
            <li key={`${title}:${index}`} className="text-sm text-gray-400">{line}</li>
          ))}
        </ul>
      )}
    </section>
  )
}

const CONTROL_CENTER_PANEL_GROUP_DEFINITIONS: ControlCenterPanelGroup[] = [
  {
    id: 'activity',
    title: 'Activity',
    priority: 10,
    layoutClassName: 'space-y-4',
    panels: [
      {
        id: 'task-ledger-activity',
        title: 'Work Activity Map',
        priority: 10,
        subgroup: 'work-density',
        defaultOpen: true,
        render: (context) => (
          <ActivityMapPanel
            context={context.dashboardContext}
            selectedBranch={context.selectedBranch}
            onBranchChange={context.onBranchChange}
          />
        ),
      },
    ],
  },
  {
    id: 'overview',
    title: 'Overview',
    priority: 20,
    layoutClassName: 'grid gap-4 lg:grid-cols-3',
    panels: [
      {
        id: 'tech-stack',
        title: 'Tech Stack',
        priority: 10,
        subgroup: 'reference',
        render: (context) => <RegisteredTextPanel title="Tech Stack" lines={context.techStackLines} icon="book" />,
      },
      {
        id: 'how-to-use',
        title: 'How To Use',
        priority: 20,
        subgroup: 'reference',
        render: (context) => <RegisteredTextPanel title="How To Use" lines={context.howToUseLines} icon="help" />,
      },
      {
        id: 'companies',
        title: 'Companies',
        priority: 30,
        subgroup: 'managed-projects',
        render: (context) => (
          <CompaniesPanel
            companies={context.workspaces}
            offline={!context.online}
            onReload={context.onReloadCompanies}
            onOpenCompany={context.onOpenWorkspace}
          />
        ),
      },
    ],
  },
]

export const CONTROL_CENTER_PANEL_GROUPS: ControlCenterPanelGroup[] = CONTROL_CENTER_PANEL_GROUP_DEFINITIONS.map((group) => ({
  ...group,
  panels: [...group.panels].sort((a, b) => a.priority - b.priority),
})).sort((a, b) => a.priority - b.priority)
