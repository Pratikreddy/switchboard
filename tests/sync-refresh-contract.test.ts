import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const serviceDetailPage = readFileSync(resolve(process.cwd(), 'src/pages/ServiceDetailPage.tsx'), 'utf-8')
const pullBundlePanel = readFileSync(resolve(process.cwd(), 'src/components/PullBundlePanel.tsx'), 'utf-8')

describe('Sync From Node freshness contract', () => {
  it('reloads all state surfaces after a node sync succeeds', () => {
    expect(serviceDetailPage).toContain('refreshAfterNodeSync')
    expect(serviceDetailPage).toContain('getService(serviceId)')
    expect(serviceDetailPage).toContain('getServiceScope(serviceId)')
    expect(serviceDetailPage).toContain('getNodeViewer(serviceId)')
    expect(serviceDetailPage).toContain('listPullBundles(serviceId)')
    expect(serviceDetailPage).toContain('Service, scope, node viewer, and pull-bundle state refreshed')
  })

  it('passes an explicit refresh key into the pull bundle panel', () => {
    expect(serviceDetailPage).toContain('pullBundleRefreshKey')
    expect(serviceDetailPage).toContain('refreshKey={pullBundleRefreshKey}')
  })

  it('uses the refresh key to clear stale pull-bundle panel state', () => {
    expect(pullBundlePanel).toContain('refreshKey?: number')
    expect(pullBundlePanel).toContain('refreshKey = 0')
    expect(pullBundlePanel).toContain('setPreflight(null)')
    expect(pullBundlePanel).toContain('setMessage')
    expect(pullBundlePanel).toContain('[disabled, refreshKey, service.service_id]')
  })
})
