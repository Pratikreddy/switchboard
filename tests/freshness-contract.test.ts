import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const serviceDetailPage = readFileSync(resolve(process.cwd(), 'src/pages/ServiceDetailPage.tsx'), 'utf-8')
const pullBundlePanel = readFileSync(resolve(process.cwd(), 'src/components/PullBundlePanel.tsx'), 'utf-8')
const apiClient = readFileSync(resolve(process.cwd(), 'src/api/client.ts'), 'utf-8')
const types = readFileSync(resolve(process.cwd(), 'src/types/switchboard.ts'), 'utf-8')

describe('freshness visibility contract', () => {
  it('keeps VPN-blocked node inspect results as node action results, not generic API errors', () => {
    expect(apiClient).toContain('connection_status')
    expect(apiClient).toContain('freshness_state')
    expect(apiClient).toContain('last_inspected_at')
    expect(apiClient).toContain('isApiError(res) && !(res as any).node')
    expect(types).toContain('vpn_or_network_blocked')
  })

  it('shows node freshness and sync authority timestamps in service detail', () => {
    expect(serviceDetailPage).toContain('Last inspected')
    expect(serviceDetailPage).toContain('Last verified')
    expect(serviceDetailPage).toContain('Last synced from node')
    expect(serviceDetailPage).toContain('Saved scope updated')
    expect(serviceDetailPage).toContain('Pull authority updated')
    expect(serviceDetailPage).toContain('Truth source')
    expect(serviceDetailPage).toContain('Data as of')
    expect(serviceDetailPage).toContain('Truth as of')
    expect(serviceDetailPage).toContain('VPN is off or network blocked. Turn VPN on for live verification.')
    expect(serviceDetailPage).toContain('Inspect Node is read-only')
    expect(serviceDetailPage).toContain('Sync From Node imports node state into Control Center')
  })

  it('blocks stale pull-bundle authority with clear operator copy', () => {
    expect(pullBundlePanel).toContain('authority_stale')
    expect(pullBundlePanel).toContain('node_local_scope_timestamp')
    expect(pullBundlePanel).toContain('control_center_scope_timestamp')
    expect(pullBundlePanel).toContain('Stale authority. Run Sync From Node with VPN on.')
    expect(pullBundlePanel).toContain('Manager truth is unavailable. Check 8020 before creating a bundle; 8009 only proves the Control Center API is alive.')
    expect(pullBundlePanel).toContain('Clean-to-commit / backup')
    expect(pullBundlePanel).toContain('Create is blocked until scope check is Ready and pull authority is fresh.')
    expect(pullBundlePanel).toContain('repo cleanliness, skipped entries, and exposure findings still need review')
    expect(pullBundlePanel).toContain('VPN required for live verification')
    expect(pullBundlePanel).toContain('Truth source:')
    expect(pullBundlePanel).toContain('Data as of:')
    expect(pullBundlePanel).toContain('Truth as of:')
    expect(pullBundlePanel).toContain('Last verified:')
    expect(pullBundlePanel).toContain('preflightContextKey')
    expect(pullBundlePanel).toContain('cachedPreflightStale')
    expect(pullBundlePanel).toContain('Cached Ready is stale. Run Check scope again.')
    expect(pullBundlePanel).toContain('Needs refresh')
  })

  it('shows backup-clean pull-bundle profile and compact review summaries', () => {
    expect(pullBundlePanel).toContain('Bundle profile: backup-clean · review required')
    expect(pullBundlePanel).toContain('bundle_profile')
    expect(pullBundlePanel).toContain('metadata_summaries')
    expect(pullBundlePanel).toContain('Skipped summary:')
    expect(pullBundlePanel).toContain('Showing first 12 exposure findings.')
    expect(types).toContain('PullBundleMetadataSummaries')
    expect(types).toContain('backup_clean')
  })
})
