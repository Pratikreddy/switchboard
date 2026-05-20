import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const app = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf-8')
const workspacePage = readFileSync(resolve(process.cwd(), 'src/pages/WorkspacePage.tsx'), 'utf-8')
const runStatus = readFileSync(resolve(process.cwd(), 'src/components/RunStatus.tsx'), 'utf-8')
const client = readFileSync(resolve(process.cwd(), 'src/api/client.ts'), 'utf-8')

describe('Collect refresh contract', () => {
  it('keeps Collect as the only primary company refresh action', () => {
    expect(runStatus).toContain('Collect refreshes node truth, saved scope, ports, docs, repo state, and pull authority.')
    expect(runStatus).not.toContain('Run All Health Checks')
    expect(workspacePage).not.toContain('workspaceHealthCheck')
    expect(workspacePage).not.toContain('Health Check Results')
  })

  it('pushes fresh collect/latest results back to App.latestResults', () => {
    expect(app).toContain('handleLatestUpdated')
    expect(app).toContain('setLatestResults((prev) => ({ ...prev, [workspaceId]: latest }))')
    expect(workspacePage).toContain('onLatestUpdated?.(workspaceId, result)')
    expect(workspacePage).toContain('onLatestUpdated?.(workspaceId, latestResult)')
  })

  it('requests node sync during Collect and normalizes node sync metadata', () => {
    expect(workspacePage).toContain('triggerCollect(workspaceId, { include_node_sync: true })')
    expect(client).toContain('node_sync_results')
    expect(client).toContain('node_sync_count')
    expect(client).toContain('node_sync_blocked_count')
  })
})
