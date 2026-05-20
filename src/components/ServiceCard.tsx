import { Star, Shield, GitBranch } from 'lucide-react'
import type { Service, ServiceRunResult } from '../types/switchboard'
import { StatusBadge } from './StatusBadge'

interface Props {
  service: Service
  result?: ServiceRunResult
  onClick: () => void
}

export function ServiceCard({ service, result, onClick }: Props) {
  const status = result?.status ?? 'unverified'
  const ports = result?.ports ?? []
  const firewallActive = result?.firewall_active ?? false
  const dirty = result?.repo_summaries?.some((r) => r.dirty) ?? false
  const nodeViewer = service.node_viewer?.[0]
  const freshnessState = nodeViewer?.freshness_state || result?.freshness_state || service.freshness_state || ''
  const freshnessIsFresh = freshnessState === 'Fresh'
  const managerUnreachable = freshnessState === 'Manager unreachable'
  const stale = Boolean(freshnessState && !freshnessIsFresh)
  const refreshAction = nodeViewer?.refresh_action || result?.refresh_action || service.refresh_action || (managerUnreachable ? 'Check 8020' : stale ? 'Inspect Node' : '')
  const rootManifestVersion = nodeViewer?.installed_version || ''
  const managerVersion = nodeViewer?.manager_version || ''
  const managerManaged = Boolean(nodeViewer?.manager_managed)
  const rootManifestStale = Boolean(freshnessIsFresh && managerManaged && managerVersion && rootManifestVersion && managerVersion !== rootManifestVersion)
  const stateLabel = managerUnreachable ? 'Manager unreachable' : stale ? freshnessState || 'Stale cache' : ''

  return (
    <button
      onClick={onClick}
      className={`w-full rounded-xl border p-4 text-left transition-colors group ${
        managerUnreachable
          ? 'border-amber-500/50 bg-amber-950/20 hover:border-amber-400/70'
          : stale
            ? 'border-amber-800/50 bg-gray-900/70 opacity-90 hover:border-amber-600/70'
            : 'border-gray-800 bg-gray-900 hover:border-gray-600'
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-white group-hover:text-blue-400 transition-colors">
              {service.display_name}
            </span>
            {service.favorite_tier === 1 && (
              <Star className="w-3.5 h-3.5 text-yellow-400 fill-yellow-400" />
            )}
          </div>
          <div className="text-xs text-gray-500 mt-0.5">{service.service_id}</div>
        </div>
        <StatusBadge status={status} />
      </div>

      {/* Tags */}
      {service.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {service.tags.map((tag) => (
            <span key={tag} className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded">
              {tag}
            </span>
          ))}
        </div>
      )}

      {nodeViewer && (
        <div className="mb-3 flex flex-wrap gap-1">
          <span className="text-xs px-2 py-0.5 rounded border border-cyan-900/40 bg-cyan-950/20 text-cyan-200">
            {service.execution_mode}
          </span>
          {freshnessIsFresh ? (
            <span className={`text-xs px-2 py-0.5 rounded border ${
              rootManifestStale || nodeViewer.needs_install || nodeViewer.needs_upgrade
                ? 'border-amber-700 bg-amber-950/30 text-amber-200'
                : managerManaged
                  ? 'border-cyan-900/40 bg-cyan-950/20 text-cyan-200'
                  : 'border-gray-800 bg-gray-900 text-gray-400'
            }`}>
              {managerManaged ? `manager ${managerVersion || 'active'}` : `node ${rootManifestVersion || 'missing'}`}
            </span>
          ) : (
            <span className="text-xs px-2 py-0.5 rounded border border-amber-700 bg-amber-950/30 text-amber-200">
              {stateLabel || 'Stale cache'}
            </span>
          )}
          {rootManifestStale && (
            <span className="text-xs px-2 py-0.5 rounded border border-amber-700 bg-amber-950/30 text-amber-200">
              root manifest {rootManifestVersion}
            </span>
          )}
          {freshnessIsFresh && (nodeViewer.bootstrap_version || nodeViewer.needs_bootstrap) && (
            <span className="text-xs px-2 py-0.5 rounded border border-gray-800 bg-gray-900 text-gray-400">
              bootstrap {nodeViewer.bootstrap_version || (nodeViewer.needs_bootstrap ? 'needed' : '')}
            </span>
          )}
          {nodeViewer.legacy_runtime_port_label && (
            <span className="text-xs px-2 py-0.5 rounded border border-amber-700/50 bg-amber-950/20 text-amber-200">
              {nodeViewer.legacy_runtime_port_label}
            </span>
          )}
          {refreshAction && stale && (
            <span className="text-xs px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-gray-300">
              {refreshAction}
            </span>
          )}
        </div>
      )}

      {/* Ports */}
      {service.execution_mode === 'networked' && ports.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {ports.map((p) => (
            <span key={p.port} className="text-xs font-mono bg-gray-800 text-cyan-400 px-2 py-0.5 rounded">
              :{p.port}
            </span>
          ))}
        </div>
      )}

      {/* Footer indicators */}
      <div className="flex gap-3 mt-2">
        {firewallActive && (
          <span className="flex items-center gap-1 text-xs text-green-400">
            <Shield className="w-3 h-3" /> Firewall
          </span>
        )}
        {dirty && (
          <span className="flex items-center gap-1 text-xs text-yellow-400">
            <GitBranch className="w-3 h-3" /> Dirty
          </span>
        )}
        {result?.collected_at && !isNaN(new Date(result.collected_at).getTime()) && (
          <span className="ml-auto text-xs text-gray-600">
            {new Date(result.collected_at).toLocaleTimeString()}
          </span>
        )}
        {stale && !result?.collected_at && (
          <span className="ml-auto text-xs text-amber-300">
            {refreshAction || 'Needs sync'}
          </span>
        )}
      </div>
    </button>
  )
}
