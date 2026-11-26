// Local-only request logs (dev server at /logs; see main.tsx). One page at a time from
// GET /api/logs, newest first. The service pages by cursor, so "Older" follows the
// cursor it returned and "Newer" steps back through the cursors already used.
// Comments are visitor text: rendered as text only, never as HTML.

import { createSignal, For, onSettled, Show } from "solid-js";

const PAGE_SIZE = 25;

interface LogCall {
  role: string;
  model: string;
  cost?: number;
}

interface LogItem {
  time: string;
  request_id: string;
  comment?: string;
  subject?: string;
  thread?: string;
  outcome?: string;
  cached?: boolean;
  latency_ms?: number;
  cost?: number;
  user_hash?: string;
  claim?: string;
  calls?: LogCall[];
}

interface LogPage {
  table: string;
  items: LogItem[];
  next: string | null;
}

const timeFormat = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function localTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : timeFormat.format(d);
}

function money(cost: number | undefined): string {
  return cost === undefined ? "–" : `$${cost.toFixed(5)}`;
}

function seconds(ms: number | undefined): string {
  return ms === undefined ? "–" : `${(ms / 1000).toFixed(1)}s`;
}

function models(calls: LogCall[] | undefined): string {
  return [...new Set((calls ?? []).map((c) => c.model))].join(", ") || "–";
}

/** "reply", "not_a_claim", or "error:rate_limited" -> a word and a tone for the pill. */
function outcome(value: string | undefined): { label: string; tone: string } {
  if (!value) return { label: "–", tone: "plain" };
  if (value.startsWith("error:")) return { label: value.slice(6).replaceAll("_", " "), tone: "bad" };
  if (value === "reply") return { label: "reply", tone: "good" };
  return { label: value.replaceAll("_", " "), tone: "plain" };
}

export default function LogsPage() {
  // cursors[i] is the cursor that loads page i; page 0 needs none.
  const [cursors, setCursors] = createSignal<(string | null)[]>([null]);
  const [page, setPage] = createSignal<LogPage | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [error, setError] = createSignal<string | null>(null);

  const pageNumber = () => cursors().length;

  async function load(cursor: string | null): Promise<boolean> {
    setLoading(true);
    setError(null);
    try {
      const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
      if (cursor) query.set("cursor", cursor);
      const response = await fetch(`/api/logs?${query}`);
      const body = await response.json().catch(() => null);
      if (!response.ok || !body) {
        setError(body?.message ?? `The service answered ${response.status}.`);
        return false;
      }
      setPage(body as LogPage);
      window.scrollTo({ top: 0 });
      return true;
    } catch {
      setError(
        "Couldn't reach the local service. Start it with: uv run python -m climate_chat.service.local",
      );
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function older() {
    const next = page()?.next;
    if (!next) return;
    if (await load(next)) setCursors([...cursors(), next]);
  }

  async function newer() {
    const stack = cursors();
    if (stack.length < 2) return;
    if (await load(stack[stack.length - 2])) setCursors(stack.slice(0, -1));
  }

  async function refresh() {
    if (await load(null)) setCursors([null]);
  }

  onSettled(() => {
    document.title = "Climate Chat request logs";
    document.body.classList.add("plain");
    void load(null);
  });

  return (
    <main class="logs-page">
      <header class="logs-head">
        <div>
          <h1>Request logs</h1>
          <p class="intro">
            Newest first, from{" "}
            <Show when={page()} fallback="the logs table">
              {(p) => <code>{p().table}</code>}
            </Show>
            . This page only exists on your machine.
          </p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={loading()}>
          Refresh
        </button>
      </header>

      <Show when={error()}>
        {(message) => (
          <p class="notice" role="alert">
            {message()}
          </p>
        )}
      </Show>

      <Show when={page()}>
        {(p) => (
          <>
            <div class="table-scroll" aria-busy={loading() ? "true" : undefined}>
              <table class="logs">
                <thead>
                  <tr>
                    <th scope="col">Time</th>
                    <th scope="col">Outcome</th>
                    <th scope="col">Comment</th>
                    <th scope="col">Visitor</th>
                    <th scope="col" class="num">Latency</th>
                    <th scope="col" class="num">Cost</th>
                    <th scope="col">Models</th>
                  </tr>
                </thead>
                <tbody>
                  <For
                    each={p().items}
                    fallback={
                      <tr>
                        <td colspan={7} class="empty">
                          {pageNumber() === 1
                            ? "No requests in the retention window yet."
                            : "No older requests."}
                        </td>
                      </tr>
                    }
                  >
                    {(item) => {
                      const o = outcome(item.outcome);
                      return (
                        <tr>
                          <td class="time" title={`${item.time} (UTC), request ${item.request_id}`}>
                            {localTime(item.time)}
                          </td>
                          <td>
                            <span class={`pill ${o.tone}`}>{o.label}</span>
                            <Show when={item.cached}>
                              <span class="pill plain">cached</span>
                            </Show>
                          </td>
                          <td class="comment">
                            {item.comment || "–"}
                            <Show when={item.subject || item.thread || item.claim}>
                              <dl class="context">
                                <Show when={item.subject}>
                                  <dt>Posted under</dt>
                                  <dd>{item.subject}</dd>
                                </Show>
                                <Show when={item.thread}>
                                  <dt>Replying to</dt>
                                  <dd>{item.thread}</dd>
                                </Show>
                                <Show when={item.claim}>
                                  <dt>Claim</dt>
                                  <dd>{item.claim}</dd>
                                </Show>
                              </dl>
                            </Show>
                          </td>
                          <td class="visitor" title={item.user_hash}>
                            {item.user_hash ? item.user_hash.slice(0, 8) : "–"}
                          </td>
                          <td class="num">{seconds(item.latency_ms)}</td>
                          <td class="num">{money(item.cost)}</td>
                          <td class="models">{models(item.calls)}</td>
                        </tr>
                      );
                    }}
                  </For>
                </tbody>
              </table>
            </div>

            <nav class="pager" aria-label="Log pages">
              <button
                type="button"
                onClick={() => void newer()}
                disabled={loading() || pageNumber() < 2}
              >
                Newer
              </button>
              <span>Page {pageNumber()}</span>
              <button type="button" onClick={() => void older()} disabled={loading() || !p().next}>
                Older
              </button>
            </nav>
          </>
        )}
      </Show>
    </main>
  );
}
