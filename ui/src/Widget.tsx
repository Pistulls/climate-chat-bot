// One Cloudflare Turnstile widget: loads the script, renders on mount, removes on unmount.
// `onReady` hands back a reset function, for getting a fresh token after one is spent.

import { onSettled } from "solid-js";

import { type Appearance, loadTurnstile, removeWidget, renderWidget, resetWidget } from "./turnstile.ts";

const SITE_KEY: string = import.meta.env.VITE_TURNSTILE_SITE_KEY;

export default function Widget(props: {
  appearance: Appearance;
  onToken: (token: string | null) => void;
  onLoadFailed: () => void;
  onReady?: (reset: () => void) => void;
}) {
  let el!: HTMLDivElement;

  onSettled(() => {
    let disposed = false;
    let id: string | undefined;
    loadTurnstile()
      .then(() => {
        if (disposed) return;
        id = renderWidget(el, SITE_KEY, (t) => props.onToken(t), props.appearance);
        props.onReady?.(() => {
          if (id) resetWidget(id);
        });
      })
      .catch(() => props.onLoadFailed());
    return () => {
      disposed = true;
      if (id) removeWidget(id);
    };
  });

  return <div class="widget" ref={el} />;
}
