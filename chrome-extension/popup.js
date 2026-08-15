function send(message) {
  return new Promise((resolve) => chrome.runtime.sendMessage(message, resolve));
}

function setBadge(el, ok, textOk, textBad) {
  el.textContent = ok ? textOk : textBad;
  el.className = "badge " + (ok ? "badge-ok" : "badge-bad");
}

async function refreshConnection() {
  const result = await send({ type: "TEST_CONNECTION" });
  const connEl = document.getElementById("conn-status");
  const pairEl = document.getElementById("pair-status");
  setBadge(connEl, result.connected, "Connected", "Unreachable");
  setBadge(pairEl, result.paired, "Active", result.reason === "invalid_token" ? "Invalid token" : "Not paired");
  return result;
}

async function refreshCurriculum() {
  const result = await send({ type: "GET_CURRENT_CURRICULUM" });
  const dayEl = document.getElementById("current-day");
  const tasksEl = document.getElementById("pending-tasks");
  if (!result.ok) {
    dayEl.textContent = "Day — / 135 (not connected)";
    tasksEl.innerHTML = "";
    return;
  }
  const body = result.body;
  if (body.post_plan_mode) {
    dayEl.textContent = "All 135 days complete";
    tasksEl.innerHTML = "";
    return;
  }
  dayEl.textContent = `Day ${body.day} / 135 — ${body.title}`;
  tasksEl.textContent = "";
  const tasks = body.pending_leetcode_tasks || [];
  if (tasks.length === 0) {
    const div = document.createElement("div");
    div.textContent = "No pending LeetCode tasks today.";
    tasksEl.appendChild(div);
  } else {
    for (const t of tasks) {
      const div = document.createElement("div");
      div.textContent = `LC ${t.leetcode_number} — ${t.title}`;
      tasksEl.appendChild(div);
    }
  }
}

async function refreshWatcherStatus() {
  const result = await send({ type: "CHECK_ACTIVE_TAB" });
  const section = document.getElementById("watcher-section");
  const warningEl = document.getElementById("watcher-warning");
  if (!result || !result.onLeetCodeProblem) {
    section.style.display = "none";
    return;
  }
  if (!result.contentScriptPresent) {
    section.style.display = "block";
    warningEl.textContent = "This LeetCode tab isn't being watched — refresh the page.";
    return;
  }
  if (result.contentScriptVersion !== result.extensionVersion) {
    section.style.display = "block";
    warningEl.textContent = `Watcher ${result.contentScriptVersion || "unknown"} is stale; refresh this LeetCode tab for ${result.extensionVersion}.`;
    return;
  }
  section.style.display = "none";
}

async function refreshDebugLog() {
  const log = await send({ type: "GET_DEBUG_LOG" });
  const el = document.getElementById("debug-log");
  el.textContent = log.map((e) => `[${e.ts}] ${e.message}`).join("\n") || "(empty)";
}

async function refreshLastAccepted() {
  const { lastAcceptedResult } = await chrome.storage.local.get(["lastAcceptedResult"]);
  const acceptedEl = document.getElementById("accepted-status");
  if (!lastAcceptedResult) {
    acceptedEl.textContent = "Waiting…";
    return;
  }
  const { payload, result } = lastAcceptedResult;
  const status = result.status;
  const map = {
    ok: `Accepted ✅ (${payload.language}) — code ${result.code_captured ? "captured ✅" : "capture failed ⚠"}`,
    stale: "Accepted, but no active session — historical result, not counted.",
    wrong_language: `Accepted, but requires Java (got ${payload.language || "unknown"}).`,
    duplicate: "Duplicate event ignored.",
    unknown_problem: "Accepted on a problem not in the curriculum.",
  };
  acceptedEl.textContent = map[status] || status || "Unknown";
}

document.getElementById("save-pairing-btn").addEventListener("click", async () => {
  const token = document.getElementById("token-input").value.trim();
  const port = parseInt(document.getElementById("port-input").value, 10) || 8765;
  await send({ type: "SAVE_PAIRING", token, port, host: "127.0.0.1" });
  await refreshConnection();
  await refreshCurriculum();
});

document.getElementById("toggle-debug-btn").addEventListener("click", async () => {
  const pre = document.getElementById("debug-log");
  const showing = pre.style.display !== "none";
  pre.style.display = showing ? "none" : "block";
  document.getElementById("toggle-debug-btn").textContent = showing ? "Show debug log" : "Hide debug log";
  if (!showing) await refreshDebugLog();
});

document.getElementById("premium-blocked-btn").addEventListener("click", async () => {
  const { lastAcceptedResult } = await chrome.storage.local.get(["lastAcceptedResult"]);
  if (lastAcceptedResult && lastAcceptedResult.result && lastAcceptedResult.result.task_id) {
    await send({ type: "REPORT_PREMIUM_BLOCKED", taskId: lastAcceptedResult.result.task_id });
  }
});

(async function init() {
  const { pairingToken, apiPort } = await chrome.storage.local.get(["pairingToken", "apiPort"]);
  if (pairingToken) document.getElementById("token-input").value = pairingToken;
  if (apiPort) document.getElementById("port-input").value = apiPort;
  await refreshConnection();
  await refreshCurriculum();
  await refreshLastAccepted();
  await refreshWatcherStatus();
})();
