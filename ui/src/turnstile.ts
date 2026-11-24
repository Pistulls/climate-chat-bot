// Cloudflare Turnstile (Project/Design.md, "Cloudflare Turnstile"). The widget loads from
// Cloudflare's own URL, so it isn't an npm package. Explicit rendering lets the page
// reset it after every response, so each request gets a fresh, single-use token.

interface TurnstileOptions {
  sitekey: string;
  action: string;
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
  "refresh-expired": "auto" | "manual" | "never";
}

interface Turnstile {
  render(el: HTMLElement, options: TurnstileOptions): string;
  reset(widgetId: string): void;
  remove(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: Turnstile;
  }
}

/** The service only accepts tokens issued for this action (TURNSTILE_ACTION in guards.py). */
export const TURNSTILE_ACTION = "chat";

const SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

let loading: Promise<void> | null = null;

/** Adds Cloudflare's script once; later calls share the same promise. */
export function loadTurnstile(): Promise<void> {
  loading ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT_URL;
    script.onload = () => resolve();
    script.onerror = () => {
      loading = null; // let a later call try again
      script.remove();
      reject(new Error("The bot check couldn't load."));
    };
    document.head.append(script);
  });
  return loading;
}

/** Renders the widget in managed mode. `onToken` gets each new token, or null when the
 * current one expires or the widget fails. Returns the widget id for `resetWidget`. */
export function renderWidget(
  el: HTMLElement,
  siteKey: string,
  onToken: (token: string | null) => void,
): string {
  if (!window.turnstile) throw new Error("Turnstile isn't loaded.");
  return window.turnstile.render(el, {
    sitekey: siteKey,
    action: TURNSTILE_ACTION,
    callback: (token) => onToken(token),
    "expired-callback": () => onToken(null),
    "error-callback": () => onToken(null),
    "refresh-expired": "auto",
  });
}

/** Spends the current token and starts getting a fresh one. */
export function resetWidget(widgetId: string): void {
  window.turnstile?.reset(widgetId);
}

export function removeWidget(widgetId: string): void {
  window.turnstile?.remove(widgetId);
}
