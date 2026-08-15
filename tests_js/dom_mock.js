"use strict";
// Minimal DOM/chrome/window mocks so content-script.js's IIFE (which has
// top-level side effects -- chrome.runtime.onMessage.addListener,
// document.readyState checks, etc.) can be require()'d in plain Node
// without a browser. Deliberately hand-rolled instead of pulling in
// jsdom/puppeteer -- "no need for a huge framework" (production repair
// pass, section 35). Only the handful of DOM surface content-script.js
// actually touches is mocked.

function makeElement(overrides = {}) {
  return Object.assign(
    { children: [], textContent: "", closest: () => null, appendChild: () => {} },
    overrides
  );
}

function installGlobalMocks() {
  const listeners = { onMessage: [] };
  const messages = [];

  global.chrome = {
    runtime: {
      getURL: (p) => `chrome-extension://fake/${p}`,
      onMessage: { addListener: (fn) => listeners.onMessage.push(fn) },
      sendMessage: (msg) => { messages.push(msg); },
    },
    _listeners: listeners,
    _messages: messages,
  };

  global.document = {
    readyState: "complete",
    addEventListener: () => {},
    head: makeElement(),
    documentElement: makeElement(),
    body: makeElement(),
    createElement: () => makeElement(),
    querySelectorAll: () => [],
    querySelector: () => null,
  };

  global.window = {
    addEventListener: () => {},
    postMessage: () => {},
    location: { pathname: "/problems/two-sum/" },
  };

  global.self = globalThis;
  global.MutationObserver = class {
    constructor(cb) { this._cb = cb; }
    observe() {}
    disconnect() {}
  };
}

module.exports = { installGlobalMocks, makeElement };
