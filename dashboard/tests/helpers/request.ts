/** JSON POST as the CLI sends it — pass a string to control the exact bytes. */
export function postJson(url: string, body: unknown, token?: string): Request {
  return new Request(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

/** Form POST as the /cli-auth browser form sends it. */
export function postForm(url: string, fields: Record<string, string>): Request {
  return new Request(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(fields).toString(),
  });
}
