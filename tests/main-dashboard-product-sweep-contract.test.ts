import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { FoundationCompressionPanel } from '../src/components/ControlCenterInsightPanels'
import type { ControlCenterContext } from '../src/types/switchboard'

const controlCenterPage = readFileSync(resolve(process.cwd(), 'src/pages/ControlCenterPage.tsx'), 'utf-8')
const insights = readFileSync(resolve(process.cwd(), 'src/components/ControlCenterInsightPanels.tsx'), 'utf-8')
const panelRegistry = readFileSync(resolve(process.cwd(), 'src/components/controlCenterPanelRegistry.tsx'), 'utf-8')
const apiClient = readFileSync(resolve(process.cwd(), 'src/api/client.ts'), 'utf-8')
const types = readFileSync(resolve(process.cwd(), 'src/types/switchboard.ts'), 'utf-8')
const githubBackupPanel = readFileSync(resolve(process.cwd(), 'src/components/GitHubBackupPanel.tsx'), 'utf-8')

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
    expect(insights).toContain('Foundation / Compression')
    expect(panelRegistry).toContain("id: 'foundation-compression'")
    expect(insights).toContain('User Story Evidence')
    expect(insights).toContain('Agent Usage Notes')
    expect(insights).toContain('Agent-authored notes about using Switchboard')
    expect(types).toContain('HarnessSourceMap')
    expect(types).toContain('UserStoryContext')
    expect(types).toContain('AgentUsageNotesContext')
    expect(types).toContain('FeatureMapContext')
    expect(types).toContain('FoundationProjection')
    expect(types).toContain('ProductionUsageLedger')
    expect(types).toContain('AgentHandoffQualityProjection')
    expect(types).toContain('DocsRelevanceProjection')
    expect(types).toContain('SuiteBoundaryRegistry')
    expect(insights).not.toContain('Git Activity Map')
    expect(insights).not.toContain('Agent Feedback')
    expect(apiClient).not.toContain('/input-prompts')
    expect(apiClient).not.toContain('/agent-feedback')
  })

  it('keeps GitHub backup action copy demo-safe at display level', () => {
    expect(githubBackupPanel).toContain('Backup Review Ready')
    expect(githubBackupPanel).not.toContain('Push Eligible')
  })

  it('renders foundation projection from fixture data without raw private details', () => {
    const context = {
      foundation_projection: {
        schema_version: 'switchboard-pass1-foundation-v0',
        privacy: {
          classification: 'git_safe_metadata',
          raw_payloads: 'excluded',
        },
        line_noise: {
          generated: '2026-05-24T01:31:00+05:30',
          schema_version: 'line-noise-v0',
          taxonomy: ['active_source', 'generated_evidence'],
          total_lines: 1000,
          active_source_lines: 436,
          noise_line_count: 564,
          active_source_ratio: 0.4358,
          noise_ratio: 0.5642,
          tracked_file_count: 5,
          top_files: [
            { path: 'switchboard/evidence/completed-tasks.json', lines: 6796, classification: 'generated_evidence' },
            { path: 'switchboard/manifests/services.json', lines: 6030, classification: 'manifest_data' },
            { path: 'src/pages/ServiceDetailPage.tsx', lines: 2854, classification: 'active_source' },
          ],
          categories: {},
          important_paths: [],
          noise_paths: [],
        },
        production_usage: {
          generated: '2026-05-24T01:31:00+05:30',
          schema_version: 'production-usage-v0',
          privacy: { classification: 'git_safe_metadata', raw_payloads: 'excluded' },
          evidence_kinds: ['model', 'tool', 'api', 'runtime', 'storage', 'manual', 'human_ui', 'tokens'],
          summary: { model: 36, tool: 211, api: 15, runtime: 19, storage: 241, manual: 224, human_ui: 2, tokens: 0 },
          entries: [
            {
              entry_id: 'tool-private-fixture',
              evidence_kind: 'tool',
              source: 'task_ledgers.tool',
              status: 'observed',
              count: 1,
              labels: ['SECRET_FINANCE_ROW', 'transcript.txt', 'personal-cost-payload'],
              private_payload: 'excluded',
              notes: 'raw prompt and bank.csv must not render',
            },
          ],
          notes: ['Private usage/cost payloads are not imported.'],
        },
        agent_handoff_quality: {
          generated: '2026-05-24T01:31:00+05:30',
          schema_version: 'agent-handoff-quality-v0',
          source: 'task_ledgers',
          task_count: 224,
          handoff_tag_count: 115,
          with_read_back: 211,
          with_scope_check: 211,
          with_changed_paths: 224,
          with_agent: 211,
          with_tool: 211,
          with_verification_hint: 63,
          quality_score: 95,
          missing: { read_back: 13, scope_check: 13, changed_paths: 0, agent: 13, tool: 13 },
          latest_records: [],
          privacy: { classification: 'git_safe_metadata', raw_payloads: 'excluded' },
        },
        docs_relevance: {
          generated: '2026-05-24T01:31:00+05:30',
          schema_version: 'docs-relevance-v0',
          source: 'switchboard/evidence/doc-index.json',
          latest_task_at: '2026-05-24T01:31:00+05:30',
          doc_count: 3,
          enabled_count: 2,
          current_count: 1,
          stale_count: 1,
          docs: [
            { doc_id: 'readme', path: 'README.md', enabled: false, generated_at: '', generated_from: '', contributor_count: 0, latest_contributor_at: '', lifecycle_state: 'disabled', memory_role: 'disabled_root_doc' },
            { doc_id: 'runbook', path: 'switchboard/local/runbook.md', enabled: true, generated_at: '2026-05-24T01:31:00+05:30', generated_from: 'switchboard/local/tasks-completed.md', contributor_count: 0, latest_contributor_at: '', lifecycle_state: 'generated_no_contributors', memory_role: 'project_local_memory' },
          ],
          privacy: { classification: 'git_safe_metadata', raw_payloads: 'excluded' },
        },
        harness_source_map: {} as never,
        suite_boundaries: {
          generated: '2026-05-24T01:31:00+05:30',
          schema_version: 'suite-boundaries-v0',
          source: 'manifests_and_manager_rules',
          suites: [],
          boundaries: [
            { boundary_id: 'switchboard_control_plane', status: 'active', owner_system: 'Switchboard', allowed: [], forbidden: [], evidence: {} },
            { boundary_id: 'agent_ops_manager_memory', status: 'projection_only', owner_system: 'Agent Ops', allowed: [], forbidden: [], evidence: {} },
            { boundary_id: 'palimpsest_deferred_boundary', status: 'deferred', owner_system: 'Palimpsest', allowed: [], forbidden: [], evidence: {} },
            { boundary_id: 'client_server_47_deferred_boundary', status: 'deferred', owner_system: 'human-gated client server', allowed: [], forbidden: [], evidence: {} },
          ],
          privacy: { classification: 'git_safe_metadata', raw_payloads: 'excluded' },
        },
        notes: [],
      },
    } as unknown as ControlCenterContext

    const markup = renderToStaticMarkup(createElement(FoundationCompressionPanel, { context }))
    const lowerMarkup = markup.toLowerCase()

    expect(markup).toContain('Foundation / Compression')
    expect(markup).toContain('56.4%')
    expect(markup).toContain('95/100')
    expect(markup).toContain('Switchboard Active Control')
    expect(markup).toContain('Agent Ops Projection Only')
    expect(markup).toContain('Palimpsest Deferred')
    expect(markup).toContain('.47 Deferred')
    expect(lowerMarkup).not.toContain('secret_finance_row')
    expect(lowerMarkup).not.toContain('transcript')
    expect(lowerMarkup).not.toContain('personal-cost-payload')
    expect(lowerMarkup).not.toContain('raw prompt')
    expect(lowerMarkup).not.toContain('bank.csv')
  })
})
