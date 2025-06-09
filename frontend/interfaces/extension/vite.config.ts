import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "dist",
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
      },
      output: {
        entryFileNames: "js/[name].js",
        chunkFileNames: "js/[name].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith(".css")) {
            return "css/[name][extname]";
          }
          return "assets/[name][extname]";
        },
      },
    },
    // Ensure compatibility with Chrome extension environment
    target: "es2015",
    minify: "esbuild",
  },
  define: {
    // Required for React in production
    "process.env.NODE_ENV": '"production"',
  },
  // Configure for extension environment
  base: "./",
  server: {
    hmr: false, // Disable HMR for extension development
  },
});
