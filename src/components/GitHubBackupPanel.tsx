import { useEffect, useState } from 'react'
import { GitBranch, LoaderCircle, Play, ShieldCheck } from 'lucide-react'
import { getGithubBackupReadiness, runGithubBackup, runGithubBackupDryRun } from '../api/client'
import type { GitHubBackupResult } from '../types/switchboard'
import { isApiError } from '../types/switchboard'
import { StatusBadge } from './StatusBadge'

interface Props {
  workspaceId?: string
  disabled?: boolean
}

export function GitHubBackupPanel({ workspaceId, disabled }: Props) {
  const [result, setResult] = useState<GitHubBackupResult | null>(null)
  const [message, setMessage] = useState('')
  const [running, setRunning] = useState<'readiness' | 'dry-run' | 'run' | ''>('')

  useEffect(() => {
    if (disabled) return
    void refresh()
  }, [disabled, workspaceId])

  async function refresh() {
    setRunning('readiness')
    const response = await getGithubBackupReadiness(workspaceId)
    setRunning('')
    if (isApiError(response)) {
      setMessage(response.message)
      return
    }
    setResult(response)
    setMessage('')
  }

  async function dryRun() {
    setRunning('dry-run')
    const response = await runGithubBackupDryRun({ workspace_id: workspaceId, dry_run: true })
    setRunning('')
    if (isApiError(response)) {
      setMessage(response.message)
      return
    }
    setResult(response)
    setMessage('Dry-run recorded.')
  }

  async function runBackup() {
    setRunning('run')
    const response = await runGithubBackup({ workspace_id: workspaceId, dry_run: false })
    setRunning('')
    if (isApiError(response)) {
      setMessage(response.message)
      return
    }
    setResult(response)
    setMessage(`${response.pushed_count ?? 0} repositories pushed.`)
  }

  const blocked = result?.repositories.filter((repo) => !repo.eligible).slice(0, 4) ?? []

  return (
    <section className="rounded-2xl border border-gray-800 bg-gray-900 p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
            <GitBranch className="h-4 w-4 text-cyan-400" />
            GitHub Backup
          </div>
          <div className="mt-1 text-sm text-gray-500">
            Readiness first, push only repos that are clean, allowlisted, and already credentialed.
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void dryRun()}
            disabled={disabled || Boolean(running)}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-200 hover:border-cyan-500 disabled:opacity-50"
          >
            {running === 'dry-run' ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
            Dry Run
          </button>
          <button
            type="button"
            onClick={() => void runBackup()}
            disabled={disabled || Boolean(running) || (result?.eligible_count ?? 0) === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs font-medium text-black hover:bg-gray-200 disabled:opacity-50"
          >
            {running === 'run' ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Backup Review Ready
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Repos</div>
          <div className="mt-1 text-xl font-semibold text-white">{result?.repository_count ?? 0}</div>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Eligible</div>
          <div className="mt-1 text-xl font-semibold text-green-200">{result?.eligible_count ?? 0}</div>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Blocked</div>
          <div className="mt-1 text-xl font-semibold text-amber-200">{result?.blocked_count ?? 0}</div>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.14em] text-gray-500">Last</div>
          <div className="mt-1"><StatusBadge status={result?.status ?? 'unverified'} /></div>
        </div>
      </div>

      {(message || result?.credential_note) && (
        <div className="mt-3 text-xs text-gray-500">{message || result?.credential_note}</div>
      )}

      {blocked.length > 0 && (
        <div className="mt-3 space-y-2">
          {blocked.map((repo) => (
            <div key={`${repo.service_id}:${repo.repo_path}`} className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2 text-xs text-gray-400">
              <div className="font-mono text-gray-300">{repo.repo_path}</div>
              <div className="mt-1">{repo.blocking_reasons.join('; ')}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
