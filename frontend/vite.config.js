import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // API Gateway 的 CORS 只允許 http://localhost:5173，換 port 會被瀏覽器擋下
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/setupTests.js',
    restoreMocks: true,
    unstubGlobals: true,
  },
})
