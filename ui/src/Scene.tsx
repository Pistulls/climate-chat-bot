// The animated backdrop: "Road being built" from the design canvas. The scene is a fixed
// 1440x900 stage of inline SVG and CSS keyframes, scaled here to cover the window and
// centred. Its markup is our own static file, bundled at build time, never API data.
// It loads as its own chunk (~70 KB gzipped), so the page and bot check don't wait for it;
// its timeline starts when it lands.

import { createSignal, onSettled, Show } from "solid-js";

import "./scene/road-scene.css";

const WIDTH = 1440;
const HEIGHT = 900;

function coverScale(): number {
  return Math.max(window.innerWidth / WIDTH, window.innerHeight / HEIGHT);
}

export default function Scene() {
  const [scale, setScale] = createSignal(coverScale());
  const [html, setHtml] = createSignal<string | null>(null);

  onSettled(() => {
    let disposed = false;
    import("./scene/road-scene.html?raw").then((m) => {
      if (!disposed) setHtml(m.default);
    });
    const onResize = () => setScale(coverScale());
    window.addEventListener("resize", onResize);
    return () => {
      disposed = true;
      window.removeEventListener("resize", onResize);
    };
  });

  return (
    <div class="backdrop">
      <Show when={html()}>
        {(markup) => (
          <div
            class="stage"
            style={{ transform: `translate(-50%, -50%) scale(${scale()})` }}
            innerHTML={markup()}
          />
        )}
      </Show>
    </div>
  );
}
