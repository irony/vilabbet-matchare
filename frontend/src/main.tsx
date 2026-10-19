import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "@xyflow/react/dist/style.css";
import "./index.css";

// mörkt tema vid inbäddning i slides: ?theme=dark
if (new URLSearchParams(window.location.search).get("theme") === "dark") {
  document.documentElement.dataset.theme = "dark";
}

const qc = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  </StrictMode>
);
