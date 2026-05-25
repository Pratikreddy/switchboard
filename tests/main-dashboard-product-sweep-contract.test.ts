import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { ActivityMapPanel } from '../src/components/ControlCenterInsightPanels'
import type { ControlCenterContext } from '../src/types/switchboard'

const app = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf-8')
const controlCenterPage = readFileSync(resolve(process.cwd(), 'src/pages/ControlCenterPage.tsx'), 'utf-8')
const insights = readFileSync(resolve(process.cwd(), 'src/components/ControlCenterInsightPanels.tsx'), 'utf-8')
const panelRegistry = readFileSync(resolve(process.cwd(), 'src/components/controlCenterPanelRegistry.tsx'), 'utf-8')
const projectsPanel = readFileSync(resolve(process.cwd(), 'src/components/ProjectsPanel.tsx'), 'utf-8')
const serviceDetail = readFileSync(resolve(process.cwd(), 'src/pages/ServiceDetailPage.tsx'), 'utf-8')

describe('main dashboard product sweep contract', () => {
  it('keeps the 1.12.7 home dashboard to activity and overview only', () => {
    expect(panelRegistry).toContain("export type ControlCenterPanelGroupId = 'activity' | 'overview'")
    expect(panelRegistry).toContain("id: 'activity'")
    expect(panelRegistry).toContain("id: 'overview'")
    expect(panelRegistry).toContain('grid gap-4 lg:grid-cols-3')
    expect(panelRegistry).not.toContain("id: 'evidence'")
    expect(panelRegistry).not.toContain("id: 'notes'")
    expect(panelRegistry).not.toContain("id: 'operations'")
  })

  it('keeps Tech Stack, How To Use, and Companies horizontally grouped on desktop', () => {
    expect(panelRegistry).toContain("id: 'tech-stack'")
    expect(panelRegistry).toContain("id: 'how-to-use'")
    expect(panelRegistry).toContain("id: 'companies'")
    expect(panelRegistry).toContain('onOpenCompany')
  })

  it('uses a task-ledger work map with branch metadata only', () => {
    expect(panelRegistry).toContain('ActivityMapPanel')
    expect(panelRegistry).toContain('Work Activity Map')
    expect(insights).toContain('Work Activity Map')
    expect(insights).toContain('GitHub-style grid from task-ledger work. Branch/head is metadata only.')
    expect(insights).toContain('aria-label="Branch metadata"')
    expect(insights).toContain('data-testid="work-activity-cell"')
  })

  it('removes noisy home-page product surfaces', () => {
    const homeSurface = `${controlCenterPage}\n${panelRegistry}\n${insights}`
    expect(homeSurface).not.toContain('Foundation / Compression')
    expect(homeSurface).not.toContain('Main And Sidecar Features')
    expect(homeSurface).not.toContain('Harness Adapter Source Map')
    expect(homeSurface).not.toContain('User Story Evidence')
    expect(homeSurface).not.toContain('Agent Usage Notes')
    expect(homeSurface).not.toContain('Server Registry')
    expect(homeSurface).not.toContain('GitHub Backup')
    expect(homeSurface).not.toContain('Brick Entries')
    expect(homeSurface).not.toContain('brick-registry')
    expect(homeSurface).not.toContain('Project Bricks')
    expect(homeSurface).not.toContain('Backend:')
    expect(homeSurface).not.toContain('metadata-only projection')
  })

  it('removes API Lab from the visible product path', () => {
    const visibleProduct = `${app}\n${projectsPanel}\n${serviceDetail}`
    expect(visibleProduct).not.toContain('EnvironmentApiLabPage')
    expect(visibleProduct).not.toContain('selectedEnvironmentLab')
    expect(visibleProduct).not.toContain('onOpenEnvironmentLab')
    expect(visibleProduct).not.toContain('Dedicated API Lab')
    expect(visibleProduct).not.toContain('API Lab')
    expect(visibleProduct).not.toContain('environment API Labs')
  })

  it('renders the work map without commit-count wording', () => {
    const context = {
      activity_map: {
        generated: '2026-05-24T08:39:17+05:30',
        source: 'task_ledgers',
        days: [
          {
            date: new Date().toISOString().slice(0, 10),
            task_count: 3,
            changed_path_count: 7,
            scope_entry_count: 6,
          },
        ],
        total_tasks: 3,
        total_changed_paths: 7,
        total_scope_entries: 6,
      },
      branch_metadata: {
        active_branch: 'main',
        current_head: 'abc123',
        branches: ['main', 'release/1.12.7'],
        generated: '2026-05-24T08:39:17+05:30',
      },
      line_noise: {
        active_source_lines: 27295,
      },
      cleanup_note: 'Activity is collected from task ledgers.',
    } as unknown as ControlCenterContext

    const markup = renderToStaticMarkup(
      createElement(ActivityMapPanel, {
        context,
        selectedBranch: 'main',
        onBranchChange: () => undefined,
      }),
    )

    expect(markup).toContain('Work Activity Map')
    expect(markup).toContain('GitHub-style grid from task-ledger work')
    expect(markup).toContain('Tasks')
    expect(markup).toContain('Active lines')
    expect(markup).not.toContain('commit count')
    expect(markup).not.toContain('Foundation')
    expect(markup).not.toContain('Sidecar')
  })
})
