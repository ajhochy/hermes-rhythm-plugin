// HD-1 (§5.4): a host-issued policySelection (e.g. the Rhythm shared-agent
// launcher) must reach session.create as `policy_selection` with model,
// provider and effort omitted, and the one-shot selection must be cleared
// once desktopSessionCreateParams has read it — never left for an unrelated
// later session-create to pick up.
import { afterEach, describe, expect, it, vi } from 'vitest'

import { $newChatPolicySelection } from '@/store/policy-selection'
import { $newChatProfile } from '@/store/profile'
import { $currentFastMode, $currentModel, $currentProvider, $currentReasoningEffort } from '@/store/session'

vi.mock('@/store/profile', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ensureGatewayProfile: vi.fn().mockResolvedValue(undefined)
}))

import { desktopSessionCreateParams } from './index'

afterEach(() => {
  $newChatPolicySelection.set(null)
  $newChatProfile.set(null)
  $currentModel.set('')
  $currentProvider.set('')
  $currentReasoningEffort.set('')
  $currentFastMode.set(false)
})

describe('desktopSessionCreateParams — policy selection seam (HD-1)', () => {
  it('sends policy_selection and omits model/provider/effort, then clears the selection', async () => {
    $currentModel.set('claude-sonnet')
    $currentProvider.set('anthropic')
    $currentReasoningEffort.set('high')
    $newChatPolicySelection.set('rhythm-shared-agent:v1:team-lead@3')

    const params = await desktopSessionCreateParams('')

    expect(params.policy_selection).toBe('rhythm-shared-agent:v1:team-lead@3')
    expect(params).not.toHaveProperty('model')
    expect(params).not.toHaveProperty('provider')
    expect(params).not.toHaveProperty('reasoning_effort')
    expect($newChatPolicySelection.get()).toBeNull()
  })

  it('keeps model/provider/effort and omits policy_selection when no selection is pending', async () => {
    $currentModel.set('claude-sonnet')
    $currentProvider.set('anthropic')
    $currentReasoningEffort.set('high')

    const params = await desktopSessionCreateParams('')

    expect(params).not.toHaveProperty('policy_selection')
    expect(params.model).toBe('claude-sonnet')
    expect(params.provider).toBe('anthropic')
    expect(params.reasoning_effort).toBe('high')
  })
})
