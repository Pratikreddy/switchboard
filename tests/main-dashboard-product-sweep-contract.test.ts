import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const controlCenterPage = readFileSync(resolve(process.cwd(), 'src/pages/ControlCenterPage.tsx'), 'utf-8')
const insights = readFileSync(resolve(process.cwd(), 'src/components/ControlCenterInsightPanels.tsx'), 'utf-8')
const panelRegistry = readFileSync(resolve(process.cwd(), 'src/components/controlCenterPanelRegistry.tsx'), 'utf-8')
const apiClient = readFileSync(resolve(process.cwd(), 'src/api/client.ts'), 'utf-8')
const types = readFileSync(resolve(process.cwd(), 'src/types/switchboard.ts'), 'utf-8')

describe('main dashboard product sweep contract', () => {
  it('keeps Tech Stack, How To Use, and Companies horizontally grouped on desktop', () => {
    expect(panelRegistry).toContain("id: 'overview'")
    expect(panelRegistry).toContain('grid gap-4 lg:grid-cols-3')
    expect(panelRegistry).toContain("id: 'tech-stack'")
    expect(panelRegistry).toContain("id: 'how-to-use'")
    expect(panelRegistry).toContain("id: 'companies'")
  })

  it('forces dashboard growth through a priority panel registry and removes the old hero band', () => {
    expect(controlCenterPage).toContain('CONTROL_CENTER_PANEL_GROUPS.map')
    expect(controlCenterPage).toContain('data-panel-priority')
    expect(controlCenterPage).toContain('data-panel-subgroup')
    expect(controlCenterPage).toContain('backend-status-compact')
    expect(controlCenterPage).not.toContain('Switchboard Control Center')
    expect(controlCenterPage).not.toContain('Data sync, evidence, and handoff surface')
    expect(panelRegistry).toContain('ControlCenterPanelDefinition')
    expect(panelRegistry).toContain('priority: 10')
    expect(panelRegistry).toContain('subgroup:')
  })

  it('uses task-ledger work activity with read-only branch metadata and line-count note', () => {
    expect(panelRegistry).toContain('ActivityMapPanel')
    expect(insights).toContain('Task-Ledger Activity Map')
    expect(insights).toContain('Branch/head is metadata only.')
    expect(insights).toContain('aria-label="Branch metadata"')
    expect(apiClient).toContain('/control-center/context')
    expect(types).toContain('ActivityMapSummary')
    expect(types).toContain('BranchMetadata')
    expect(types).toContain('LineNoiseSummary')
  })

  it('keeps harness context, user story intake, and agent usage note surfaces as evidence', () => {
    expect(insights).toContain('Harness Adapter Source Map')
    expect(insights).toContain('Main And Sidecar Features')
    expect(insights).toContain('User Story Evidence')
    expect(insights).toContain('Agent Usage Notes')
    expect(insights).toContain('Agent-authored notes about using Switchboard')
    expect(types).toContain('HarnessSourceMap')
    expect(types).toContain('UserStoryContext')
    expect(types).toContain('AgentUsageNotesContext')
    expect(types).toContain('FeatureMapContext')
    expect(insights).not.toContain('Git Activity Map')
    expect(insights).not.toContain('Agent Feedback')
    expect(apiClient).not.toContain('/input-prompts')
    expect(apiClient).not.toContain('/agent-feedback')
  })
})
