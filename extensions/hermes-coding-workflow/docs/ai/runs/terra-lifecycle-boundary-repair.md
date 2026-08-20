# Terra lifecycle runtime-boundary repair

Date: 2026-08-19

## Boundary

Hermes v0.20 native `pre_tool_call` hooks run only when the Hermes agent loop dispatches a tool. They cannot intercept file or shell operations performed inside Codex app-server or ACP runtimes. Hermes source routes `api_mode == "codex_app_server"` directly to Codex, and ACP transports (such as `copilot-acp`) also own direct code tools. This installer does not claim to bridge that core/runtime boundary.

Before any profile, payload, plugin-enable, or config mutation, the installer requires the role-worker source to name a documented Hermes-dispatch route. Native providers remain allowed. OpenAI account OAuth through `openai-codex` is also allowed when `model.openai_runtime` is unset or `auto`, because current Hermes resolves that route to `codex_responses` and dispatches tools through its own loop. `codex_app_server`, ACP, and other direct-code routes remain rejected fail-closed with `HCW_PROVIDER_BOUNDARY_UNSAFE`. Use `--worker-source-profile` when a preference/source profile uses a direct-code runtime but the cloned role workers use a safe Hermes route.

Existing role profiles are not normalized: their description must already be the exact workflow description and their provider must be safe. That avoids rewriting user identity or config in place.

## Transaction and checks

The preflight validates source profiles, every pre-existing role profile, payload sources, and provider routes before staging. It snapshots root and pre-existing role `config.yaml` files plus lifecycle ownership metadata before plugin enablement. On any post-stage exception it restores payloads and those files byte-for-byte, and deletes profiles created by the transaction. The doctor validates the provider boundary in the base and every role home in addition to plugin scanning and launcher checks.

Integration coverage creates an isolated safe profile solely with supported `hermes config set model.provider openai` and an inert default model; it makes no model or network call. It also asserts unsafe `openai-codex` preflight produces the exact error code without filesystem/config mutation, and injects a failure after doctor to prove payload/config/ownership restoration and no leaked profiles.

## Current-core integration target

The always-on installed E2E specifies the future core public contract: `create-run --goal` returns actual stage task IDs, then design/plan, RED, commit, green, two reviews, full/security verification, live activation and live finalization complete via installed launchers. This local rejected base does not yet provide that complete core contract; its integration failure is recorded by the test result, without a skip, xfail, fake Kanban, or model call.
# Superseded by [terra-final-reconcile.md](terra-final-reconcile.md).
