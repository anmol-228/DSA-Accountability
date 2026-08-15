"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {
  monaco: null,
  addEventListener: () => {},
  postMessage: () => {},
};
global.document = { querySelector: () => null };

const bridge = require(path.join(__dirname, "..", "chrome-extension", "page-bridge.js"));

test("Monaco capture prefers the Java model and reports Java", () => {
  const python = { getLanguageId: () => "python", getValue: () => "print('x')" };
  const java = { getLanguageId: () => "java", getValue: () => "class Solution {}" };
  global.window.monaco = { editor: { getModels: () => [python, java] } };
  assert.deepEqual(bridge.captureCode(), {
    code: "class Solution {}", language: "java", method: "monaco_global",
  });
});

test("DOM reconstruction sorts visual lines by top offset", () => {
  global.window.monaco = null;
  const lines = [
    { style: { top: "20px" }, innerText: "second" },
    { style: { top: "0px" }, innerText: "first" },
  ];
  global.document.querySelector = (selector) => {
    if (selector === ".monaco-editor") return null;
    if (selector === ".monaco-editor .view-lines") return { querySelectorAll: () => lines };
    return null;
  };
  assert.deepEqual(bridge.captureCode(), {
    code: "first\nsecond", language: null, method: "dom_reconstruction",
  });
});
