import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const projectsPanel = readFileSync(resolve(process.cwd(), 'src/components/ProjectsPanel.tsx'), 'utf-8')
const projectOnboardingPanel = readFileSync(resolve(process.cwd(), 'src/components/ProjectOnboardingPanel.tsx'), 'utf-8')
const workspacePage = readFileSync(resolve(process.cwd(), 'src/pages/WorkspacePage.tsx'), 'utf-8')

describe('Projects panel company grouping contract', () => {
  it('uses Projects and Add Project as the primary company grouping labels', () => {
    expect(projectsPanel).toContain('Projects')
    expect(projectsPanel).toContain('Add Project')
    expect(projectsPanel).toContain('Parent Project')
    expect(projectsPanel).toContain('Renaming updates child projects and environments.')
    expect(projectsPanel).not.toContain('Projects & Environments')
    expect(projectsPanel).not.toContain('Add Project Group')
    expect(projectsPanel).not.toContain('Advanced identity')
  })

  it('keeps service onboarding behind an advanced inventory surface', () => {
    expect(workspacePage).toContain('Advanced Service Inventory')
    expect(workspacePage).not.toContain('Use Add Service to seed this workspace manually.')
  })

  it('shows assigned and unassigned services with owner labels', () => {
    expect(projectsPanel).toContain('Selected for this project')
    expect(projectsPanel).toContain('Unassigned')
    expect(projectsPanel).toContain('Owned by')
    expect(projectsPanel).toContain('Will move from')
    expect(projectsPanel).not.toContain('return !owner || owner === editingProjectId')
  })

  it('counts current project services separately from missing service references', () => {
    expect(projectsPanel).toContain('missing reference')
    expect(projectsPanel).toContain('Missing reference:')
    expect(projectsPanel).toContain('No current services owned by this project.')
    expect(projectsPanel).not.toContain('{project.service_ids.length} services')
  })

  it('lets service onboarding assign the created service to a project with existing APIs', () => {
    expect(projectOnboardingPanel).toContain('Assign to Project')
    expect(projectOnboardingPanel).toContain('updateProject(selectedProject.project_id')
    expect(projectOnboardingPanel).toContain('Created and assigned')
    expect(projectOnboardingPanel).toContain('missing service references')
    expect(projectOnboardingPanel).not.toContain('Group it under a business project later')
  })

  it('keeps environment editing secondary to the project view', () => {
    expect(projectsPanel).toContain('Secondary setup')
    expect(projectsPanel).toContain('Main view stops at company, project, and owned services.')
    expect(projectsPanel).not.toContain('Advanced ·')
  })

  it('does not expose project or environment delete controls in this pass', () => {
    expect(projectsPanel).not.toContain('deleteProject')
    expect(projectsPanel).not.toContain('deleteProjectEnvironment')
    expect(projectsPanel).not.toContain('removeProject')
    expect(projectsPanel).not.toContain('removeEnvironment')
  })
})
