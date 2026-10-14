export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:18421";

const TOKEN_KEY = "finsight_token";

export function readToken() {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

export function writeToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = readToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      clearToken();
      window.dispatchEvent(new Event("finsight:auth-expired"));
    }
    const detail = data && data.detail ? data.detail : response.statusText;
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return data;
}

export async function* authenticatedEventStream(path, body, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = readToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: options.signal,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && typeof window !== "undefined") {
      clearToken();
      window.dispatchEvent(new Event("finsight:auth-expired"));
    }
    throw new Error(data.detail || response.statusText || "Stream request failed");
  }
  if (!response.body) throw new Error("Streaming response is unavailable");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const event = frame.match(/^event:\s*(.+)$/m)?.[1] || "message";
      const data = frame.match(/^data:\s*(.+)$/m)?.[1];
      if (data) yield { event, data: JSON.parse(data) };
    }
    if (done) break;
  }
}

export function quoteSocket() {
  const token = readToken();
  const base = API_URL.replace(/^http/, "ws");
  return new WebSocket(`${base}/ws/quotes?token=${encodeURIComponent(token)}`);
}
