import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// The base stylesheet, before `App` and not after it. Imports are evaluated in source order, and
// `App` brings in the shell and chart sheets -- both of which override rules in here. Put this
// second and the base sheet wins instead, which is the cascade backwards.
//
// It moved out of `/static` when the Jinja pages went. It was always this app's stylesheet; being
// served separately only meant two interfaces could drift apart without anyone noticing.
import "./styles/app.css";

import { App } from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("index.html is missing #root.");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
