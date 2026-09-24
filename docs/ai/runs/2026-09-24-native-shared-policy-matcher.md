---
date: 2026-09-24
repo: hermes-rhythm-plugin
branch: codex/native-hermes-session-policy
pr: null
issues: [shared-agent-n0]
status: local-candidate
tags: [run, hermes]
---

# Native shared-agent N0 policy contract and matcher

## Files

- `tests/tui_gateway/test_shared_agent_policy_live.py` drives native `session.create` and `prompt.submit` through the real in-process gateway and AIAgent with a deterministic OpenAI-compatible endpoint bound to ephemeral `127.0.0.1`. It uses a registered fixture policy provider, synthetic `HOME`/`HERMES_HOME`, synthetic credentials, and a fresh SessionDB. `RHYTHM_SHARED_AGENTS_LIVE=1` gates the suite; `scripts/run_tests.sh` forwards that one opt-in through its clean environment.
- `tests/plugins/test_session_policy.py` records Rhythm scalar wildcard cases and path-grant safety regressions. `agent/session_policy.py` now keeps a global `*` global, handles supported scalar terminal wildcard semantics, rejects ambiguous path globs, and rejects symlink components in exact or anchored path rules both at construction/resume and at authorization. Raw policy fields remain in the persisted snapshot.
- `docs/ai/contracts/shared-agent-n0.json` records partial live evidence and remaining acceptance gaps. All eight broad criteria remain pending.

## Checks

- Before the symlink repair, two focused regressions failed: an existing symlink rule anchor was accepted and a rule anchor replaced by a symlink after snapshot moved authority. After repair those cases and the deliberate final-newline strictness test passed 3/3.
- `scripts/run_tests.sh tests/plugins/test_session_policy.py tests/plugins/test_session_policy_parent_review.py tests/tui_gateway/test_native_session_policy.py -q`: 27 passed.
- `scripts/run_tests.sh tests/plugins/test_session_policy.py tests/plugins/test_session_policy_parent_review.py tests/tui_gateway/test_native_session_policy.py tests/tui_gateway/test_protocol.py tests/test_model_tools.py tests/tools/test_refresh_agent_mcp_tools.py tests/tui_gateway/test_session_resume_db_ownership.py tests/tools/test_request_tool_approval.py -q`: 140 passed after the path repair.
- `RHYTHM_SHARED_AGENTS_LIVE=1 scripts/run_tests.sh tests/tui_gateway/test_shared_agent_policy_live.py -q`: nine passed after the path repair. The same suite without the flag skipped nine tests. `bash -n scripts/run_tests.sh` and Python bytecode compilation passed.

## Notes

- The live suite uses the actual native agent tool loop and model HTTP requests but runs the gateway in process, not as a separate `hermes serve` child. The provider and local model are deterministic fixtures, not Rhythm API, OpenCode, an external provider, or installed account stores. No real key or production home is read or written.
- Model request assertions cover selected model, frozen instruction marker, and filtered tool names. They do not yet prove exact reasoning request bytes or absence of OpenCode/API network requests by traffic capture. Compute-host construction, separate-process restart, direct `model_tools` dispatch under live policy, terminal command execution and decomposition, unavailable/headless approval, and simultaneous opposite-allowlist sessions remain outstanding.
- Terminal matching is deliberately stricter than Rhythm's JS `^...$` for a final trailing newline: Python `re.fullmatch` denies that case. Brackets are literal, backslashes normalize to slashes, wildcard spans newlines, and a final `" *"` is optional where supported. This is not a claim of complete JS matcher equivalence.
- Revalidating symlink components before policy evaluation prevents deterministic retargeting of a frozen lexical path grant. Filesystem changes between `lstat`/`realpath` and the eventual tool operation remain a TOCTOU limit; this is not descriptor-root confinement. An ordinary replacement at the same lexical path retains the path grant.
- GitNexus impact lookup for `authorize_tool_call` found a stale fork index with no mapped new-symbol callers and unknown risk; it did not establish a low blast radius. No commit or push was made. Acceptance and manual smoke remain pending.

## Parent fork integration

Copied reviewed native constructor/executor/approval/MCP-refresh/persistence changes into `codex/hermes-shared-integration` on S3 commit d14e280dbf. Parent canonical adjacent replay passed 140/140. First integrated live replay had 8 passes and one assertion failure: the forged terminal call was correctly refused as unavailable, but the test searched all request messages for “policy”. The candidate worktree path itself contained that word, masking the overbroad assertion. Parent now checks the actual matching tool-result denial, retaining zero offered tools and absent marker assertions. The request also asserts `reasoning_effort: low` directly. The corrected integrated live replay passed 9/9 in 12.9 seconds.

This proves the selected fixture's reasoning bytes, not all provider mappings. Other original criterion gaps remain. Logs `n0-fork-integrated-adjacent.log`, `n0-fork-integrated-live.log`, and `n0-fork-integrated-live-repaired.log` are preserved in the Rhythm repair4 evidence directory.
