import { defineConfig } from "vite";
import { sveltekit } from "@sveltejs/kit/vite";

const host = process.env.TAURI_DEV_HOST;

// Where `/api` requests are forwarded. Natively and in Docker this is the
// meeting service on loopback: in Docker the web container shares the API
// container's network namespace, so 127.0.0.1 reaches it there too.
const apiTarget = process.env.MOM_API_URL || "http://127.0.0.1:8000";

// https://vite.dev/config/
export default defineConfig(async () => ({
  plugins: [sveltekit()],

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
      // File-change events do not cross a Windows bind mount into a Linux
      // container, so the Docker setup opts into polling. Native runs keep
      // native file watching.
      usePolling: process.env.VITE_USE_POLLING === "1",
    },
    // Same-origin proxy to the local meeting service, so the browser never
    // makes a cross-origin call (the API has no CORS configuration).
    //
    // Security boundary: the API's synthetic-dev check trusts the socket peer,
    // and every proxied request arrives from 127.0.0.1. So anything that can
    // reach this dev server is treated as local. Never expose it beyond
    // loopback. (A client-supplied X-Forwarded-For is passed through and
    // uvicorn honours it from a loopback peer; that can only make a request
    // look non-local and be denied, not the reverse.) Leave `xfwd` off: it
    // would replace the loopback peer with the proxy's view of the client.
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: false,
      },
    },
  },
}));
