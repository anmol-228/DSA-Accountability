/*
 * content-script.js — runs in the isolated content-script world on
 * https://leetcode.com/problems/*. Responsibilities:
 *   1. Tell the service worker which problem is open (slug) so the desktop
 *      app can start a "fresh session" if this matches today's task.
 *   2. Watch for a fresh Accepted result via MutationObserver (robust,
 *      multi-strategy — LeetCode's DOM changes over time, see
 *      docs/TROUBLESHOOTING.md).
 *   3. On Accepted, ask page-bridge.js (page context) for the current
 *      editor code and detected language, then hand everything to the
 *      service worker to forward to the desktop app.
 *
 * This script never reads cookies, auth tokens, or account/history data.
 * It only observes the DOM of the page the user is already looking at.
 */
(function () {
  // Bump on every content-script.js change. Reloading the extension via
  // chrome://extensions does NOT re-inject this into an already-open tab
  // -- only a full page refresh does. This version is exposed via a
  // PING_CONTENT_SCRIPT handshake (see below) so the popup/service-worker
  // can detect a stale, already-open tab still running an old version
  // instead of silently reporting "watcher ready" (production repair
  // pass, section 30 -- this exact gap caused a real, confusing failure
  // this session: an extension reload didn't help until the page itself
  // was also refreshed).
  const CONTENT_SCRIPT_VERSION = "1.0.3";
  const SUBMIT_ARM_WINDOW_MS = 2 * 60 * 1000;

  const KNOWN_LANGUAGES = [
    "C++", "Java", "Python", "Python3", "C", "C#", "JavaScript", "TypeScript",
    "PHP", "Swift", "Kotlin", "Dart", "Go", "Ruby", "Scala", "Rust",
    "Racket", "Erlang", "Elixir",
  ];

  let lastFiredKey = null;
  let submitArmedAt = null;
  let lastNotifiedSlug = null;
  let bridgeInjected = false;
  let pendingCodeRequests = new Map();

  function newTraceId() {
    return (self.crypto && crypto.randomUUID) ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  // Responds to the popup/service-worker asking "are you the current
  // version, and are you even here at all" -- lets the UI tell the user
  // "refresh this tab" instead of silently behaving as if nothing is
  // wrong when an old content script is still resident in an
  // already-open tab after an extension reload.
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message && message.type === "PING_CONTENT_SCRIPT") {
      sendResponse({ type: "PONG_CONTENT_SCRIPT", version: CONTENT_SCRIPT_VERSION, slug: currentSlug() });
      return true;
    }
    return false;
  });

  function injectBridgeOnce() {
    if (bridgeInjected) return;
    const script = document.createElement("script");
    script.src = chrome.runtime.getURL("page-bridge.js");
    script.onload = () => script.remove();
    (document.head || document.documentElement).appendChild(script);
    bridgeInjected = true;
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== "DSA_ACCOUNTABILITY_CODE_RESULT") return;
    const resolver = pendingCodeRequests.get(event.data.requestId);
    if (resolver) {
      pendingCodeRequests.delete(event.data.requestId);
      resolver(event.data.result);
    }
  });

  function requestCodeFromPage(timeoutMs = 1500) {
    return new Promise((resolve) => {
      const requestId = `${Date.now()}-${Math.random()}`;
      const timer = setTimeout(() => {
        pendingCodeRequests.delete(requestId);
        resolve(null);
      }, timeoutMs);
      pendingCodeRequests.set(requestId, (result) => {
        clearTimeout(timer);
        resolve(result);
      });
      window.postMessage({ type: "DSA_ACCOUNTABILITY_REQUEST_CODE", requestId }, "*");
    });
  }

  function currentSlug() {
    const match = window.location.pathname.match(/\/problems\/([^/]+)/);
    return match ? match[1] : null;
  }

  function _hasOnlyIconChildren(el) {
    for (const child of el.children) {
      if (child.tagName !== "IMG" && child.tagName !== "SVG") return false;
    }
    return true;
  }

  function detectLanguage() {
    // Strategy 1: any visible button/span whose exact trimmed text is a
    // known LeetCode language name (the language-select control).
    //
    // Previously required el.children.length === 0 (a true DOM leaf).
    // LeetCode's language-selector button now renders with a child <img>
    // (a dropdown/language icon) alongside the text -- confirmed live,
    // 2026-08-12 -- so that button was never a leaf and detection always
    // returned null. Icon-only children (img/svg, which never contribute
    // to textContent) no longer disqualify a match; anything else
    // (nested text-bearing elements, which could make a large container
    // falsely match a short language name like "C" or "Go") still does,
    // preserving the original precision for those short-name cases.
    const candidates = document.querySelectorAll("button, span, div");
    for (const el of candidates) {
      const text = (el.textContent || "").trim();
      if (KNOWN_LANGUAGES.includes(text) && _hasOnlyIconChildren(el)) {
        return text.toLowerCase() === "python3" ? "python" : text.toLowerCase();
      }
    }
    return null;
  }

  function normalizeLanguage(value) {
    if (!value) return null;
    const match = KNOWN_LANGUAGES.find(
      (known) => known.toLowerCase() === String(value).trim().toLowerCase()
    );
    if (!match) return null;
    return match.toLowerCase() === "python3" ? "python" : match.toLowerCase();
  }

  function resolveCapturedLanguage(codeResult, domLanguage) {
    // The PAGE-context bridge can identify the exact Monaco model selected
    // for capture. Prefer that over a DOM label, whose markup changes often.
    return normalizeLanguage(codeResult && codeResult.language) || normalizeLanguage(domLanguage);
  }

  function isFreshSubmitArm(armedAt, now = Date.now()) {
    return Number.isFinite(armedAt) && now >= armedAt && now - armedAt <= SUBMIT_ARM_WINDOW_MS;
  }

  function findAcceptedNode() {
    // Strategy 1: LeetCode's semantic locator attribute (subject to change).
    let el = document.querySelector('[data-e2e-locator="submission-result"]');
    if (el && el.textContent && el.textContent.trim() === "Accepted") return el;

    // Strategy 2: scan short, leaf text nodes for the exact word "Accepted"
    // inside anything that looks like a results/status panel.
    const all = document.querySelectorAll("span, div, h1, h2, h3");
    for (const node of all) {
      if (node.children.length > 0) continue; // only leaf nodes
      const text = (node.textContent || "").trim();
      if (text !== "Accepted") continue;
      const container = node.closest(
        '[class*="result" i], [class*="submission" i], [id*="result" i]'
      );
      if (container) return node;
    }
    return null;
  }

  let debounceTimer = null;
  function scheduleScan() {
    notifyPageOpened(); // LeetCode uses SPA navigation; the content script is not reloaded.
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(scanForAccepted, 400);
  }

  async function scanForAccepted() {
    // Merely opening a page that already shows an old Accepted result must
    // never count. Only a recent, real click on LeetCode's Submit button arms
    // one detection window.
    if (!isFreshSubmitArm(submitArmedAt)) {
      submitArmedAt = null;
      return;
    }
    const node = findAcceptedNode();
    if (!node) return;

    const slug = currentSlug();
    if (!slug) return;

    const nowMinuteBucket = Math.floor(Date.now() / 15000); // 15s de-dup window
    const key = `${slug}|${nowMinuteBucket}`;
    if (key === lastFiredKey) return;
    lastFiredKey = key;
    submitArmedAt = null; // one real submit can produce at most one forwarded Accepted

    const traceId = newTraceId();
    console.debug(`[DSA Accountability trace=${traceId}] Accepted node matched for slug=${slug}`);

    const domLanguage = detectLanguage();
    const codeResult = await requestCodeFromPage();
    const language = resolveCapturedLanguage(codeResult, domLanguage);
    console.debug(`[DSA Accountability trace=${traceId}] language=${language} capture=${codeResult ? codeResult.method : "failed"}`);

    chrome.runtime.sendMessage({
      type: "ACCEPTED_DETECTED",
      payload: {
        slug,
        language,
        code: codeResult ? codeResult.code : null,
        code_capture_method: codeResult ? codeResult.method : "failed",
        timestamp: new Date().toISOString(),
        source: "fresh_submission",
        trace_id: traceId,
        content_script_version: CONTENT_SCRIPT_VERSION,
      },
    });
  }

  function watchSubmitClicks() {
    document.addEventListener(
      "click",
      (e) => {
        const target = e.target;
        if (!(target instanceof Element)) return;
        const btn = target.closest("button");
        if (btn && /submit/i.test(btn.textContent || "")) {
          lastFiredKey = null; // allow a new Accepted result to fire again
          submitArmedAt = Date.now();
          console.debug(`[DSA Accountability] fresh Submit armed for ${currentSlug() || "unknown slug"}`);
        }
      },
      true
    );
  }

  function notifyPageOpened() {
    const slug = currentSlug();
    if (slug && slug !== lastNotifiedSlug) {
      lastNotifiedSlug = slug;
      console.debug(`[DSA Accountability] page opened, slug=${slug}, content_script_version=${CONTENT_SCRIPT_VERSION}`);
      chrome.runtime.sendMessage({
        type: "PROBLEM_PAGE_OPENED",
        payload: { slug, content_script_version: CONTENT_SCRIPT_VERSION },
      });
      return true;
    }
    return false;
  }

  function init() {
    injectBridgeOnce();
    notifyPageOpened();
    watchSubmitClicks();
    const observer = new MutationObserver(scheduleScan);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Test-only hook (production repair pass, section 35-36): exposes pure,
  // DOM-dependent-but-chrome-API-independent logic for a real Node test
  // harness (tests_js/). `module` never exists in a real browser content
  // script, so this has zero effect on runtime behavior -- it only runs
  // under `node --test`.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      CONTENT_SCRIPT_VERSION, KNOWN_LANGUAGES, currentSlug, detectLanguage,
      findAcceptedNode, _hasOnlyIconChildren, newTraceId, normalizeLanguage,
      resolveCapturedLanguage, isFreshSubmitArm, SUBMIT_ARM_WINDOW_MS,
      notifyPageOpened,
    };
  }
})();
