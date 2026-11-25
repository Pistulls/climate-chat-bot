// The one-shot page (Project/Plans/04.UI.md, "The page"). Markup and layout only: the
// logic lives in api.ts and text.ts, the look in style.css.
// Everything from the API is rendered as text, never as HTML.

import { createSignal, For, onSettled, Show } from "solid-js";

import { CAPS, type ChatResult, isLinkable, type Platform, postChat, type Style } from "./api.ts";
import { charCount } from "./text.ts";
import { loadTurnstile, removeWidget, renderWidget, resetWidget } from "./turnstile.ts";

const PLATFORMS: [Platform, string][] = [
  ["x", "X"],
  ["youtube", "YouTube"],
  ["facebook", "Facebook"],
];
const STYLES: [Style, string][] = [
  ["match", "Match their tone"],
  ["neutral", "Neutral"],
];
const SITE_KEY: string = import.meta.env.VITE_TURNSTILE_SITE_KEY;

function Count(props: { count: number; cap: number }) {
  return (
    <span class={["count", { over: props.count > props.cap }]}>
      {props.count}/{props.cap}
    </span>
  );
}

function pagesLabel(pages: string): string {
  return pages.includes("-") ? `pp. ${pages}` : `p. ${pages}`;
}

export default function App() {
  const [comment, setComment] = createSignal("");
  const [subject, setSubject] = createSignal("");
  const [thread, setThread] = createSignal("");
  const [platform, setPlatform] = createSignal<Platform>("youtube");
  const [style, setStyle] = createSignal<Style>("match");
  const [token, setToken] = createSignal<string | null>(null);
  const [widgetFailed, setWidgetFailed] = createSignal(false);
  const [busy, setBusy] = createSignal(false);
  const [result, setResult] = createSignal<ChatResult | null>(null);
  const [copied, setCopied] = createSignal(false);

  let widgetEl!: HTMLDivElement;
  let widgetId: string | undefined;

  onSettled(() => {
    let disposed = false;
    loadTurnstile()
      .then(() => {
        if (disposed) return;
        widgetId = renderWidget(widgetEl, SITE_KEY, (t) => {
          setToken(t);
          if (t) setWidgetFailed(false);
        });
      })
      .catch(() => setWidgetFailed(true));
    return () => {
      disposed = true;
      if (widgetId) removeWidget(widgetId);
    };
  });

  const overCap = () =>
    charCount(comment()) > CAPS.comment ||
    charCount(subject()) > CAPS.subject ||
    charCount(thread()) > CAPS.thread;
  const ready = () => !busy() && token() !== null && charCount(comment()) > 0 && !overCap();
  const reply = () => {
    const r = result();
    return r?.ok ? r : null;
  };
  const failure = () => {
    const r = result();
    return r && !r.ok ? r : null;
  };
  const buttonLabel = () => {
    if (busy()) return "Writing a sourced reply…";
    if (token() === null) return "Waiting for the bot check…";
    return "Get reply";
  };

  async function send() {
    const t = token();
    if (t === null || busy()) return;
    setBusy(true);
    setResult(null);
    setCopied(false);
    const r = await postChat(
      { comment: comment(), subject: subject(), thread: thread(), platform: platform(), style: style() },
      t,
    );
    setResult(r);
    setBusy(false);
    // Tokens are single-use: spend this one and start getting the next.
    setToken(null);
    if (widgetId) resetWidget(widgetId);
  }

  function tryAnother() {
    setComment("");
    setSubject("");
    setThread("");
    setResult(null);
    setCopied(false);
  }

  function copy(text: string) {
    navigator.clipboard.writeText(text).then(() => setCopied(true));
  }

  return (
    <main>
      <h1>Climate Chat</h1>
      <p class="intro">Paste a climate-sceptic comment and get a short, sourced reply.</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <label class="field">
          <span class="field-head">
            Comment <Count count={charCount(comment())} cap={CAPS.comment} />
          </span>
          <textarea
            rows={5}
            required
            value={comment()}
            onInput={(e) => setComment(e.currentTarget.value)}
          />
        </label>

        <details>
          <summary>Add context (optional)</summary>
          <label class="field">
            <span class="field-head">
              Posted under (a video title or topic)
              <Count count={charCount(subject())} cap={CAPS.subject} />
            </span>
            <input value={subject()} onInput={(e) => setSubject(e.currentTarget.value)} />
          </label>
          <label class="field">
            <span class="field-head">
              Replying to (the message above it)
              <Count count={charCount(thread())} cap={CAPS.thread} />
            </span>
            <textarea rows={3} value={thread()} onInput={(e) => setThread(e.currentTarget.value)} />
          </label>
        </details>

        <div class="choices">
          <fieldset>
            <legend>Platform</legend>
            <div class="segments">
              <For each={PLATFORMS}>
                {([value, label]) => (
                  <label class="option">
                    <input
                      type="radio"
                      name="platform"
                      checked={platform() === value}
                      onChange={() => setPlatform(value)}
                    />
                    {label}
                  </label>
                )}
              </For>
            </div>
          </fieldset>

          <fieldset>
            <legend>Style</legend>
            <div class="segments">
              <For each={STYLES}>
                {([value, label]) => (
                  <label class="option">
                    <input
                      type="radio"
                      name="style"
                      checked={style() === value}
                      onChange={() => setStyle(value)}
                    />
                    {label}
                  </label>
                )}
              </For>
            </div>
          </fieldset>
        </div>

        <div ref={widgetEl} />
        <Show when={widgetFailed()}>
          <p class="notice" role="alert">
            The bot check couldn't load. Please reload the page.
          </p>
        </Show>

        <button type="submit" disabled={!ready()}>
          {buttonLabel()}
        </button>
      </form>

      <Show when={failure()}>
        {(f) => (
          <section class="error" role="alert">
            <p>{f().message}</p>
            <Show when={f().retry}>
              <button type="button" disabled={!ready()} onClick={() => void send()}>
                {token() === null ? "Waiting for the bot check…" : "Retry"}
              </button>
            </Show>
          </section>
        )}
      </Show>

      <Show when={reply()}>
        {(r) => (
          <section class="reply">
            <h2>Reply</h2>
            <p class="reply-text">{r().reply}</p>
            <div class="reply-actions">
              <button type="button" onClick={() => copy(r().reply)}>
                {copied() ? "Copied" : "Copy"}
              </button>
              <button type="button" onClick={tryAnother}>
                Try another
              </button>
            </div>
            <Show when={r().fallacy}>
              <p class="fallacy">Fallacy: {r().fallacy}</p>
            </Show>
            <Show when={r().citations.length > 0}>
              <div class="sources">
                <h3>Sources</h3>
                <ol>
                  <For each={r().citations}>
                    {(c) => (
                      <li>
                        <Show when={isLinkable(c.url)} fallback={c.title}>
                          <a href={c.url} target="_blank" rel="noopener noreferrer">
                            {c.title}
                          </a>
                        </Show>
                        , {pagesLabel(c.pages)}
                      </li>
                    )}
                  </For>
                </ol>
              </div>
            </Show>
          </section>
        )}
      </Show>
    </main>
  );
}
