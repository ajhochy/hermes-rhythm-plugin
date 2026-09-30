import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/store/profile', async importActual => {
  const actual = await importActual()

  return { ...(actual as Record<string, unknown>), newSessionInProfile: vi.fn() }
})

import { takeSessionDraft } from '@/store/composer'
import { newSessionInProfile } from '@/store/profile'

import { host } from './index'

describe('host.newChat draft prefill', () => {
  afterEach(() => {
    vi.clearAllMocks()
    window.location.hash = ''
  })

  it('opens one editable unsent draft and never submits a turn', () => {
    host.newChat({ prefill: 'Help me plan this task.', profile: 'rhythm' })

    expect(newSessionInProfile).toHaveBeenCalledOnce()
    expect(newSessionInProfile).toHaveBeenCalledWith('rhythm')
    expect(takeSessionDraft(null)).toMatchObject({ attachments: [], text: 'Help me plan this task.' })
    expect(window.location.hash).toBe('#/')
  })

  it('resolves duplicate/racing new-chat calls deterministically to one latest draft', () => {
    host.newChat({ prefill: 'first' })
    host.newChat({ prefill: 'second' })

    expect(newSessionInProfile).toHaveBeenCalledTimes(2)
    expect(takeSessionDraft(null).text).toBe('second')
  })

  it('bounds source metadata before it reaches the editable draft', () => {
    host.newChat({
      prefill: 'Ask Hermes',
      source: {
        label: 'Rhythm task',
        metadata: Object.fromEntries(Array.from({ length: 30 }, (_, i) => [`field-${i}`, 'x'.repeat(500)]))
      }
    })

    const text = takeSessionDraft(null).text
    expect(text).toContain('Ask Hermes')
    expect(text).toContain('Rhythm task')
    expect(text.length).toBeLessThanOrEqual(2_048)
    expect((text.match(/field-/g) ?? []).length).toBeLessThanOrEqual(8)
  })
})
