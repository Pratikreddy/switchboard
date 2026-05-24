import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const companiesPanel = readFileSync(resolve(process.cwd(), 'src/components/CompaniesPanel.tsx'), 'utf-8')
const serviceDetailPage = readFileSync(resolve(process.cwd(), 'src/pages/ServiceDetailPage.tsx'), 'utf-8')

describe('UI load prune contract', () => {
  it('keeps company CRUD hidden until it is tested end to end', () => {
    expect(companiesPanel).toContain('COMPANY_CRUD_ENABLED = false')
    expect(companiesPanel).not.toContain('Company editing is hidden in this build')
    expect(companiesPanel).not.toContain('read-only until add/edit/delete is tested end to end')
  })

  it('keeps service detail evidence collapsed and removes the API-lab dead end', () => {
    expect(serviceDetailPage).toContain("DEFAULT_OPEN_PANELS: ServicePanelKey[] = ['runtime']")
    expect(serviceDetailPage).not.toContain('No project environment is linked to this location yet. Add one in Projects')
    expect(serviceDetailPage).not.toContain('apiLabEnvironment &&')
    expect(serviceDetailPage).not.toContain('Dedicated API Lab')
  })
})
