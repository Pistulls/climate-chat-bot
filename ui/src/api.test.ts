import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";

import { buildBody, type ChatInput, GENERIC_MESSAGE, isLinkable, postChat, sha256Hex } from "./api.ts";

const input: ChatInput = {
  comment: "Solar is useless at night 🙄",
  platform: "youtube",
  style: "match",
};

type Call = { url: string; init: RequestInit };

/** A fake fetch that records its calls and answers with `respond`. */
function fakeFetch(respond: () => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fn = async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return respond();
  };
  return { fn: fn as typeof fetch, calls };
}

const json = (status: number, payload: unknown) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });

const apiError = (status: number, error: string, message = "Server says no.") =>
  json(status, { error, message });

test("body leaves out empty context", () => {
  const body = JSON.parse(buildBody({ ...input, subject: "   ", thread: "" }, "tok"));
  assert.deepEqual(body, {
    comment: "Solar is useless at night 🙄",
    turnstile_token: "tok",
    platform: "youtube",
    style: "match",
  });
});

test("body includes cleaned context", () => {
  const body = JSON.parse(buildBody({ ...input, subject: " Heat pumps ", thread: "é" }, "t"));
  assert.equal(body.subject, "Heat pumps");
  assert.equal(body.thread, "é");
});

test("hash matches the exact body", async () => {
  assert.equal(
    await sha256Hex("abc"),
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  );
  const body = buildBody({ ...input, comment: "Café 🙄" }, "tok");
  assert.equal(await sha256Hex(body), createHash("sha256").update(body, "utf8").digest("hex"));
});

test("sends content-type and x-amz-content-sha256", async () => {
  const f = fakeFetch(() => json(200, { reply: "r", citations: [], fallacy: null, cached: false }));
  await postChat(input, "tok", f.fn);
  assert.equal(f.calls.length, 1);
  const { url, init } = f.calls[0];
  assert.equal(url, "/api/chat");
  assert.equal(init.method, "POST");
  const headers = new Headers(init.headers);
  assert.equal(headers.get("content-type"), "application/json");
  assert.equal(headers.get("x-amz-content-sha256"), await sha256Hex(init.body as string));
  assert.equal(init.body, buildBody(input, "tok"));
});

test("reads a reply", async () => {
  const citations = [{ source_id: "24-0012", title: "Ember 2026", url: "https://ember.org/r", pages: "39-41" }];
  const f = fakeFetch(() =>
    json(200, { reply: "Solar output…", citations, fallacy: "Cherry picking", cached: true }),
  );
  assert.deepEqual(await postChat(input, "tok", f.fn), {
    ok: true,
    reply: "Solar output…",
    citations,
    fallacy: "Cherry picking",
    cached: true,
  });
});

test("reads an API error message", async () => {
  const f = fakeFetch(() => apiError(400, "comment_too_long", "The comment must be 1000 characters or fewer."));
  assert.deepEqual(await postChat(input, "tok", f.fn), {
    ok: false,
    code: "comment_too_long",
    message: "The comment must be 1000 characters or fewer.",
    retry: false,
  });
});

test("turnstile_failed, 429, 500, 502 and 503 offer retry; 400s don't", async () => {
  const cases: [number, string, boolean][] = [
    [403, "turnstile_failed", true],
    [429, "rate_limited", true],
    [500, "internal", true],
    [502, "upstream_error", true],
    [503, "unavailable", true],
    [400, "bad_request", false],
    [400, "comment_too_long", false],
    [400, "subject_too_long", false],
    [400, "thread_too_long", false],
  ];
  for (const [status, code, retry] of cases) {
    const result = await postChat(input, "tok", fakeFetch(() => apiError(status, code)).fn);
    assert.equal(result.ok, false);
    assert.equal(!result.ok && result.retry, retry, code);
  }
});

const generic = { ok: false, code: "unknown", message: GENERIC_MESSAGE, retry: true };

test("a 403 without JSON is generic", async () => {
  // CloudFront's OAC refusal: a 403 whose body is not the API's JSON.
  const f = fakeFetch(() => new Response('{"message":"Forbidden"}', { status: 403 }));
  assert.deepEqual(await postChat(input, "tok", f.fn), generic);
});

test("an HTML error page is generic", async () => {
  const f = fakeFetch(() => new Response("<html><body>504 Gateway Timeout</body></html>", { status: 504 }));
  assert.deepEqual(await postChat(input, "tok", f.fn), generic);
});

test("a 200 that isn't a reply is generic", async () => {
  const f = fakeFetch(() => json(200, { hello: "world" }));
  assert.deepEqual(await postChat(input, "tok", f.fn), generic);
});

test("a network failure is generic", async () => {
  const f = fakeFetch(() => {
    throw new TypeError("Failed to fetch");
  });
  assert.deepEqual(await postChat(input, "tok", f.fn), generic);
});

test("a timeout is generic", async () => {
  // A fetch that never answers on its own, only rejects when its signal aborts.
  const never = (async (_url: string | URL | Request, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
    })) as typeof fetch;
  assert.deepEqual(await postChat(input, "tok", never, 20), generic);
});

test("javascript: and data: URLs are not linkable", () => {
  assert.equal(isLinkable("https://www.ipcc.ch/report.pdf"), true);
  assert.equal(isLinkable("http://example.org/a"), true);
  assert.equal(isLinkable("javascript:alert(1)"), false);
  assert.equal(isLinkable("JavaScript:alert(1)"), false);
  assert.equal(isLinkable("data:text/html,<script>alert(1)</script>"), false);
  assert.equal(isLinkable("not a url"), false);
  assert.equal(isLinkable(""), false);
});
