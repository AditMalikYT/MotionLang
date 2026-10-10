import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The studio is a static Vite app. `composition.json` (produced by
// `motion <script>.hmg --studio`) lives in `public/` and is fetched at runtime.
export default defineConfig({
  plugins: [react()],
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
