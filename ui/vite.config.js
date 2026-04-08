import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/detect': 'http://127.0.0.1:8000',
      '/match': 'http://127.0.0.1:8000',
      '/export': 'http://127.0.0.1:8000',
      '/thumbnails': 'http://127.0.0.1:8000',
      '/browse': 'http://127.0.0.1:8000',
      '/video': 'http://127.0.0.1:8000',
    },
  },
})
