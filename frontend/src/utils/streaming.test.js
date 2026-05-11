import test from "node:test";
import assert from "node:assert/strict";
import { shouldAppendToken } from "./streaming.js";

test("appends non-empty token on done=true for backwards compatibility", () => {
  assert.equal(shouldAppendToken({ token: "tail", done: true }), true);
});

test("does not append empty or non-string tokens", () => {
  assert.equal(shouldAppendToken({ token: "", done: false }), false);
  assert.equal(shouldAppendToken({ token: null, done: false }), false);
  assert.equal(shouldAppendToken({ done: false }), false);
});
