import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The app is served by FastAPI from its own origin, never from a separate host. That is a
// deliberate choice, not an accident of convenience: the session is an HttpOnly cookie with
// SameSite=lax and there is no CSRF token anywhere in this system, so a cross-site frontend would
// need SameSite=None; Secure and a CSRF layer built to go with it. Same origin needs neither.
//
// In development Vite serves the page and proxies /api to uvicorn. localhost:5173 and
// localhost:8000 are the *same site* -- SameSite ignores the port -- so the existing cookie is
// sent unchanged and no backend setting has to be relaxed to work locally.
export default defineConfig({
  plugins: [react()],
  // The app is the interface now, mounted at the root. Written out rather than left to default
  // so that it is a visible decision: `BASENAME` in App.tsx reads it, and the router's basename
  // and the asset URLs have to agree or a reload serves the page from a path the bundle is not
  // under.
  base: "/",
  build: {
    // Straight into the package FastAPI serves, so there is one artefact and no copy step.
    outDir: "../zaco/web/spa",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
});
