/**
 * Shared chat error parsing for HTTP JSON errors and SSE error frames.
 */

export function parseChatError({ status, detail, message }) {
  let errMsg =
    message || "Sorry, I'm having trouble connecting to the AI service.";
  let detectedPiiTypes = null;
  let piiCount = 0;
  const stripUser = status === 400 || status === 403;

  if (status === 400 && !detail) {
    errMsg = "Message blocked by AI Prompt Guard.";
  } else if (detail) {
    if (typeof detail === "object") {
      errMsg = detail.message || JSON.stringify(detail);
      detectedPiiTypes = detail.detected_pii_types || null;
      piiCount = detail.pii_count || 0;
      if (detail.description) {
        errMsg = `Access Denied: ${detail.description}`;
      }
    } else {
      errMsg = detail;
    }
  }

  return { errMsg, detectedPiiTypes, piiCount, stripUser };
}

export function buildAssistantErrorMessage({
  errMsg,
  detectedPiiTypes,
  piiCount,
  selectedSensitivity,
}) {
  return {
    role: "assistant",
    content: errMsg,
    timestamp: new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    isError: true,
    providedSensitivity: selectedSensitivity,
    detectedPiiTypes,
    piiCount,
  };
}

export function applyChatErrorToMessages(
  prev,
  { errMsg, detectedPiiTypes, piiCount, stripUser, selectedSensitivity },
) {
  const next = [...prev];
  if (stripUser && next[next.length - 1]?.role === "user") {
    next.pop();
  }
  return [
    ...next,
    buildAssistantErrorMessage({
      errMsg,
      detectedPiiTypes,
      piiCount,
      selectedSensitivity,
    }),
  ];
}

/** Normalize SSE `data.error` (string or structured object). */
export function parseSseChatError(dataError) {
  if (typeof dataError === "string") {
    return parseChatError({ status: 500, message: dataError });
  }
  return parseChatError({
    status: dataError.status ?? 500,
    detail: dataError.detail,
    message: dataError.message,
  });
}
