import test from "node:test";
import assert from "node:assert/strict";
import {
  AUTO_INTENT_OPTION,
  formatIntentConfidence,
  hasIntentClassificationDetails,
} from "./intentClassification.js";

test("auto intent option is stable", () => {
  assert.equal(AUTO_INTENT_OPTION.value, "auto");
  assert.match(AUTO_INTENT_OPTION.label, /Auto/i);
});

test("formatIntentConfidence clamps and formats percent", () => {
  assert.equal(formatIntentConfidence(0.82), "82%");
  assert.equal(formatIntentConfidence(4), "100%");
  assert.equal(formatIntentConfidence(-3), "0%");
  assert.equal(formatIntentConfidence(null), null);
});

test("hasIntentClassificationDetails detects classifier metadata", () => {
  assert.equal(hasIntentClassificationDetails({}), false);
  assert.equal(hasIntentClassificationDetails({ resolvedIntent: "general_chat" }), true);
  assert.equal(hasIntentClassificationDetails({ intentConfidence: 0.12 }), true);
});
