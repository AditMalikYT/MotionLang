import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { motionApi } from "./vite-plugin-motion-api";

// The studio is a static Vite app. `composition.json` (produced by
// `motion <script>.hmg --studio`) lives in `public/` and is fetched at runtime.
// `motionApi()` adds the dev-server backend (POST /api/composition, /api/render)
// so the editor can sync timelines and trigger Remotion renders from the UI.
export default defineConfig({
  plugins: [react(), motionApi()],
  server: {
    port: 5173,
    host: true,
    fs: {
      // Allow reading media that the compiler copied next to the app.
      allow: [".."],
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
