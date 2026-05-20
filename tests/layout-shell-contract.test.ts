import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const appSource = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf-8')

describe('app shell width contract', () => {
  it('does not hard-cap the control center to the old narrow shell', () => {
    expect(appSource).toContain('max-w-[1800px]')
    expect(appSource).not.toContain('max-w-6xl')
  })
})
