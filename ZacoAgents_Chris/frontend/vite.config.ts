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
  // Assets are requested under /app/, which is where FastAPI mounts the build.
  base: "/app/",
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
      // The stylesheet and the existing interface, so both are reachable from the dev server.
      "/static": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
});
