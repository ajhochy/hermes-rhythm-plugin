import { atom } from 'nanostores'

// One-shot session-create seam for a host-issued policy selection (§5.4 —
// e.g. the Rhythm shared-agent launcher). `desktopSessionCreateParams`
// (use-session-actions/index.ts) reads and clears this in the same call that
// builds `session.create`'s params — it is never a sticky default like
// $newChatProfile, and never round-trips through the composer draft.
export const $newChatPolicySelection = atom<string | null>(null)

export function setNewChatPolicySelection(selection: string | null): void {
  $newChatPolicySelection.set(selection)
}
