import type { CollectStatus } from '../types/switchboard'

const STATUS_STYLES: Record<CollectStatus, string> = {
  ok: 'bg-green-900 text-green-300 border border-green-700',
  partial: 'bg-yellow-900 text-yellow-300 border border-yellow-700',
  auth_failed: 'bg-red-900 text-red-300 border border-red-700',
  unreachable: 'bg-red-900 text-red-300 border border-red-700',
  vpn_or_network_blocked: 'bg-orange-900 text-orange-300 border border-orange-700',
  command_missing: 'bg-orange-900 text-orange-300 border border-orange-700',
  path_missing: 'bg-orange-900 text-orange-300 border border-orange-700',
  not_git_repo: 'bg-gray-800 text-gray-400 border border-gray-600',
  dirty_repo: 'bg-yellow-900 text-yellow-300 border border-yellow-700',
  permission_limited: 'bg-orange-900 text-orange-300 border border-orange-700',
  skipped_by_exclude: 'bg-gray-800 text-gray-400 border border-gray-600',
  unverified: 'bg-gray-800 text-gray-400 border border-gray-600',
  action_in_progress: 'bg-blue-900 text-blue-300 border border-blue-700',
}

const STATUS_LABELS: Record<CollectStatus, string> = {
  ok: 'OK',
  partial: 'Partial',
  auth_failed: 'Auth Failed',
  unreachable: 'Unreachable',
  vpn_or_network_blocked: 'VPN Blocked',
  command_missing: 'Cmd Missing',
  path_missing: 'Path Missing',
  not_git_repo: 'Not Git',
  dirty_repo: 'Dirty',
  permission_limited: 'Limited',
  skipped_by_exclude: 'Skipped',
  unverified: 'Unverified',
  action_in_progress: 'In Progress',
}

interface Props {
  status: CollectStatus
  size?: 'sm' | 'md'
}

export function StatusBadge({ status, size = 'sm' }: Props) {
  const base = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1'
  return (
    <span className={`inline-block rounded-full font-medium ${base} ${STATUS_STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  )
}
