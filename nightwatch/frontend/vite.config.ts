import react from '@vitejs/plugin-react'
import { defineConfig, type ProxyOptions } from 'vite'
import http from 'node:http'

const CANDIDATE_PORTS = Array.from(new Set([
  process.env.BACKEND_PORT,
  '8008',
  '8000',
  '8080',
  '8001',
])).filter(Boolean) as string[]

let activePort = process.env.BACKEND_PORT || '8008'
let apiProxyOpts: ProxyOptions | null = null
let wsProxyOpts: ProxyOptions | null = null

function probePort(port: string): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/api/network`, { timeout: 350 }, (res) => {
      resolve(res.statusCode !== undefined && res.statusCode < 500)
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => { req.destroy(); resolve(false) })
  })
}

async function findActivePort(): Promise<string> {
  for (const port of CANDIDATE_PORTS) {
    if (await probePort(port)) {
      if (activePort !== port) {
        activePort = port
        if (apiProxyOpts) apiProxyOpts.target = `http://127.0.0.1:${port}`
        if (wsProxyOpts) wsProxyOpts.target = `ws://127.0.0.1:${port}`
      }
      return port
    }
  }
  return activePort
}

// Initial probe
void findActivePort()

// Background probe every 3 seconds to auto-follow backend port changes or restarts
const probeTimer = setInterval(() => { void findActivePort() }, 3000)
if (probeTimer && typeof probeTimer === 'object' && 'unref' in probeTimer) {
  probeTimer.unref()
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${activePort}`,
        changeOrigin: true,
        configure: (proxy, options) => {
          apiProxyOpts = options
          proxy.on('proxyReq', (_proxyReq, _req, _res, opts) => {
            opts.target = `http://127.0.0.1:${activePort}`
          })
          proxy.on('error', (_err, _req, res) => {
            void findActivePort()
            if (res && 'writeHead' in res && !res.headersSent) {
              res.writeHead(503, { 'Content-Type': 'application/json' })
              res.end(JSON.stringify({ error: 'Connecting to backend...', activePort }))
            }
          })
        },
      },
      '/ws': {
        target: `ws://127.0.0.1:${activePort}`,
        ws: true,
        changeOrigin: true,
        configure: (proxy, options) => {
          wsProxyOpts = options
          proxy.on('proxyReqWs', (_proxyReq, _req, _socket, opts) => {
            opts.target = `ws://127.0.0.1:${activePort}`
          })
          proxy.on('error', () => {
            void findActivePort()
          })
        },
      },
    },
  },
})
