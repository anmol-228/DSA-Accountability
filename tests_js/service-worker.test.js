"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const storage = {};
const fetchCalls = [];

global.chrome = {
  storage: {
    local: {
      async get(keys) {
        const out = {};
        for (const key of keys) if (Object.hasOwn(storage, key)) out[key] = storage[key];
        return out;
      },
      async set(values) { Object.assign(storage, values); },
    },
  },
  runtime: {
    getManifest: () => ({ version: "1.0.3" }),
    onMessage: { addListener: () => {} },
  },
  tabs: {
    query: async () => [],
    sendMessage: async () => null,
  },
};

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

global.fetch = async (url, options) => {
  fetchCalls.push({ url, options });
  return response(500, {});
};

const sw = require(path.join(__dirname, "..", "chrome-extension", "service-worker.js"));

test.beforeEach(() => {
  for (const key of Object.keys(storage)) delete storage[key];
  fetchCalls.length = 0;
  storage.pairingToken = "persistent-token";
  storage.apiPort = 8765;
  storage.apiHost = "malicious.example";
});

test("settings always force localhost and preserve the paired token", async () => {
  const settings = await sw.getSettings();
  assert.equal(settings.apiHost, "127.0.0.1");
  assert.equal(settings.pairingToken, "persistent-token");
});

test("connection succeeds without rotating or clearing the token", async () => {
  global.fetch = async (url, options) => {
    fetchCalls.push({ url, options });
    if (url.endsWith("/api/health")) return response(200, { status: "ok" });
    return response(200, { active_day: 1 });
  };
  const result = await sw.testConnection();
  assert.equal(result.paired, true);
  assert.equal(storage.pairingToken, "persistent-token");
  assert.equal(storage.apiPort, 8765);
});

test("connection automatically discovers a desktop fallback port", async () => {
  global.fetch = async (url, options) => {
    fetchCalls.push({ url, options });
    if (url.startsWith("http://127.0.0.1:8766/") && url.endsWith("/api/health")) {
      return response(200, { status: "ok" });
    }
    if (url.startsWith("http://127.0.0.1:8766/") && url.endsWith("/api/status")) {
      return response(200, { active_day: 1 });
    }
    throw new Error("connection refused");
  };
  const result = await sw.testConnection();
  assert.equal(result.paired, true);
  assert.equal(result.apiPort, 8766);
  assert.equal(storage.apiPort, 8766);
  assert.equal(storage.pairingToken, "persistent-token");
});

test("Accepted payload is forwarded unchanged with auth and persisted for UI", async () => {
  let postedBody = null;
  global.fetch = async (url, options) => {
    fetchCalls.push({ url, options });
    postedBody = JSON.parse(options.body);
    return response(200, { status: "ok", code_captured: true });
  };
  const payload = { slug: "two-sum", language: "java", code: "class Solution {}", trace_id: "trace-1" };
  const result = await sw.forwardAccepted(payload);
  assert.equal(result.ok, true);
  assert.deepEqual(postedBody, payload);
  assert.equal(fetchCalls[0].options.headers["X-DSA-Token"], "persistent-token");
  assert.deepEqual(storage.lastAcceptedResult.payload, payload);
});
