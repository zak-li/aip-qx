import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  publicDir: 'public',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          chart:  ['chart.js'],
          marked: ['marked', 'dompurify'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api':    { target: 'http://10.10.10.150:8000', changeOrigin: true },
      '/health': { target: 'http://10.10.10.150:8000', changeOrigin: true },
    },
  },
});
