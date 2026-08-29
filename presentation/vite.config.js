import { defineConfig } from 'vite';

// Relative base so `dist/` opens from file:// on a laptop with no server.
export default defineConfig({
    base: './',
    build: { outDir: 'dist', emptyOutDir: true },
    server: { port: 5180, open: true },
});
