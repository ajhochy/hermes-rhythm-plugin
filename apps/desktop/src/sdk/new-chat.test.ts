import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/store/profile', async importActual => {
  const actual = await importActual()

  return { ...(actual as Record<string, unknown>), newSessionInProfile: vi.fn() }
})

import { takeSessionDraft } from '@/store/composer'
import { newSessionInProfile } from '@/store/profile'

import { host, newChatPolicySelection } from './index'

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

// Follow-up from the S7 review: a direct unit test for the §5.4 policy-
// selection validator, independent of the draft-composition tests above.
describe('newChatPolicySelection validator (§5.4)', () => {
  it('accepts a well-formed selection and trims surrounding whitespace', () => {
    expect(newChatPolicySelection({ policySelection: '  rhythm:shared-agent@v1.2_launch  ' })).toBe(
      'rhythm:shared-agent@v1.2_launch'
    )
  })

  it('drops a selection with characters outside the allowed grammar', () => {
    expect(newChatPolicySelection({ policySelection: 'bad value!' })).toBeNull()
    expect(newChatPolicySelection({ policySelection: 'has/slash' })).toBeNull()
    expect(newChatPolicySelection({ policySelection: 'emoji😀' })).toBeNull()
  })

  it('accepts exactly the length limit and drops one character over it', () => {
    expect(newChatPolicySelection({ policySelection: 'a'.repeat(1_024) })).toBe('a'.repeat(1_024))
    expect(newChatPolicySelection({ policySelection: 'a'.repeat(1_025) })).toBeNull()
  })

  it('drops a missing, empty, or whitespace-only selection', () => {
    expect(newChatPolicySelection({})).toBeNull()
    expect(newChatPolicySelection({ policySelection: '' })).toBeNull()
    expect(newChatPolicySelection({ policySelection: '   ' })).toBeNull()
  })
})
