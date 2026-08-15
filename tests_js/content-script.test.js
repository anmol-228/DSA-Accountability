"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const { installGlobalMocks, makeElement } = require("./dom_mock.js");

installGlobalMocks();
const cs = require(path.join(__dirname, "..", "chrome-extension", "content-script.js"));

test("currentSlug extracts the slug from a real LeetCode problem URL", () => {
  global.window.location.pathname = "/problems/reverse-integer/";
  assert.equal(cs.currentSlug(), "reverse-integer");
});

test("currentSlug returns null off the /problems/ path", () => {
  global.window.location.pathname = "/problemset/all/";
  assert.equal(cs.currentSlug(), null);
});

test("KNOWN_LANGUAGES includes java and known short names", () => {
  assert.ok(cs.KNOWN_LANGUAGES.includes("Java"));
  assert.ok(cs.KNOWN_LANGUAGES.includes("C"));
  assert.ok(cs.KNOWN_LANGUAGES.includes("Go"));
});

test("content-script version matches manifest version", () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "chrome-extension", "manifest.json"), "utf8"));
  assert.equal(cs.CONTENT_SCRIPT_VERSION, manifest.version);
});

test("SPA navigation emits exactly one new session-start notification per slug", () => {
  global.chrome._messages.length = 0;
  global.window.location.pathname = "/problems/reverse-integer/";
  assert.equal(cs.notifyPageOpened(), true);
  assert.equal(cs.notifyPageOpened(), false);
  assert.equal(global.chrome._messages.length, 1);
  assert.equal(global.chrome._messages[0].type, "PROBLEM_PAGE_OPENED");
  assert.equal(global.chrome._messages[0].payload.slug, "reverse-integer");
});

test("_hasOnlyIconChildren: true for a button with only an <img> child", () => {
  const img = makeElement({ tagName: "IMG" });
  const button = makeElement({ children: [img] });
  assert.equal(cs._hasOnlyIconChildren(button), true);
});

test("_hasOnlyIconChildren: true for a leaf with zero children (unchanged old behavior)", () => {
  const leaf = makeElement({ children: [] });
  assert.equal(cs._hasOnlyIconChildren(leaf), true);
});

test("_hasOnlyIconChildren: false when a child is not an icon (e.g. nested text span)", () => {
  const span = makeElement({ tagName: "SPAN" });
  const container = makeElement({ children: [span] });
  assert.equal(cs._hasOnlyIconChildren(container), false);
});

test("_hasOnlyIconChildren: true for a mix of IMG and SVG icon children", () => {
  const img = makeElement({ tagName: "IMG" });
  const svg = makeElement({ tagName: "SVG" });
  const button = makeElement({ children: [img, svg] });
  assert.equal(cs._hasOnlyIconChildren(button), true);
});

test("detectLanguage: THE REAL BUG -- matches 'Java' even with an icon child (regression for the live fix)", () => {
  const icon = makeElement({ tagName: "IMG" });
  const languageButton = makeElement({ textContent: "Java", children: [icon] });
  global.document.querySelectorAll = () => [languageButton];
  assert.equal(cs.detectLanguage(), "java");
});

test("detectLanguage: normalizes Python3 -> python", () => {
  const el = makeElement({ textContent: "Python3", children: [] });
  global.document.querySelectorAll = () => [el];
  assert.equal(cs.detectLanguage(), "python");
});

test("detectLanguage: returns null when nothing matches a known language", () => {
  global.document.querySelectorAll = () => [makeElement({ textContent: "Submit", children: [] })];
  assert.equal(cs.detectLanguage(), null);
});

test("detectLanguage: a large container with extra text does NOT falsely match a short language name", () => {
  // Regression guard for the fix itself: removing the leaf-only
  // requirement entirely (rather than allowing only icon children) would
  // have let a container like this falsely match "C" or "Go".
  const bigContainer = makeElement({
    textContent: "Copyright 2026 LeetCode. All rights reserved. Go to problem list.",
    children: [makeElement({ tagName: "SPAN" })],
  });
  global.document.querySelectorAll = () => [bigContainer];
  assert.equal(cs.detectLanguage(), null);
});

test("resolveCapturedLanguage prefers the Java Monaco model over missing DOM detection", () => {
  assert.equal(cs.resolveCapturedLanguage({ language: "java" }, null), "java");
});

test("resolveCapturedLanguage falls back to normalized DOM language", () => {
  assert.equal(cs.resolveCapturedLanguage({ language: null }, "Python3"), "python");
});

test("fresh Accepted forwarding requires a recent Submit arm", () => {
  const now = 1_000_000;
  assert.equal(cs.isFreshSubmitArm(null, now), false);
  assert.equal(cs.isFreshSubmitArm(now - cs.SUBMIT_ARM_WINDOW_MS - 1, now), false);
  assert.equal(cs.isFreshSubmitArm(now - 500, now), true);
});

test("findAcceptedNode: matches the semantic data-e2e-locator strategy", () => {
  const node = makeElement({ textContent: "Accepted" });
  global.document.querySelector = (sel) =>
    sel === '[data-e2e-locator="submission-result"]' ? node : null;
  assert.equal(cs.findAcceptedNode(), node);
});

test("findAcceptedNode: returns null when nothing says exactly 'Accepted'", () => {
  global.document.querySelector = () => null;
  global.document.querySelectorAll = () => [makeElement({ textContent: "Wrong Answer", children: [] })];
  assert.equal(cs.findAcceptedNode(), null);
});

test("findAcceptedNode: fallback strategy requires a result/submission container, not just the word Accepted anywhere", () => {
  global.document.querySelector = () => null;
  const orphanNode = makeElement({
    textContent: "Accepted",
    children: [],
    closest: () => null, // not inside any result/submission container
  });
  global.document.querySelectorAll = () => [orphanNode];
  assert.equal(cs.findAcceptedNode(), null);
});

test("newTraceId produces a non-empty, unique-looking string each call", () => {
  const a = cs.newTraceId();
  const b = cs.newTraceId();
  assert.ok(typeof a === "string" && a.length > 0);
  assert.notEqual(a, b);
});
