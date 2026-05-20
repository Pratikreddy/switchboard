import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const serviceDetailPage = readFileSync(resolve(process.cwd(), 'src/pages/ServiceDetailPage.tsx'), 'utf-8')

describe('service detail surface contract', () => {
  it('removes the visible checklist and abstract view presets', () => {
    expect(serviceDetailPage).not.toContain('Visible Checklist')
    expect(serviceDetailPage).not.toContain('SERVICE_CHECKLIST')
    expect(serviceDetailPage).not.toContain('Reset checklist')
    expect(serviceDetailPage).not.toContain("(['simple', 'ops', 'full']")
    expect(serviceDetailPage).not.toContain('ViewPreset')
  })

  it('keeps port health collapsed and separates Switchboard roles', () => {
    expect(serviceDetailPage).toContain('Port Health')
    expect(serviceDetailPage).toContain('Check ports')
    expect(serviceDetailPage).toContain('port_health')
    expect(serviceDetailPage).toContain('AccordionSection')
    expect(serviceDetailPage).not.toContain("DEFAULT_OPEN_PANELS: ServicePanelKey[] = ['port_health'")
    expect(serviceDetailPage).toContain('CONTROL_CENTER_PORT = 8009')
    expect(serviceDetailPage).toContain('DEFAULT_MANAGER_PORT = 8020')
    expect(serviceDetailPage).toContain('DEV_UI_PORT = 5173')
    expect(serviceDetailPage).not.toContain('title="Network"')
  })

  it('falls back to configured repo paths instead of showing fake empty repositories', () => {
    expect(serviceDetailPage).toContain('configuredRepoPaths')
    expect(serviceDetailPage).toContain('service?.repo_paths')
    expect(serviceDetailPage).toContain("status: 'unverified'")
  })
})
