// The client for POST /api/chat (Project/Design.md, "Front end and API").
// Plain TypeScript with no Solid imports, so it's tested with `node --test` and the
// components stay thin.

import { clean } from "./text.ts";

/** The service's length caps, counted with `charCount`. */
export const CAPS = { comment: 1000, subject: 300, thread: 1000 } as const;

export type Platform = "x" | "youtube" | "facebook";
export type Style = "match" | "neutral";

export interface ChatInput {
  comment: string;
  subject?: string;
  thread?: string;
  platform: Platform;
  style: Style;
}

export interface Citation {
  source_id: string;
  title: string;
  url: string;
  pages: string;
}

export type ChatResult =
  | { ok: true; reply: string; citations: Citation[]; fallacy: string | null; cached: boolean }
  | { ok: false; code: string; message: string; retry: boolean };

export const GENERIC_MESSAGE = "Something went wrong. Please try again.";

/** Error codes worth retrying. The 400s need the user to change the form instead. */
const RETRY_CODES = new Set([
  "turnstile_failed",
  "rate_limited",
  "internal",
  "upstream_error",
  "unavailable",
]);

const GENERIC: ChatResult = { ok: false, code: "unknown", message: GENERIC_MESSAGE, retry: true };

/** The JSON body, built once so the hash and the request use the same string. */
export function buildBody(input: ChatInput, token: string): string {
  const body: Record<string, string> = {
    comment: clean(input.comment),
    turnstile_token: token,
    platform: input.platform,
    style: input.style,
  };
  for (const field of ["subject", "thread"] as const) {
    const value = clean(input[field] ?? "");
    if (value) body[field] = value;
  }
  return JSON.stringify(body);
}

/** Hex SHA-256 of the UTF-8 bytes, for CloudFront's OAC (x-amz-content-sha256). */
export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Only http(s) URLs become links, so a `javascript:` URL can never run. */
export function isLinkable(url: string): boolean {
  try {
    const { protocol } = new URL(url);
    return protocol === "https:" || protocol === "http:";
  } catch {
    return false;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCitation(value: unknown): value is Citation {
  return (
    isRecord(value) &&
    ["source_id", "title", "url", "pages"].every((k) => typeof value[k] === "string")
  );
}

function readResult(status: number, data: unknown): ChatResult {
  if (!isRecord(data)) return GENERIC;
  if (status === 200) {
    const { reply, citations, fallacy, cached } = data;
    if (typeof reply !== "string" || !Array.isArray(citations)) return GENERIC;
    return {
      ok: true,
      reply,
      citations: citations.filter(isCitation),
      fallacy: typeof fallacy === "string" && fallacy ? fallacy : null,
      cached: cached === true,
    };
  }
  // The API's own errors always carry both; anything else (OAC's bare 403, a CloudFront
  // error page) is generic.
  const { error, message } = data;
  if (typeof error !== "string" || typeof message !== "string") return GENERIC;
  return { ok: false, code: error, message, retry: RETRY_CODES.has(error) };
}

/** Sends one request and never throws: every failure becomes a `ChatResult`. */
export async function postChat(
  input: ChatInput,
  token: string,
  fetchFn: typeof fetch = fetch,
  timeoutMs = 35_000,
): Promise<ChatResult> {
  const body = buildBody(input, token);
  try {
    const response = await fetchFn("/api/chat", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-amz-content-sha256": await sha256Hex(body),
      },
      body,
      signal: AbortSignal.timeout(timeoutMs),
    });
    let data: unknown;
    try {
      data = JSON.parse(await response.text());
    } catch {
      return GENERIC;
    }
    return readResult(response.status, data);
  } catch {
    // Network failure or timeout.
    return GENERIC;
  }
}
