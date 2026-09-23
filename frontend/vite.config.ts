import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'FRUKTAI_');
  const api = env.FRUKTAI_API_PROXY ?? 'http://127.0.0.1:8000';
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': api,
        '/health': api,
      },
    },
  };
});
