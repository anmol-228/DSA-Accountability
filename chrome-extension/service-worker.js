/*
 * service-worker.js — MV3 background script. Owns the connection to the
 * desktop app's localhost API and the pairing token. Content scripts and
 * the popup talk to the desktop app only through this file.
 */

const DEFAULT_PORT = 8765;
const MAX_PORT = 8784;
const MAX_LOG_ENTRIES = 60;
const EXTENSION_VERSION = chrome.runtime.getManifest ? chrome.runtime.getManifest().version : "unknown";

async function getSettings() {
  const stored = await chrome.storage.local.get([
    "pairingToken", "apiHost", "apiPort", "paired",
  ]);
  return {
    pairingToken: stored.pairingToken || null,
    // The desktop API is intentionally localhost-only. Ignore any stale or
    // tampered stored host rather than ever forwarding code elsewhere.
    apiHost: "127.0.0.1",
    apiPort: stored.apiPort || DEFAULT_PORT,
    paired: !!stored.paired,
  };
}

async function apiBase(portOverride = null) {
  const { apiHost, apiPort } = await getSettings();
  return `http://${apiHost}:${portOverride || apiPort}`;
}

async function logDebug(message, data) {
  const { debugLog = [] } = await chrome.storage.local.get(["debugLog"]);
  const entry = { ts: new Date().toISOString(), message, data: data ?? null };
  const next = [entry, ...debugLog].slice(0, MAX_LOG_ENTRIES);
  await chrome.storage.local.set({ debugLog: next });
}

async function apiFetch(path, options = {}, portOverride = null) {
  const { pairingToken } = await getSettings();
  const base = await apiBase(portOverride);
  const headers = Object.assign(
    { "Content-Type": "application/json" },
    pairingToken ? { "X-DSA-Token": pairingToken } : {},
    options.headers || {}
  );
  try {
    const requestOptions = { ...options, headers };
    if (!requestOptions.signal && typeof AbortSignal !== "undefined" && AbortSignal.timeout) {
      requestOptions.signal = AbortSignal.timeout(1200);
    }
    const resp = await fetch(base + path, requestOptions);
    const body = await resp.json().catch(() => ({}));
    return { ok: resp.ok, status: resp.status, body };
  } catch (err) {
    return { ok: false, status: 0, body: { error: String(err) } };
  }
}

async function testConnection() {
  const { apiPort } = await getSettings();
  const ports = [apiPort, ...Array.from({ length: MAX_PORT - DEFAULT_PORT + 1 }, (_, i) => DEFAULT_PORT + i)]
    .filter((port, index, all) => all.indexOf(port) === index);

  async function probe(port) {
    const health = await apiFetch("/api/health", {}, port);
    if (!health.ok || health.body.status !== "ok") return { port, reachable: false, health };
    const status = await apiFetch("/api/status", {}, port);
    return { port, reachable: true, status };
  }

  const preferred = await probe(ports[0]);
  const results = [preferred];
  if (!(preferred.reachable && preferred.status.ok)) {
    results.push(...await Promise.all(ports.slice(1).map(probe)));
  }
  const success = results.find((result) => result.reachable && result.status.ok);
  if (success) {
    await chrome.storage.local.set({ apiPort: success.port, paired: true });
    await logDebug(`Connection test succeeded on port ${success.port}`, success.status.body);
    return { connected: true, paired: true, status: success.status.body, apiPort: success.port };
  }

  const reachable = results.filter((result) => result.reachable);
  if (reachable.some((result) => result.status.status === 401)) {
    await logDebug("Connection test: reachable but token invalid");
    await chrome.storage.local.set({ paired: false });
    return { connected: true, paired: false, reason: "invalid_token" };
  }
  if (reachable.length > 0) {
    await logDebug("Connection test: status endpoint failed", reachable[0].status);
    return { connected: true, paired: false, reason: "status_error" };
  }
  await logDebug("Connection test failed: desktop app unreachable", preferred.health);
  return { connected: false, paired: false, reason: "desktop_unreachable" };
}

async function forwardSessionStart(slug) {
  const result = await apiFetch("/api/session/start", {
    method: "POST",
    body: JSON.stringify({ slug }),
  });
  await logDebug(`Session start for slug=${slug}`, result.body);
  return result;
}

async function forwardAccepted(payload) {
  await logDebug(`trace=${payload.trace_id} Accepted detected: ${payload.slug} (${payload.language || "unknown language"})`, {
    code_captured: !!payload.code,
    method: payload.code_capture_method,
    content_script_version: payload.content_script_version,
  });
  const result = await apiFetch("/api/leetcode/accepted", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await logDebug(`trace=${payload.trace_id} Desktop response for ${payload.slug}`, result.body);
  await chrome.storage.local.set({ lastAcceptedResult: { payload, result: result.body, ts: Date.now() } });
  return result;
}

async function forwardPremiumBlocked(taskId) {
  const result = await apiFetch("/api/leetcode/premium_blocked", {
    method: "POST",
    body: JSON.stringify({ task_id: taskId }),
  });
  await logDebug("Premium-blocked replacement requested", result.body);
  return result;
}

// Reloading the extension in chrome://extensions does NOT re-inject
// content-script.js into a tab that was already open -- only a full page
// refresh does. This queries the active tab directly so the popup can
// tell the user "refresh this tab" instead of silently reporting
// everything as fine while a stale content script keeps running
// (production repair pass, section 30 -- a real, confusing failure this
// session was exactly this: the extension was reloaded, but the LeetCode
// tab kept firing the pre-fix language-detection bug for several minutes
// until the page itself was also refreshed).
async function checkActiveLeetCodeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url || !/^https:\/\/leetcode\.com\/problems\//.test(tab.url)) {
    return { onLeetCodeProblem: false };
  }
  const pong = await Promise.race([
    chrome.tabs.sendMessage(tab.id, { type: "PING_CONTENT_SCRIPT" }).catch(() => null),
    new Promise((resolve) => setTimeout(() => resolve(null), 800)),
  ]);
  if (!pong) {
    return { onLeetCodeProblem: true, contentScriptPresent: false };
  }
  return {
    onLeetCodeProblem: true,
    contentScriptPresent: true,
    contentScriptVersion: pong.version,
    extensionVersion: EXTENSION_VERSION,
    slug: pong.slug,
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    switch (message.type) {
      case "PROBLEM_PAGE_OPENED":
        sendResponse(await forwardSessionStart(message.payload.slug));
        break;
      case "ACCEPTED_DETECTED":
        sendResponse(await forwardAccepted(message.payload));
        break;
      case "TEST_CONNECTION":
        sendResponse(await testConnection());
        break;
      case "SAVE_PAIRING":
        await chrome.storage.local.set({
          pairingToken: message.token,
          apiHost: message.host || "127.0.0.1",
          apiPort: message.port || DEFAULT_PORT,
        });
        sendResponse(await testConnection());
        break;
      case "GET_CURRENT_CURRICULUM":
        sendResponse(await apiFetch("/api/curriculum/current"));
        break;
      case "REPORT_PREMIUM_BLOCKED":
        sendResponse(await forwardPremiumBlocked(message.taskId));
        break;
      case "GET_DEBUG_LOG": {
        const { debugLog = [] } = await chrome.storage.local.get(["debugLog"]);
        sendResponse(debugLog);
        break;
      }
      case "CHECK_ACTIVE_TAB":
        sendResponse(await checkActiveLeetCodeTab());
        break;
      default:
        sendResponse({ error: "unknown_message_type" });
    }
  })();
  return true; // keep the message channel open for the async response
});

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    DEFAULT_PORT, MAX_PORT, EXTENSION_VERSION, getSettings, apiBase, apiFetch,
    testConnection, forwardSessionStart, forwardAccepted, checkActiveLeetCodeTab,
  };
}
