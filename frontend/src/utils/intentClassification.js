export const AUTO_INTENT_OPTION = {
  value: "auto",
  label: "Auto (classify)",
};

export function formatIntentConfidence(confidence) {
  if (typeof confidence !== "number" || Number.isNaN(confidence)) return null;
  const pct = Math.max(0, Math.min(100, Math.round(confidence * 100)));
  return `${pct}%`;
}

export function hasIntentClassificationDetails(message) {
  return Boolean(
    message?.resolvedIntent ||
      message?.intentMode ||
      message?.intentSource ||
      typeof message?.intentConfidence === "number" ||
      message?.intentTaxonomyVersion,
  );
}
