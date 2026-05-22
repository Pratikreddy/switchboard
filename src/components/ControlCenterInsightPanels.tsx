import { useMemo } from 'react'
import { Activity, Bot, GitBranch, MessageSquareText, SlidersHorizontal, SplitSquareHorizontal } from 'lucide-react'
import type { ActivityMapDay, ControlCenterContext, FeatureMapItem } from '../types/switchboard'

interface ActivityMapProps {
  context: ControlCenterContext | null
  selectedBranch: string
  onBranchChange: (branch: string) => void
}

function colorFor(day?: ActivityMapDay) {
  const value = day ? day.task_count + Math.ceil(day.scope_entry_count / 3) : 0
  if (value <= 0) return 'bg-gray-800'
  if (value <= 2) return 'bg-emerald-950'
  if (value <= 5) return 'bg-emerald-700'
  if (value <= 10) return 'bg-emerald-500'
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
            <Activity className="h-4 w-4 text-emerald-300" />
            Task-Ledger Activity Map
          </div>
          <div className="mt-1 text-xs text-gray-500">
            Branch/head is metadata only. Task ledgers are the activity source.
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
        {context?.cleanup_note || 'No line/noise note loaded yet.'}
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

export function HarnessContextPanel({ context }: { context: ControlCenterContext | null }) {
  const harness = context?.harness_source_map
  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
          <SlidersHorizontal className="h-4 w-4 text-cyan-300" />
          Harness Adapter Source Map
        </div>
        <span className="rounded-full border border-gray-700 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-gray-400">
          {harness?.active_count ?? 0} active
        </span>
      </div>
      <div className="mt-1 text-xs text-gray-500">{harness?.note}</div>
      <div className="mt-4 space-y-2">
        {(harness?.entries ?? []).map((entry) => (
          <div key={entry.adapter_file} className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <div className="font-mono text-sm text-gray-200">{entry.adapter_file}</div>
              <span className={entry.active ? 'text-xs text-emerald-300' : 'text-xs text-amber-300'}>
                {entry.active ? 'active' : 'parked'}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-gray-500">
              <span>{entry.line_count} lines</span>
              <span>{entry.byte_count} bytes</span>
              <span>{entry.points_to || 'no canonical pointer'}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function FeatureList({ title, items }: { title: string; items: FeatureMapItem[] }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
      <div className="text-xs uppercase tracking-[0.14em] text-gray-500">{title}</div>
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <div key={`${title}:${item.name}`}>
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium text-gray-200">{item.name}</div>
              <span className="rounded-full border border-gray-700 px-2 py-0.5 text-[10px] text-gray-400">{item.status}</span>
            </div>
            <div className="mt-1 text-xs text-gray-500">{item.note}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function FeatureMapPanel({ context }: { context: ControlCenterContext | null }) {
  const map = context?.feature_map
  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
        <SplitSquareHorizontal className="h-4 w-4 text-cyan-300" />
        Main And Sidecar Features
      </div>
      <div className="mt-1 text-xs text-gray-500">{map?.correction_note}</div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <FeatureList title="Main" items={map?.main_features ?? []} />
        <FeatureList title="Sidecar" items={map?.sidecar_features ?? []} />
      </div>
    </section>
  )
}

export function SourceNotesPanel({ context }: { context: ControlCenterContext | null }) {
  const story = context?.user_story
  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
        <MessageSquareText className="h-4 w-4 text-amber-300" />
        User Story Evidence
      </div>
      <div className="mt-1 text-xs text-gray-500">Project-local raw asks, clarifications, interpretation, and open ambiguities.</div>
      {story?.exists && (
        <div className="mt-3 rounded-lg border border-gray-800 bg-gray-950 p-3 text-xs">
          <div className="flex items-center justify-between gap-3 text-gray-500">
            <span>{story.last_clarified_at || story.updated_at}</span>
            <span>project-local</span>
          </div>
          <div className="mt-2 line-clamp-4 text-gray-300">{story.current_interpretation}</div>
          <div className="mt-2 font-mono text-[11px] text-gray-500">{story.path}</div>
        </div>
      )}
    </section>
  )
}

export function AgentExperienceNotesPanel({ context }: { context: ControlCenterContext | null }) {
  const notes = context?.agent_usage_notes
  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
        <Bot className="h-4 w-4 text-violet-300" />
        Agent Usage Notes
      </div>
      <div className="mt-1 text-xs text-gray-500">Agent-authored notes about using Switchboard for data sync, evidence, and handoff.</div>
      {notes?.exists && (
        <div className="mt-3 rounded-lg border border-gray-800 bg-gray-950 p-3 text-xs text-gray-400">
          <div className="text-gray-500">{notes.updated_at || notes.path}</div>
          <div className="mt-2 text-gray-300">{notes.latest_note || notes.suggested_features[0] || notes.confusing[0] || notes.useful[0]}</div>
          <div className="mt-2 font-mono text-[11px] text-gray-500">{notes.path}</div>
        </div>
      )}
    </section>
  )
}

export const HarnessSourceMapPanel = HarnessContextPanel
export const UserStoryPanel = SourceNotesPanel
export const AgentUsageNotesPanel = AgentExperienceNotesPanel
