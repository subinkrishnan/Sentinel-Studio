# Ask Pulse connection to Sentinel Assistant

Studio's Ask Pulse now has a server-side bridge to the actual documented Sentinel Assistant conversation API. This is not a local generative model or canned-answer replacement. Enable `pulse.enabled` in the host admin config after the Mart mapping and API access are ready. The example keeps it disabled; the current Mac config has not been changed.

## Verified interface

Inspected official Dev Help/Assistant and its served OpenAPI contract on 6 October 2026:

- `GET /api/v1/assistant/config` checks API readiness.
- `POST /api/v1/assistant/conversations` creates an owned conversation.
- `POST /api/v1/assistant/conversations/{cid}/messages` takes `content`, optional `strong`, `model`, and `context`. It streams SSE: `delta {text}`, `tool_start`, `tool_end {name,summary,artifact?}`, `done`, and `error`.
- Action execution uses separate endpoints. Studio does not expose or call them.

The official Python SDK 0.8.0 has no Assistant method. The bridge uses its inspected `_get`, `_post`, `_headers` transport helpers for authentication and conversation setup, and Requests for SSE. These are private SDK helpers: compatibility checks fail closed if absent, and future SDK updates need the transport tests rerun. Conversation creation currently expects the response's positive integer `id`; the deployed response and API-token eligibility still need live validation from the Mac. No browser-session credentials or cookies are copied into Studio.

## Behaviour

The frontend verifies Pulse API readiness and enables questions only when the configured Mart summary is CONNECTED with an eligible published run. Each question rechecks Mart and rejects a stale run selection. The server supplies the relation, scoring run, cutoff, model version, business line and workspace mode as documented conversation context. It asks the engine to cite its sources and explain proposed changes for review.

Context is a grounding hint, not an IAM restriction. The engine's authenticated principal, delegated-token ceiling and governed gateway enforce access. With an admin-owned personal key, the Assistant may have broader data access than the displayed Mart; do not represent this integration as a table-scoped security boundary. A truly restricted account must be configured on the platform if that becomes a requirement. No permission changes are made here.

Studio sessions have separate conversation IDs. A changed Mart context starts a new conversation. New chat discards the local conversation reference while preserving engine history for audit. Logout discards local session state. One turn per session can be in flight. Failures and partial streams are not automatically retried, and an incomplete turn is never displayed as a successful answer.

The answer and tool summaries are rendered as escaped text. Studio shows the supplied Mart/run context separately from the engine's answer, so it is not confused with proof that every tool read that relation. Tool artifacts, action confirmation cards, scheduler instructions and write execution are not implemented here; use the native Dev Assistant to review any action.

## Credentials and activation

Pulse uses the same configured endpoint/credentials as the Mart reader, kept server-side. On Dev, existing `SENTINEL_CLIENT_ID`/`SENTINEL_CLIENT_SECRET` can be used. Dedicated `SENTINEL_MART_CLIENT_ID`/`SENTINEL_MART_CLIENT_SECRET` are also supported; canonical production mode requires an approved production endpoint and dedicated credentials.

After Bronze/Silver/scoring/Mart validation, pull the branch on the Mac, confirm the physical Mart column mapping, enable `mart.enabled` and `pulse.enabled`, restart Studio in its existing Python/SDK environment, and click Verify Pulse connection. Ask about the published run and check the engine's cited sources, quantities and cutoff against the displayed summary. Test conversation setup, SSE completion, access denial and token budget with that actual API credential. API readiness alone is not a live-answer test.

Status states remain honest: NOT_CONFIGURED / BLOCKED / UNAVAILABLE / READY, then ANSWERED only after a completed nonempty engine response. When Mart is absent, Studio does not substitute fixture answers. Bronze upload and the original canonical table names are unchanged.
