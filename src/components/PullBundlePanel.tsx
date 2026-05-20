import { useEffect, useMemo, useState } from 'react'
import { Archive, ChevronDown, ChevronRight, Download, LoaderCircle, PackagePlus, Settings2 } from 'lucide-react'
import { createPullBundle, getActionLocks, listPullBundles, preflightPullBundle } from '../api/client'
import type { DependencyComposition, PullBundlePreflight, PullBundleRecord, ScopeEntry, Service } from '../types/switchboard'
import { isApiError } from '../types/switchboard'
import { StatusBadge } from './StatusBadge'
import { ConfirmationModal, ACTION_EXPLAIN } from './ConfirmationModal'
import { AccordionSection } from './AccordionSection'

interface Props {
  service: Service
  disabled?: boolean
  refreshKey?: number
}

function uniqueByPath(entries: ScopeEntry[]) {
  const seen = new Set<string>()
  return entries.filter((entry) => {
    if (seen.has(`${entry.kind}:${entry.path}`)) return false
    seen.add(`${entry.kind}:${entry.path}`)
    return true
  })
}

function formatTimestampLabel(value?: string) {
  if (!value) return 'missing'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function freshnessDisplayLabel(value?: string) {
  const state = value || 'Unverified'
  return state === 'Stale' ? 'Stale cache' : state
}

function freshnessSourceLabel(value?: string) {
  return value ? value.replace(/_/g, ' ') : 'Unverified'
}

function timestampBefore(left?: string, right?: string) {
  if (!left || !right) return false
  const leftDate = new Date(left)
  const rightDate = new Date(right)
  if (Number.isNaN(leftDate.getTime()) || Number.isNaN(rightDate.getTime())) return false
  return leftDate.getTime() < rightDate.getTime()
}

function countSummaryLabel(summary?: Record<string, number>) {
  const entries = Object.entries(summary ?? {}).filter(([, count]) => count > 0)
  if (entries.length === 0) return ''
  return entries.map(([key, count]) => `${key} ${count}`).join(' · ')
}

function readinessStatusLabel(bundle: PullBundleRecord) {
  const status = bundle.backup_readiness_status ?? (bundle.backup_clean ? 'review_required' : 'proof_only')
  return status.replace(/_/g, ' ')
}

function bundleProfileLabel(bundle: PullBundleRecord) {
  if (bundle.backup_clean || bundle.bundle_profile) return `Bundle profile: ${bundle.bundle_profile ?? 'backup-clean'}`
  return 'Bundle profile: legacy proof'
}

function exposureSummary(bundle: PullBundleRecord) {
  return bundle.exposure_summary ?? bundle.metadata_summaries?.exposure_summary
}

function skippedSummary(bundle: PullBundleRecord) {
  return bundle.metadata_summaries?.skipped_summary
}

function unresolvedExposureCount(bundle: PullBundleRecord) {
  return bundle.unresolved_exposure_count ?? bundle.exposure_findings?.length ?? 0
}

function skippedReviewCount(bundle: PullBundleRecord) {
  return bundle.skipped_review_count ?? bundle.skipped_entry_count ?? 0
}

function authorityBlockerCopy(preflight: PullBundlePreflight) {
  if (preflight.freshness?.stale_reason === 'manager_8020_unreachable' || preflight.freshness?.refresh_action === 'Check 8020') {
    return 'Manager truth is unavailable. Check 8020 before creating a bundle; 8009 only proves the Control Center API is alive.'
  }
  if (preflight.vpn_required) return 'Stale authority. Run Sync From Node with VPN on.'
  return 'Stale authority. Run Sync From Node before creating a bundle.'
}

export function PullBundlePanel({ service, disabled, refreshKey = 0 }: Props) {
  const actionKey = 'pull_bundle'
  const sessionKey = `pending:${actionKey}:${service.service_id}`
  const [history, setHistory] = useState<PullBundleRecord[]>([])
  const [bundleResult, setBundleResult] = useState<PullBundleRecord | null>(null)
  const [includePath, setIncludePath] = useState('')
  const [includeKind, setIncludeKind] = useState<'code' | 'doc' | 'log'>('doc')
  const [includePathType, setIncludePathType] = useState<'file' | 'dir' | 'glob'>('file')
  const [extraIncludes, setExtraIncludes] = useState<ScopeEntry[]>([])
  const [extraExcludes, setExtraExcludes] = useState('')
  const [note, setNote] = useState('')
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState('')
  const [preflight, setPreflight] = useState<PullBundlePreflight | null>(null)
  const [preflightContextKey, setPreflightContextKey] = useState('')
  const [preflighting, setPreflighting] = useState(false)
  const [expandedHistory, setExpandedHistory] = useState<Record<string, boolean>>({})
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [pendingActions, setPendingActions] = useState<Record<string, boolean>>({})
  const [createOpen, setCreateOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [leftOutOpen, setLeftOutOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const defaultLocationId = useMemo(() => {
    if (service.locations.length === 1) return service.locations[0].location_id
    return service.locations.find((location) => location.is_primary)?.location_id ?? ''
  }, [service.locations])
  const [locationId, setLocationId] = useState(defaultLocationId)

  const selectedNodeViewer = useMemo(
    () => service.node_viewer?.find((entry) => entry.location_id === locationId),
    [locationId, service.node_viewer],
  )
  const selectedNodeSync = useMemo(
    () => service.node_sync?.find((entry) => entry.location_id === locationId && entry.direction === 'from_node'),
    [locationId, service.node_sync],
  )
  const activeExtraExcludes = useMemo(
    () => advancedOpen
      ? extraExcludes
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean)
      : [],
    [advancedOpen, extraExcludes],
  )
  const preflightAuthorityContextKey = useMemo(
    () => JSON.stringify({
      service_id: service.service_id,
      location_id: locationId,
      saved_scope_generated_at: service.saved_scope_generated_at ?? '',
      service_data_as_of: service.freshness?.data_as_of ?? service.data_as_of ?? '',
      service_truth_as_of: service.freshness?.truth_as_of ?? service.truth_as_of ?? '',
      service_freshness_state: service.freshness?.freshness_state ?? service.freshness_state ?? '',
      node_data_as_of: selectedNodeViewer?.data_as_of ?? '',
      node_truth_as_of: selectedNodeViewer?.truth_as_of ?? '',
      node_freshness_state: selectedNodeViewer?.freshness_state ?? '',
      node_manifest_updated_at: selectedNodeViewer?.manifest_updated_at ?? '',
      node_sync_timestamp: selectedNodeSync?.timestamp ?? '',
      extra_includes: advancedOpen ? extraIncludes.map((entry) => `${entry.kind}:${entry.path_type}:${entry.path}:${entry.enabled}`).sort() : [],
      extra_excludes: activeExtraExcludes,
    }),
    [
      activeExtraExcludes,
      advancedOpen,
      extraIncludes,
      locationId,
      selectedNodeSync?.timestamp,
      selectedNodeViewer?.data_as_of,
      selectedNodeViewer?.freshness_state,
      selectedNodeViewer?.manifest_updated_at,
      selectedNodeViewer?.truth_as_of,
      service.data_as_of,
      service.freshness?.data_as_of,
      service.freshness?.freshness_state,
      service.freshness?.truth_as_of,
      service.freshness_state,
      service.saved_scope_generated_at,
      service.service_id,
      service.truth_as_of,
    ],
  )

  useEffect(() => {
    setLocationId(defaultLocationId)
    setPreflight(null)
    setPreflightContextKey('')
    setMessage('')
  }, [defaultLocationId, service.service_id, refreshKey])

  useEffect(() => {
    let cancelled = false

    const refreshPending = async () => {
      const keys = Object.keys(sessionStorage)
      const pending: Record<string, boolean> = {}
      for (const key of keys) {
        if (key.startsWith('pending:')) pending[key] = true
      }

      if (disabled) {
        if (!cancelled) setPendingActions(pending)
        return
      }

      const result = await getActionLocks(service.service_id)
      if (cancelled) return
      if (isApiError(result)) {
        setPendingActions(pending)
        return
      }

      const bundleLocked = result.locks.some((lock) => lock.action_key === actionKey)
      if (bundleLocked) {
        pending[sessionKey] = true
      } else {
        sessionStorage.removeItem(sessionKey)
        delete pending[sessionKey]
      }
      setPendingActions(pending)
    }

    void refreshPending()
    const timer = window.setInterval(() => {
      void refreshPending()
    }, 5000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [actionKey, disabled, service.service_id, sessionKey])

  useEffect(() => {
    if (disabled) return
    listPullBundles(service.service_id).then((result) => {
      if (!isApiError(result)) setHistory(result)
    })
  }, [disabled, refreshKey, service.service_id])

  useEffect(() => {
    setPreflight(null)
    setPreflightContextKey('')
    setMessage('')
  }, [refreshKey, service.scope_entries])

  const savedScope = useMemo(
    () => service.scope_entries.filter((entry) => entry.enabled && entry.kind !== 'exclude'),
    [service.scope_entries],
  )
  const savedScopeSummary = useMemo(() => {
    const counts = { repo: 0, code: 0, doc: 0, log: 0 }
    for (const entry of savedScope) {
      if (entry.kind === 'repo' || entry.kind === 'code' || entry.kind === 'doc' || entry.kind === 'log') counts[entry.kind] += 1
    }
    return counts
  }, [savedScope])
  const latestBundleWithFiles = useMemo(() => {
    if (bundleResult?.files?.length) return bundleResult
    return history.find((bundle) => (bundle.files?.length ?? 0) > 0) ?? null
  }, [bundleResult, history])
  const cachedPreflightChanged = Boolean(preflight && preflightContextKey && preflightContextKey !== preflightAuthorityContextKey)
  const cachedPreflightAuthorityStale = Boolean(
    preflight?.status === 'ok' &&
    timestampBefore(preflight.source_authority?.updated_at || preflight.freshness?.data_as_of, selectedNodeViewer?.truth_as_of || service.freshness?.truth_as_of || service.truth_as_of),
  )
  const cachedPreflightStale = cachedPreflightChanged || cachedPreflightAuthorityStale
  const preflightReadyToCreate = Boolean(preflight && preflight.status === 'ok' && !cachedPreflightStale)
  const preflightBlocksCreate = Boolean(preflight && (preflight.status !== 'ok' || cachedPreflightStale))

  function addExtraInclude() {
    const trimmed = includePath.trim()
    if (!trimmed) return
    setExtraIncludes((current) =>
      uniqueByPath([
        ...current,
        {
          kind: includeKind,
          path: trimmed,
          path_type: includePathType,
          source: 'user_added',
          enabled: true,
        },
      ]),
    )
    setIncludePath('')
  }

  function initiateCreate() {
    if (!preflightReadyToCreate) {
      setMessage('Create is blocked until scope check is Ready and pull authority is fresh.')
      return
    }
    setConfirmOpen(true)
  }

  function pullRequestPayload() {
    return {
      location_id: locationId || undefined,
      extra_includes: advancedOpen ? extraIncludes : [],
      extra_excludes: activeExtraExcludes,
      note,
    }
  }

  async function runPreflight() {
    setPreflighting(true)
    setMessage('')
    try {
      const result = await preflightPullBundle(service.service_id, pullRequestPayload())
      setPreflight(result as PullBundlePreflight)
      setPreflightContextKey(preflightAuthorityContextKey)
      if ((result as PullBundlePreflight).status !== 'ok') {
        setMessage((result as PullBundlePreflight).message || 'Pull bundle preflight failed.')
        return false
      }
      setMessage('Pull bundle preflight passed. Source authority is explicit.')
      return true
    } finally {
      setPreflighting(false)
    }
  }

  async function handleCreate() {
    sessionStorage.setItem(sessionKey, 'true')
    setPendingActions(prev => ({ ...prev, [sessionKey]: true }))
    setConfirmOpen(false)
    setCreating(true)
    setMessage('')

    try {
      const ready = await runPreflight()
      if (!ready) return
      const result = await createPullBundle(service.service_id, pullRequestPayload())
      if (isApiError(result)) {
        setMessage(result.message)
        return
      }
      setBundleResult(result)
      setHistory((current) => [result, ...current])
      setMessage(`Bundle ${result.bundle_id} created.`)
    } finally {
      setCreating(false)
      sessionStorage.removeItem(sessionKey)
      setPendingActions(prev => { const next = { ...prev }; delete next[sessionKey]; return next })
    }
  }

  function renderComposition(composition?: DependencyComposition) {
    if (!composition) return null
    const topLanguages = composition.language_percentages.slice(0, 4)
    const models = composition.models ?? []
    return (
      <div className="mt-3 rounded-lg border border-gray-800 bg-black/20 p-3">
        <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Composition</div>
        <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
          {topLanguages.length === 0 ? (
            <span className="text-gray-600">No file mix yet</span>
          ) : (
            topLanguages.map((item) => (
              <span key={item.name} className="rounded-full border border-gray-800 px-2 py-1 text-gray-300">
                {item.name} {item.percentage}%
              </span>
            ))
          )}
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
        {models.length > 0 && (
          <div className="mt-2 text-xs text-gray-400">
            Models: {models.map((model) => `${model.name} (${model.category})`).join(', ')}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <AccordionSection
        title="Create Bundle"
        open={createOpen}
        onToggle={() => setCreateOpen((current) => !current)}
        icon={<PackagePlus className="h-4 w-4 text-cyan-400" />}
        summary={`${savedScope.length} saved entries · ${extraIncludes.length} one-run extras · ${extraExcludes.split('\n').map((line) => line.trim()).filter(Boolean).length} excludes`}
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="mt-1 text-sm text-gray-500">
              Pull the selected node-defined scope into a versioned local mirror. Remote bundles require Sync From Node first.
              Clean-to-commit / backup eligibility still requires a clean repo, fresh pull authority, reviewed skipped entries, and no unresolved exposure findings.
            </p>
            <p className="mt-2 text-xs text-cyan-200">Bundle profile: backup-clean</p>
            <p className="mt-1 text-xs text-amber-200">Backup readiness: review required</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => void runPreflight()}
              disabled={disabled || preflighting}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-200 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
            >
              {preflighting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Settings2 className="h-4 w-4" />}
              Check scope
            </button>
            <button
              onClick={initiateCreate}
              disabled={disabled || creating || pendingActions[`pending:pull_bundle:${service.service_id}`] || !locationId || !preflightReadyToCreate}
              className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-black transition-colors hover:bg-gray-200 disabled:opacity-50"
            >
              {creating || pendingActions[`pending:pull_bundle:${service.service_id}`] ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}
              {creating || pendingActions[`pending:pull_bundle:${service.service_id}`] ? 'Creating' : 'Create bundle'}
            </button>
          </div>
        </div>

        <div className="mt-4 rounded-xl border border-gray-800 bg-gray-900 p-3">
          <div className="grid gap-3 md:grid-cols-[1.2fr,2fr]">
            <label className="text-xs text-gray-400">
              Source location
              <select
                value={locationId}
                onChange={(event) => {
                  setLocationId(event.target.value)
                  setPreflight(null)
                }}
                className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                disabled={disabled}
              >
                <option value="">Select a location</option>
                {service.locations.map((location) => (
                  <option key={location.location_id} value={location.location_id}>
                    {location.location_id} · {location.server_id}
                  </option>
                ))}
              </select>
            </label>
            <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2 text-xs text-gray-300">
              {preflight ? (
                <>
                  <div className={preflight.status === 'ok' ? 'text-green-300' : 'text-amber-200'}>
                    {cachedPreflightStale ? 'Needs refresh' : preflight.status === 'ok' ? 'Ready' : 'Blocked'} · {cachedPreflightStale ? 'Cached Ready is stale. Run Check scope again.' : preflight.message}
                  </div>
                  <div className="mt-1 text-gray-500">
                    Authority {preflight.source_authority?.source ?? 'unknown'} · includes {preflight.include_count ?? 0} · excludes {preflight.exclude_count ?? 0} · profile {preflight.bundle_profile ?? 'backup-clean'}
                  </div>
                  <div className="mt-2 grid gap-1 text-[11px] text-gray-500 md:grid-cols-2">
                    <div>Node-local authority: {formatTimestampLabel(preflight.node_local_scope_timestamp)}</div>
                    <div>Control Center scope: {formatTimestampLabel(preflight.control_center_scope_timestamp)}</div>
                    <div>Authority updated: {formatTimestampLabel(preflight.source_authority?.updated_at)}</div>
                    <div>{preflight.vpn_required ? 'VPN required for live verification' : 'No VPN required for this source'}</div>
                  </div>
                  {preflight.freshness?.freshness_state && preflight.freshness.freshness_state !== 'Fresh' && (
                    <div className="mt-2 rounded-lg border border-amber-800/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-100">
                      Freshness: {freshnessDisplayLabel(preflight.freshness.freshness_state)}
                      {preflight.freshness.refresh_action ? ` · ${preflight.freshness.refresh_action}` : ''}
                      {preflight.freshness.stale_reason ? ` · ${preflight.freshness.stale_reason}` : ''}
                      <div className="mt-1 text-amber-100/80">
                        Truth source: {freshnessSourceLabel(preflight.freshness.freshness_source)} · Data as of: {formatTimestampLabel(preflight.freshness.data_as_of)} · Truth as of: {formatTimestampLabel(preflight.freshness.truth_as_of)} · Last verified: {formatTimestampLabel(preflight.freshness.data_as_of)}
                      </div>
                    </div>
                  )}
                  {preflight.authority_stale && (
                    <div className="mt-2 rounded-lg border border-amber-800/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-100">
                      {authorityBlockerCopy(preflight)}
                    </div>
                  )}
                  {cachedPreflightStale && (
                    <div className="mt-2 rounded-lg border border-amber-800/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-100">
                      Cached Ready is no longer current for this service truth. Run Check scope before creating a bundle.
                    </div>
                  )}
                  <div className={`mt-2 rounded-lg border px-3 py-2 text-xs ${preflight.status === 'ok' ? 'border-cyan-900/40 bg-cyan-950/20 text-cyan-100' : 'border-amber-800/50 bg-amber-950/30 text-amber-100'}`}>
                    Clean-to-commit / backup: {preflight.status === 'ok' && !cachedPreflightStale
                      ? 'scope mirror is allowed, but repo cleanliness, skipped entries, and exposure findings still need review.'
                      : 'blocked until scope check is Ready and authority is fresh.'}
                  </div>
                  {preflight.status !== 'ok' && preflight.blocked_reasons && preflight.blocked_reasons.length > 0 && (
                    <ul className="mt-2 space-y-1 text-[11px] text-amber-100">
                      {preflight.blocked_reasons.map((reason) => (
                        <li key={reason}>- {reason}</li>
                      ))}
                    </ul>
                  )}
                  {preflight.root && <div className="mt-1 font-mono text-[11px] text-gray-500 break-all">{preflight.root}</div>}
                </>
              ) : (
                <div className="text-gray-500">Run scope check before pulling. The bundle will also check this before it creates files.</div>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-3">
            <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Saved scope summary</div>
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-3 text-sm text-gray-300">
                <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Repo</div>
                <div className="mt-1 text-lg font-medium text-white">{savedScopeSummary.repo}</div>
              </div>
              <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-3 text-sm text-gray-300">
                <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Code</div>
                <div className="mt-1 text-lg font-medium text-white">{savedScopeSummary.code}</div>
              </div>
              <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-3 text-sm text-gray-300">
                <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Doc</div>
                <div className="mt-1 text-lg font-medium text-white">{savedScopeSummary.doc}</div>
              </div>
              <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-3 text-sm text-gray-300">
                <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Log</div>
                <div className="mt-1 text-lg font-medium text-white">{savedScopeSummary.log}</div>
              </div>
            </div>
            <div className="mt-3 text-xs text-gray-500">
              Saved scope paths are managed in the Scope panel. Bundle creation uses that snapshot without repeating the full list here.
            </div>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900 p-3">
            <button
              type="button"
              onClick={() => setAdvancedOpen((current) => !current)}
              className="flex w-full items-center justify-between text-left"
            >
              <span className="text-xs uppercase tracking-[0.16em] text-gray-500">Advanced one-run overrides</span>
              {advancedOpen ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
            </button>
            {!advancedOpen && (
              <div className="mt-3 text-sm text-gray-500">
                Off by default. Normal pulls use the node-defined scope only.
              </div>
            )}
            {advancedOpen && (
              <>
            <div className="mt-3 grid gap-3 md:grid-cols-[2fr,1fr,1fr,auto]">
              <input
                value={includePath}
                onChange={(event) => setIncludePath(event.target.value)}
                className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                placeholder="/path/to/extra/file.log"
                disabled={disabled}
              />
              <select
                value={includeKind}
                onChange={(event) => setIncludeKind(event.target.value as 'code' | 'doc' | 'log')}
                className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                disabled={disabled}
              >
                <option value="code">Code</option>
                <option value="doc">Doc</option>
                <option value="log">Log</option>
              </select>
              <select
                value={includePathType}
                onChange={(event) => setIncludePathType(event.target.value as 'file' | 'dir' | 'glob')}
                className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                disabled={disabled}
              >
                <option value="file">File</option>
                <option value="dir">Dir</option>
                <option value="glob">Glob</option>
              </select>
              <button
                onClick={addExtraInclude}
                disabled={disabled}
                className="rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-200 transition-colors hover:border-cyan-500 hover:text-white disabled:opacity-50"
              >
                Add
              </button>
            </div>

            <div className="mt-3 space-y-2">
              {extraIncludes.length === 0 ? (
                <div className="text-sm text-gray-500">No extra include paths for this run.</div>
              ) : (
                extraIncludes.map((entry) => (
                  <div key={`${entry.kind}:${entry.path}`} className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950 px-3 py-2">
                    <div>
                      <div className="font-mono text-xs text-gray-300">{entry.path}</div>
                      <div className="mt-1 text-[11px] uppercase tracking-[0.14em] text-gray-500">
                        {entry.kind} · {entry.path_type}
                      </div>
                    </div>
                    <button
                      onClick={() => setExtraIncludes((current) => current.filter((candidate) => candidate.path !== entry.path))}
                      className="text-xs text-red-300 transition-colors hover:text-red-200"
                    >
                      Remove
                    </button>
                  </div>
                ))
              )}
            </div>

            <label className="mt-4 block text-sm text-gray-300">
              <div className="mb-1">Extra excludes</div>
              <textarea
                value={extraExcludes}
                onChange={(event) => setExtraExcludes(event.target.value)}
                className="min-h-28 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                placeholder="One path or glob per line"
                disabled={disabled}
              />
            </label>
              </>
            )}

            <label className="mt-4 block text-sm text-gray-300">
              <div className="mb-1">Pull note</div>
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                className="min-h-24 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500"
                placeholder="Optional note for this pull bundle."
                disabled={disabled}
              />
            </label>
          </div>
        </div>

        <div className="mt-4 text-sm text-gray-400">
          {message || 'Bundle creation stays read-safe. Files are mirrored under the original tree shape, and doc/log labels stay in metadata.'}
        </div>
        {bundleResult && (
          <div className="mt-3 rounded-xl border border-green-800 bg-green-950/20 p-3 text-sm text-green-200">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-medium">{bundleResult.bundle_id}</div>
                <div className="mt-1 text-xs text-green-300/80">
                  {bundleResult.source_tree_path ?? bundleResult.bundle_path}
                </div>
              </div>
              <StatusBadge status="ok" />
            </div>
            {bundleResult.diff_summary && (
              <div className="mt-3 rounded-lg border border-amber-800/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
                {bundleResult.diff_summary.summary}
              </div>
            )}
            {bundleResult.note && (
              <div className="mt-3 rounded-lg border border-gray-800 bg-black/20 px-3 py-2 text-xs text-gray-200">
                {bundleResult.note}
              </div>
            )}
            {bundleResult.authority && (
              <div className="mt-3 rounded-lg border border-cyan-900/40 bg-cyan-950/20 px-3 py-2 text-xs text-cyan-100">
                Authority: {bundleResult.authority.source} · {bundleResult.authority.root}
              </div>
            )}
            <div className="mt-3 rounded-lg border border-cyan-900/40 bg-cyan-950/20 px-3 py-2 text-xs text-cyan-100">
              {bundleProfileLabel(bundleResult)}
            </div>
            <div className="mt-2 rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-100">
              Backup readiness: {readinessStatusLabel(bundleResult)}
              <div className="mt-1 text-amber-100/80">
                Unresolved exposures: {unresolvedExposureCount(bundleResult)} · skipped review: {skippedReviewCount(bundleResult)}
              </div>
            </div>
            {renderComposition(bundleResult.dependency_context?.composition)}
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-green-900/40 bg-black/20 p-3">
                <div className="text-xs uppercase tracking-[0.16em] text-green-300/80">Pulled files</div>
                <div className="mt-2 max-h-56 space-y-1 overflow-auto">
                  {(bundleResult.files ?? []).length === 0 ? (
                    <div className="text-xs text-green-200/70">No copied files recorded.</div>
                  ) : (
                    (bundleResult.files ?? []).slice(0, 40).map((file) => (
                      <div key={`${file.target_path}:${file.sha256}`} className="rounded border border-green-900/30 px-2 py-1">
                        <div className="font-mono text-[11px] break-all">{file.relative_path}</div>
                        <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-green-300/70">{file.kind}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>
              <div className="rounded-lg border border-yellow-900/40 bg-black/20 p-3">
                {(bundleResult.exposure_findings?.length ?? 0) > 0 && (
                  <div className="mb-3 rounded-lg border border-yellow-900/30 bg-yellow-950/20 px-3 py-2 text-xs text-yellow-200">
                    {bundleResult.exposure_findings?.length} exposure finding{bundleResult.exposure_findings?.length === 1 ? '' : 's'} in pulled files.
                    {countSummaryLabel(exposureSummary(bundleResult)) ? ` ${countSummaryLabel(exposureSummary(bundleResult))}` : ''}
                  </div>
                )}
                {countSummaryLabel(skippedSummary(bundleResult)) && (
                  <div className="mb-3 rounded-lg border border-yellow-900/30 bg-yellow-950/20 px-3 py-2 text-xs text-yellow-200">
                    Skipped summary: {countSummaryLabel(skippedSummary(bundleResult))}
                  </div>
                )}
                <div className="text-xs uppercase tracking-[0.16em] text-yellow-200/80">Missed scope</div>
                <div className="mt-2 max-h-56 space-y-1 overflow-auto">
                  {(bundleResult.skipped_entries ?? []).length === 0 ? (
                    <div className="text-xs text-green-200/70">No skipped scope entries.</div>
                  ) : (
                    (bundleResult.skipped_entries ?? []).map((entry) => (
                      <div key={`${entry.path}:${entry.reason}`} className="rounded border border-yellow-900/30 px-2 py-1">
                        <div className="font-mono text-[11px] break-all">{entry.path}</div>
                        <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-yellow-200/70">
                          {entry.kind} · {entry.path_type} · {entry.reason}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </AccordionSection>

      <AccordionSection
        title="Bundle History"
        open={historyOpen}
        onToggle={() => setHistoryOpen((current) => !current)}
        icon={<Download className="h-4 w-4 text-cyan-400" />}
        summary={history.length > 0 ? `${history.length} bundles · latest ${new Date(history[0].created_at).toLocaleString()}` : 'No bundle history yet'}
      >
        <div className="mt-3 space-y-3">
          {history.length === 0 ? (
            <div className="text-sm text-gray-500">No bundle history yet.</div>
          ) : (
            history.map((bundle) => (
              <div key={bundle.bundle_id} className="rounded-xl border border-gray-800 bg-gray-900 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedHistory((current) => ({
                        ...current,
                        [bundle.bundle_id]: !current[bundle.bundle_id],
                      }))
                    }
                    className="flex min-w-0 flex-1 items-start gap-2 text-left"
                  >
                    {expandedHistory[bundle.bundle_id] ? (
                      <ChevronDown className="mt-0.5 h-4 w-4 text-gray-500" />
                    ) : (
                      <ChevronRight className="mt-0.5 h-4 w-4 text-gray-500" />
                    )}
                    <div className="min-w-0">
                      <div className="font-mono text-xs text-gray-300 break-all">{bundle.bundle_id}</div>
                      <div className="mt-1 text-xs text-gray-500">
                        {new Date(bundle.created_at).toLocaleString()} · {bundle.file_count} files
                      </div>
                      {bundle.diff_summary && (
                        <div className="mt-2 inline-flex rounded-full border border-amber-900/50 bg-amber-950/20 px-2 py-0.5 text-[11px] text-amber-200">
                          {bundle.diff_summary.summary}
                        </div>
                      )}
                    </div>
                  </button>
                  <div className="text-right text-xs text-gray-400">
                    <div>{bundle.docs_count} docs</div>
                    <div>{bundle.logs_count} logs</div>
                    <div>{bundle.skipped_entry_count ?? 0} missed</div>
                  </div>
                </div>
                {expandedHistory[bundle.bundle_id] && (
                  <div className="mt-3 space-y-3">
                    {(bundle.note || bundle.authority || bundle.dependency_context || (bundle.exposure_findings?.length ?? 0) > 0) && (
                      <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Bundle Notes</div>
                        {bundle.note && <div className="mt-2 text-sm text-gray-300">{bundle.note}</div>}
                        <div className="mt-2 rounded-lg border border-cyan-900/40 bg-cyan-950/20 px-3 py-2 text-xs text-cyan-100">
                          {bundleProfileLabel(bundle)}
                        </div>
                        <div className="mt-2 rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-100">
                          Backup readiness: {readinessStatusLabel(bundle)}
                          <div className="mt-1 text-amber-100/80">
                            Unresolved exposures: {unresolvedExposureCount(bundle)} · skipped review: {skippedReviewCount(bundle)}
                          </div>
                        </div>
                        {bundle.authority && (
                          <div className="mt-2 rounded-lg border border-cyan-900/40 bg-cyan-950/20 px-3 py-2 text-xs text-cyan-100">
                            Authority: {bundle.authority.source} · {bundle.authority.root}
                            {bundle.authority.updated_at ? ` · synced ${new Date(bundle.authority.updated_at).toLocaleString()}` : ''}
                          </div>
                        )}
                        {bundle.dependency_context && (
                          <div className="mt-3 grid gap-3 md:grid-cols-2">
                            <div>
                              <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Dependencies</div>
                              <div className="mt-2 space-y-1">
                                {(bundle.dependency_context.dependencies ?? []).length === 0 ? (
                                  <div className="text-xs text-gray-600">None</div>
                                ) : (
                                  bundle.dependency_context.dependencies?.map((dep, idx) => (
                                    <div key={idx} className="text-xs text-gray-300">
                                      {dep.kind} · {dep.name} · {dep.host || 'local'}{dep.port ? `:${dep.port}` : ''}
                                    </div>
                                  ))
                                )}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] uppercase tracking-[0.16em] text-gray-500">Cross-System Notes</div>
                              <div className="mt-2 space-y-1">
                                {(bundle.dependency_context.cross_dependencies ?? []).length === 0 ? (
                                  <div className="text-xs text-gray-600">None</div>
                                ) : (
                                  bundle.dependency_context.cross_dependencies?.map((dep, idx) => (
                                    <div key={idx} className="text-xs text-gray-300">
                                      {dep.kind} · {dep.name} · {dep.host || 'local'}{dep.port ? `:${dep.port}` : ''}
                                    </div>
                                  ))
                                )}
                              </div>
                            </div>
                          </div>
                        )}
                        {renderComposition(bundle.dependency_context?.composition)}
                        {(bundle.exposure_findings?.length ?? 0) > 0 && (
                          <div className="mt-3">
                            <div className="text-[11px] uppercase tracking-[0.16em] text-yellow-300">Exposure Notes</div>
                            <div className="mt-2 rounded border border-yellow-900/30 bg-yellow-950/20 px-2 py-1 text-xs text-yellow-100/90">
                              {bundle.exposure_findings?.length} total
                              {countSummaryLabel(exposureSummary(bundle)) ? ` · ${countSummaryLabel(exposureSummary(bundle))}` : ''}
                            </div>
                            <div className="mt-2 space-y-1">
                              {bundle.exposure_findings?.slice(0, 12).map((finding, idx) => (
                                <div key={idx} className="text-xs text-yellow-100/90">
                                  {finding.relative_path} · {finding.finding_kind}{finding.variable_name ? ` · ${finding.variable_name}` : ''} · line {finding.line_number}
                                </div>
                              ))}
                              {(bundle.exposure_findings?.length ?? 0) > 12 && (
                                <div className="text-xs text-yellow-100/70">Showing first 12 exposure findings.</div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {(bundle.diff_entries?.length ?? 0) > 0 && (
                      <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Diff</div>
                        <div className="mt-2 max-h-48 space-y-1 overflow-auto">
                          {bundle.diff_entries?.map((entry, idx) => (
                            <div key={`${bundle.bundle_id}:${entry.relative_path}:${idx}`} className="flex items-center gap-2 rounded border border-gray-800 px-2 py-1 text-xs">
                              <span className={entry.change === 'added' ? 'text-green-400' : entry.change === 'removed' ? 'text-red-400' : 'text-amber-300'}>
                                {entry.change === 'added' ? '+' : entry.change === 'removed' ? '-' : '~'}
                              </span>
                              <span className="font-mono text-gray-300 break-all">{entry.relative_path}</span>
                              <span className="ml-auto uppercase tracking-[0.14em] text-gray-500">{entry.kind}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
                      <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Pulled files</div>
                      <div className="mt-2 max-h-56 space-y-1 overflow-auto">
                        {(bundle.files ?? []).length === 0 ? (
                          <div className="text-xs text-gray-500">No copied file list stored for this bundle.</div>
                        ) : (
                          (bundle.files ?? []).map((file) => (
                            <div key={`${bundle.bundle_id}:${file.target_path}:${file.sha256}`} className="rounded border border-gray-800 px-2 py-1">
                              <div className="font-mono text-[11px] text-gray-300 break-all">{file.relative_path}</div>
                              <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-gray-500">{file.kind}</div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                    <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
                      <div className="text-xs uppercase tracking-[0.16em] text-gray-500">Missed scope</div>
                      {countSummaryLabel(skippedSummary(bundle)) && (
                        <div className="mt-2 rounded border border-gray-800 px-2 py-1 text-xs text-gray-300">
                          Skipped summary: {countSummaryLabel(skippedSummary(bundle))}
                        </div>
                      )}
                      <div className="mt-2 max-h-56 space-y-1 overflow-auto">
                        {(bundle.skipped_entries ?? []).length === 0 ? (
                          <div className="text-xs text-gray-500">No missed scope entries.</div>
                        ) : (
                          (bundle.skipped_entries ?? []).map((entry) => (
                            <div key={`${bundle.bundle_id}:${entry.path}:${entry.reason}`} className="rounded border border-gray-800 px-2 py-1">
                              <div className="font-mono text-[11px] text-gray-300 break-all">{entry.path}</div>
                              <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-gray-500">
                                {entry.kind} · {entry.path_type} · {entry.reason}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </AccordionSection>

      <AccordionSection
        title="Left Out"
        open={leftOutOpen}
        onToggle={() => setLeftOutOpen((current) => !current)}
        icon={<Archive className="h-4 w-4 text-gray-500" />}
        summary={`${service.scope_entries.filter(e => e.kind === 'exclude' && e.enabled).length} saved excludes · ${(latestBundleWithFiles?.skipped_entries ?? []).length} skipped entries`}
      >
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
            <div className="text-xs uppercase tracking-[0.16em] text-gray-500 mb-2">Saved Excludes</div>
            <div className="space-y-1 max-h-40 overflow-auto">
              {service.scope_entries.filter(e => e.kind === 'exclude' && e.enabled).length === 0 ? (
                <div className="text-xs text-gray-600">None</div>
              ) : (
                service.scope_entries.filter(e => e.kind === 'exclude' && e.enabled).map((e, idx) => (
                  <div key={idx} className="font-mono text-[10px] text-gray-400 break-all">{e.path}</div>
                ))
              )}
            </div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
            <div className="text-xs uppercase tracking-[0.16em] text-gray-500 mb-2">One-run Excludes</div>
            <div className="space-y-1 max-h-40 overflow-auto">
              {!extraExcludes.trim() ? (
                <div className="text-xs text-gray-600">None</div>
              ) : (
                extraExcludes.split('\n').filter(Boolean).map((e, idx) => (
                  <div key={idx} className="font-mono text-[10px] text-gray-400 break-all">{e.trim()}</div>
                ))
              )}
            </div>
          </div>
          <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
            <div className="text-xs uppercase tracking-[0.16em] text-gray-500 mb-2">Latest Skipped</div>
            <div className="space-y-1 max-h-40 overflow-auto">
              {(latestBundleWithFiles?.skipped_entries ?? []).length === 0 ? (
                <div className="text-xs text-gray-600">None</div>
              ) : (
                (latestBundleWithFiles?.skipped_entries ?? []).map((entry, idx) => (
                  <div key={idx} className="font-mono text-[10px] text-gray-400 break-all">
                    {entry.path} <span className="text-gray-600">({entry.reason})</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </AccordionSection>

      {confirmOpen && ACTION_EXPLAIN['pull_bundle'] && (
        <ConfirmationModal
          open={confirmOpen}
          title={ACTION_EXPLAIN['pull_bundle'].title}
          willDo={ACTION_EXPLAIN['pull_bundle'].happens}
          willNotChange={ACTION_EXPLAIN['pull_bundle'].untouched}
          writesTo={ACTION_EXPLAIN['pull_bundle'].writesTo}
          onConfirm={handleCreate}
          onCancel={() => setConfirmOpen(false)}
        />
      )}
    </div>
  )
}
