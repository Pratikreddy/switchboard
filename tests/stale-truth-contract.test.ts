import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const apiClient = readFileSync(resolve(process.cwd(), 'src/api/client.ts'), 'utf-8')
const types = readFileSync(resolve(process.cwd(), 'src/types/switchboard.ts'), 'utf-8')
const serviceCard = readFileSync(resolve(process.cwd(), 'src/components/ServiceCard.tsx'), 'utf-8')
const controlCenterPage = readFileSync(resolve(process.cwd(), 'src/pages/ControlCenterPage.tsx'), 'utf-8')
const serviceDetailPage = readFileSync(resolve(process.cwd(), 'src/pages/ServiceDetailPage.tsx'), 'utf-8')
const workspacePage = readFileSync(resolve(process.cwd(), 'src/pages/WorkspacePage.tsx'), 'utf-8')

describe('stale truth contract', () => {
  it('normalizes freshness metadata across operational API payloads', () => {
    for (const token of ['data_as_of', 'truth_as_of', 'freshness_state', 'stale_reason', 'refresh_action', 'manager_health_checked_at', 'manager_health_runtime_port', 'manager_manifest_runtime_port', 'runtime_port_source']) {
      expect(types).toContain(token)
      expect(apiClient).toContain(token)
    }
    expect(apiClient).toContain('normalizeFreshness')
    expect(apiClient).toContain('normalizeRuntimeCheck')
    expect(apiClient).toContain('normalizeNodeSync')
    expect(apiClient).toContain('normalizeNodeViewer')
    expect(apiClient).toContain('normalizeWorkspaceLatest')
  })

  it('shows stale manager truth as stale instead of rendering cached node chips as current', () => {
    expect(serviceCard).toContain('Manager unreachable')
    expect(serviceCard).toContain('Stale cache')
    expect(serviceCard).toContain('Check 8020')
    expect(serviceCard).toContain('Unverified')
    expect(serviceCard).toContain('Truth source:')
    expect(serviceCard).toContain('Manager health checked:')
    expect(serviceCard).toContain('Manifest last updated:')
    expect(serviceCard).toContain('Manager live :')
    expect(serviceCard).toContain('freshnessIsFresh')
    expect(serviceCard).toContain('legacy_runtime_port_label')
    expect(serviceDetailPage).toContain('target_manager_port')
    expect(serviceDetailPage).toContain('Manager unreachable')
    expect(serviceDetailPage).toContain('8009 only proves the Control Center API')
    expect(serviceDetailPage).toContain('Manager live on 8020')
    expect(serviceDetailPage).toContain('Manager live :')
    expect(serviceDetailPage).toContain('Manifest runtime port:')
    expect(serviceDetailPage).toContain('Manager health checked:')
    expect(serviceDetailPage).toContain('Manifest last updated:')
    expect(serviceDetailPage).toContain('Truth source:')
    expect(serviceDetailPage).toContain('Data as of:')
    expect(serviceDetailPage).toContain('Truth as of:')
    expect(serviceDetailPage).toContain('cached runtime')
    expect(serviceDetailPage).toContain('legacy_runtime_port_label')
  })

  it('marks workspace latest snapshots with data and truth timestamps', () => {
    expect(workspacePage).toContain('workspaceFreshnessState')
    expect(workspacePage).toContain('Stale cache')
    expect(workspacePage).toContain('Truth source:')
    expect(workspacePage).toContain('Data as of:')
    expect(workspacePage).toContain('Truth as of:')
    expect(workspacePage).toContain('Snapshot data as of:')
  })

  it('marks company cards stale when latest snapshots are older than truth', () => {
    expect(controlCenterPage).toContain('freshness_state')
    expect(controlCenterPage).toContain('Needs Collect')
    expect(controlCenterPage).toContain('border-amber')
  })
})
