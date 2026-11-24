import assert from "node:assert/strict";
import { test } from "node:test";

import { charCount, clean } from "./text.ts";

// The server trims, normalises to NFC, then counts code points (service/api.py).

test("counts emoji as one", () => {
  assert.equal(charCount("🙄"), 1);
  assert.equal(charCount("solar 🙄"), 7);
});

test("counts a decomposed accent once", () => {
  assert.equal(charCount("é"), 1);
  assert.equal(clean("é"), "é");
});

test("ignores surrounding spaces", () => {
  assert.equal(charCount("  hi \n"), 2);
  assert.equal(clean("  hi \n"), "hi");
});

test("1000 emoji fit the 1000 cap", () => {
  assert.equal(charCount("🙄".repeat(1000)), 1000);
  assert.equal(charCount("a".repeat(1001)), 1001);
});
