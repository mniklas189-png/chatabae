import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'serve' ? '/' : (process.env.VITE_BASE_PATH || '/chatabae/'),
  server: { port: 5173 },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts', css: false },
}));
