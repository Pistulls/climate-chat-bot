import { render } from "@solidjs/web";

import App from "./App.tsx";
import "./style.css";

const root = document.getElementById("app")!;

// The request-logs page is local only: it reads GET /api/logs, which only the local
// service (climate_chat.service.local) serves. A production build replaces
// import.meta.env.DEV with false, so this branch and the page's module are left out.
if (import.meta.env.DEV && location.pathname === "/logs") {
  void import("./LogsPage.tsx").then(({ default: LogsPage }) => {
    render(() => <LogsPage />, root);
  });
} else {
  render(() => <App />, root);
}
