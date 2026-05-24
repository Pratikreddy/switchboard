import { useMemo } from 'react'
import {
  Activity,
  GitBranch,
} from 'lucide-react'
import type { ActivityMapDay, ControlCenterContext } from '../types/switchboard'

interface ActivityMapProps {
  context: ControlCenterContext | null
  selectedBranch: string
  onBranchChange: (branch: string) => void
}

function colorFor(day?: ActivityMapDay) {
  const value = day ? day.task_count + Math.ceil(day.scope_entry_count / 3) : 0
  if (value <= 0) return 'bg-gray-800'
  if (value <= 2) return 'bg-amber-950'
  if (value <= 5) return 'bg-amber-700'
  if (value <= 10) return 'bg-yellow-500'
  return 'bg-lime-300'
}

function lastCalendarDates() {
  const dates: string[] = []
  const today = new Date()
  const start = new Date(today)
  start.setDate(today.getDate() - 97)
  start.setDate(start.getDate() - start.getDay())
  for (let i = 0; i < 112; i += 1) {
    const date = new Date(start)
    date.setDate(start.getDate() + i)
    dates.push(date.toISOString().slice(0, 10))
  }
  return dates
}

export function ActivityMapPanel({ context, selectedBranch, onBranchChange }: ActivityMapProps) {
  const activity = context?.activity_map
  const branch = context?.branch_metadata
  const dayByDate = useMemo(() => {
    const map = new Map<string, ActivityMapDay>()
    activity?.days.forEach((day) => map.set(day.date, day))
    return map
  }, [activity?.days])
  const dates = useMemo(lastCalendarDates, [])
  const branches = branch?.branches.length ? branch.branches : [branch?.active_branch || 'main']

  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
            <Activity className="h-4 w-4 text-amber-300" />
            Work Activity Map
          </div>
          <div className="mt-1 text-xs text-gray-500">
            GitHub-style grid from task-ledger work. Branch/head is metadata only.
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-400">
          <GitBranch className="h-3.5 w-3.5 text-cyan-300" />
          <select
            value={selectedBranch || branch?.active_branch || ''}
            onChange={(event) => onBranchChange(event.target.value)}
            className="rounded-lg border border-gray-700 bg-gray-950 px-2 py-1.5 text-xs text-gray-200 outline-none focus:border-cyan-500"
            aria-label="Branch metadata"
          >
            {branches.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4 overflow-x-auto pb-1">
        <div className="grid w-max grid-flow-col grid-rows-7 gap-1">
          {dates.map((date) => {
            const day = dayByDate.get(date)
            return (
              <div
                key={date}
                data-testid="work-activity-cell"
                title={`${date}: ${day?.task_count ?? 0} task entries`}
                className={`h-2.5 w-2.5 rounded-[2px] ${colorFor(day)}`}
              />
            )
          })}
        </div>
      </div>

      <div className="mt-4 grid gap-3 text-xs sm:grid-cols-4">
        <Metric label="Tasks" value={activity?.total_tasks ?? 0} />
        <Metric label="Changed paths" value={activity?.total_changed_paths ?? 0} tone="emerald" />
        <Metric label="Scopes" value={activity?.total_scope_entries ?? 0} tone="cyan" />
        <Metric label="Active lines" value={context?.line_noise.active_source_lines ?? 0} tone="cyan" />
      </div>

      <div className="mt-3 text-xs text-gray-500">
        {context?.cleanup_note || 'No task-ledger activity note loaded yet.'}
      </div>
    </section>
  )
}

function Metric({ label, value, tone = 'white' }: { label: string; value: number; tone?: 'white' | 'emerald' | 'cyan' }) {
  const color = tone === 'emerald' ? 'text-emerald-200' : tone === 'cyan' ? 'text-cyan-100' : 'text-white'
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
      <div className="text-gray-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${color}`}>{value}</div>
    </div>
  )
}
