export function shouldAppendToken(data) {
  return typeof data?.token === "string" && data.token.length > 0;
}
