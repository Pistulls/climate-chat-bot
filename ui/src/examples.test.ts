import assert from "node:assert/strict";
import { test } from "node:test";

import { EXAMPLES, randomExample } from "./examples.ts";

test("picks from the list, first to last", () => {
  assert.equal(randomExample(() => 0), EXAMPLES[0]);
  assert.equal(randomExample(() => 0.9999999), EXAMPLES[EXAMPLES.length - 1]);
});

test("always returns one of the examples", () => {
  for (let i = 0; i < 200; i++) assert.ok(EXAMPLES.includes(randomExample()));
});
