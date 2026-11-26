import { render } from "@solidjs/web";

import App from "./App.tsx";
import "./style.css";

const root = document.getElementById("app")!;

// /logs is the request-logs page. It's a separate chunk, so the chat page never loads it,
// and it holds no secrets: the logs come from GET /api/logs, which needs the admin key.
if (location.pathname === "/logs") {
  void import("./LogsPage.tsx").then(({ default: LogsPage }) => {
    render(() => <LogsPage />, root);
  });
} else if (location.pathname === "/sources") {
  // The list of sources the bot cites, also its own chunk.
  void import("./SourcesPage.tsx").then(({ default: SourcesPage }) => {
    render(() => <SourcesPage />, root);
  });
} else {
  render(() => <App />, root);
}
