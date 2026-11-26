// The one-shot page (Project/Plans/04.UI.md, "The page"). Markup and layout only: the
// logic lives in api.ts and text.ts, the look in style.css.
// Everything from the API is rendered as text, never as HTML.
//
// Opening sequence: the road scene plays behind a bot-check card. Once the check passes,
// the card fades away and the form fades in, no sooner than FORM_DELAY_MS after opening.
// The gate's token only lets the visitor in. Each request spends a token from the form's
// own widget, which stays hidden unless Cloudflare wants another tick.

import { createSignal, For, onSettled, Show } from "solid-js";

import { CAPS, type ChatResult, isLinkable, type Platform, postChat, type Style } from "./api.ts";
import { EXAMPLES } from "./examples.ts";
import Scene from "./Scene.tsx";
import { charCount } from "./text.ts";
import Widget from "./Widget.tsx";

const PLATFORMS: [Platform, string][] = [
  ["x", "X"],
  ["youtube", "YouTube"],
  ["facebook", "Facebook"],
];
const STYLES: [Style, string][] = [
  ["match", "Match their tone"],
  ["neutral", "Neutral"],
];
const FORM_DELAY_MS = 4000;

const WAIT_STEP_MS = 3000;
const WAIT_LABELS = [
  "Writing a sourced reply…",
  "This is taking a while, I wonder why? 🤨",
  "Oh, it's because I don't want to pay the big money for the fast models when it's public on the internet 😜",
];

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

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

  // The gate: passed once, then the form takes over.
  const [verified, setVerified] = createSignal(false);
  const [gateFailed, setGateFailed] = createSignal(false);
  const [showForm, setShowForm] = createSignal(false);
  const openedAt = performance.now();

  function passGate() {
    if (verified()) return;
    setVerified(true);
    const wait = prefersReducedMotion()
      ? 0
      : Math.max(0, FORM_DELAY_MS - (performance.now() - openedAt));
    setTimeout(() => setShowForm(true), wait);
  }

  let resetFormWidget: (() => void) | undefined;

  // The chat card arrives collapsed to its title row ("Start Chat") and expands downwards
  // on click. Its top is fixed where the full card's top would sit when centred, so the
  // expansion never shifts it.
  const [open, setOpen] = createSignal(false);
  const [settled, setSettled] = createSignal(false); // expansion finished: stop clipping
  const [cardTop, setCardTop] = createSignal(0);
  let chatCard: HTMLDivElement | undefined;
  let chatBodyInner: HTMLDivElement | undefined;
  let commentBox: HTMLTextAreaElement | undefined;

  function placeCard() {
    if (open() || !chatCard || !chatBodyInner) return;
    const fullHeight = chatCard.offsetHeight + chatBodyInner.scrollHeight;
    setCardTop(Math.max(16, (window.innerHeight - fullHeight) / 2));
  }

  onSettled(() => {
    window.addEventListener("resize", placeCard);
    return () => window.removeEventListener("resize", placeCard);
  });

  let examplesDialog: HTMLDialogElement | undefined;

  /** Fills the comment box with an example, replacing what was there. */
  function pickExample(text: string) {
    setComment(text);
    examplesDialog?.close();
    commentBox?.focus();
  }

  function openChat() {
    setOpen(true);
    if (prefersReducedMotion()) setSettled(true);
    // The button is gone, so move focus to where the visitor will type next.
    requestAnimationFrame(() => commentBox?.focus({ preventScroll: true }));
  }

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
  // The button's words while a reply is being written, moving on every WAIT_STEP_MS: the
  // cheap models can be slow, so the page owns up to it.
  const [waitStage, setWaitStage] = createSignal(0);
  const buttonLabel = () => {
    if (busy()) return WAIT_LABELS[waitStage()];
    if (token() === null) return "Waiting for the bot check…";
    return "Get reply";
  };

  async function send() {
    const t = token();
    if (t === null || busy()) return;
    setBusy(true);
    setResult(null);
    setCopied(false);
    setWaitStage(0);
    const timers = WAIT_LABELS.slice(1).map((_, i) =>
      setTimeout(() => setWaitStage(i + 1), WAIT_STEP_MS * (i + 1)),
    );
    try {
      const r = await postChat(
        { comment: comment(), subject: subject(), thread: thread(), platform: platform(), style: style() },
        t,
      );
      setResult(r);
    } finally {
      timers.forEach(clearTimeout);
      setWaitStage(0);
      setBusy(false);
      // Tokens are single-use: spend this one and start getting the next.
      setToken(null);
      resetFormWidget?.();
    }
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
    <>
      <Scene />
      <main class={["overlay", { "top-anchored": showForm() }]}>
        <Show when={!showForm()}>
          <section class={["card", "gate", { leaving: verified() }]} aria-hidden={verified() ? "true" : undefined}>
            <h1>Climate Chat</h1>
            <p class="intro">
              Get short, sourced replies to climate-sceptic comments. First, a quick check that
              you're a person.
            </p>
            <Widget
              appearance="always"
              onToken={(t) => t && passGate()}
              onLoadFailed={() => setGateFailed(true)}
            />
            <Show when={gateFailed()}>
              <p class="notice" role="alert">
                The bot check couldn't load. Please reload the page.
              </p>
            </Show>
          </section>
        </Show>

        <Show when={showForm()}>
          <div
            class="card enter"
            style={{ "margin-top": `${cardTop()}px` }}
            ref={(el) => {
              chatCard = el;
              requestAnimationFrame(placeCard);
            }}
          >
            <Show
              when={open()}
              fallback={
                <button
                  type="button"
                  class="start"
                  aria-expanded="false"
                  aria-controls="chat-body"
                  onClick={openChat}
                >
                  Start Chat
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </button>
              }
            >
              <h1>Climate Chat</h1>
            </Show>

            <div
              id="chat-body"
              class={["expander", { open: open(), settled: settled() }]}
              inert={!open()}
              onTransitionEnd={(e) => {
                if (e.target === e.currentTarget && open()) setSettled(true);
              }}
            >
              <div class="expander-inner" ref={chatBodyInner}>
                <p class="intro">Paste a climate-sceptic comment and get a short, sourced reply.</p>

                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void send();
                  }}
                >
                  <p class="examples-hint">
                    See some{" "}
                    <button
                      type="button"
                      class="link"
                      aria-haspopup="dialog"
                      onClick={() => examplesDialog?.showModal()}
                    >
                      examples
                    </button>
                  </p>

                  <label class="field">
                    <span class="field-head">
                      Comment <Count count={charCount(comment())} cap={CAPS.comment} />
                    </span>
                    <textarea
                      ref={commentBox}
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

                  <Widget
                    appearance="interaction-only"
                    onToken={(t) => {
                      setToken(t);
                      if (t) setWidgetFailed(false);
                    }}
                    onLoadFailed={() => setWidgetFailed(true)}
                    onReady={(reset) => (resetFormWidget = reset)}
                  />
                  <Show when={widgetFailed()}>
                    <p class="notice" role="alert">
                      The bot check couldn't load. Please reload the page.
                    </p>
                  </Show>

                  <button type="submit" disabled={!ready()} aria-busy={busy() ? "true" : undefined}>
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
              </div>
            </div>
          </div>
        </Show>
      </main>

      {/* A native modal: focus stays inside, Escape closes it, and it sits in the top
          layer above the card. Clicking the backdrop (the dialog itself) closes it too. */}
      <dialog
        class="examples"
        aria-labelledby="examples-title"
        ref={examplesDialog}
        onClick={(e) => {
          if (e.target === e.currentTarget) e.currentTarget.close();
        }}
      >
        <div class="examples-panel">
          <div class="examples-head">
            <h2 id="examples-title">Example comments</h2>
            <button
              type="button"
              class="close"
              aria-label="Close"
              onClick={() => examplesDialog?.close()}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
          <p class="examples-note">Choose one to put it in the comment box.</p>
          <ul>
            <For each={EXAMPLES}>
              {(text) => (
                <li>
                  <button type="button" onClick={() => pickExample(text)}>
                    {text}
                  </button>
                </li>
              )}
            </For>
          </ul>
        </div>
      </dialog>
    </>
  );
}
