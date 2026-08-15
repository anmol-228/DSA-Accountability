# Chrome Extension

Manifest V3, scoped to `https://leetcode.com/problems/*` and
`http://127.0.0.1/*`. No other host permissions. It never reads cookies,
auth tokens, or LeetCode account/submission history — only the DOM of the
problem page you already have open, plus a fetch to your own desktop app.

## Install (unpacked, dev mode)

1. Open `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `chrome-extension\` folder inside this repo
5. Open the extension's popup (puzzle-piece icon in the toolbar -> pin it)
6. On the first pairing only, show/copy the existing pairing token from desktop
   Settings and paste it into the extension. Do not regenerate it during normal
   setup or troubleshooting.
7. Click **Save & Test Connection** — you should see "Desktop App: Connected"
   and "Pairing: Active"
8. Open any LeetCode problem page to verify the watcher — the popup should
   show the current curriculum day and any pending LeetCode tasks
9. Perform a real submission only when you're ready to test end-to-end sync

## How Accepted detection works

`content-script.js` runs a `MutationObserver` on the page and looks for a
DOM node whose exact text is `Accepted`, using LeetCode's
`data-e2e-locator="submission-result"` attribute first and a broader
result-panel heuristic as a fallback. Detection is armed only by a real click
on LeetCode's Submit button and expires after two minutes; an Accepted result
already present when a page opens is never forwarded. One Submit can forward
at most one Accepted event. **LeetCode's DOM
changes over time** — if detection silently stops working, see
[TROUBLESHOOTING.md](TROUBLESHOOTING.md#accepted-not-detected).

LeetCode uses client-side navigation, so the watcher also notices slug changes
and starts a new desktop session once per newly opened problem without needing
a full content-script reload.

## How code capture works

`page-bridge.js` is injected into the **page** context (content scripts run
in an isolated world that can't see the page's `window.monaco`) and tries,
in order:
1. `window.monaco.editor.getModels()` — the Monaco global, when exposed
2. Walking up from `.monaco-editor` to find a React fiber prop carrying the
   editor instance (`__reactProps$...`) — a common technique because
   LeetCode's editor is React-wrapped
3. Reconstructing text from `.view-lines .view-line` DOM nodes, sorted by
   their `top` CSS offset — imperfect (can lose exact whitespace) but
   functional as a last resort

If all three fail, the desktop app shows "Accepted verified ✅ / Automatic
code capture failed ⚠" with **Retry Code Sync**, **Capture Current Editor**,
and **Paste Code Manually** options — it never silently marks the problem
complete without code.

The Monaco capture result includes its language ID. When it identifies the
captured model as Java, that authoritative value is preferred over the more
brittle visible DOM language label.

## Persistence and port recovery

- The extension stores the token in `chrome.storage.local`; connection failures
  never clear or regenerate it.
- The desktop host is always forced to `127.0.0.1`, even if old/tampered storage
  contains another host.
- If the desktop app must use a fallback port, the service worker probes
  8765–8784, validates both health and token-authenticated status, and persists
  the working port automatically.
- After updating/reloading this unpacked extension, refresh any already-open
  LeetCode tab. The popup compares content-script and extension versions and
  shows a refresh warning when they differ.

## Security

- Binds only to `127.0.0.1`; the server rejects any request without a valid
  `X-DSA-Token` header (see `pairing_service.py`).
- The token is generated locally, hidden by default, and never leaves your
  machine.
- No LAN exposure, no cloud relay.
