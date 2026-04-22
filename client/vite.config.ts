import playbotComponentInjector from '../plugins/vite-plugin-playbot';
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue(), playbotComponentInjector()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8004',
        ws: true,
      },
    },
  },
})
