import { useEffect, useState } from 'react'
import type { Envelope } from '../types'
import { api } from '../api'

interface Props {
  env: Envelope
  run?: (fn: () => Promise<unknown>) => Promise<void>
}

// 12 columns x 8 rows LED Matrix Canvas / SVG component
function LedMatrix({ pixels, label, active = true, status = 'ONLINE' }: {
  pixels: boolean[][]
  label: string
  active?: boolean
  status?: string
}) {
  return (
    <div style={{
      background: '#0d1117',
      border: '2px solid #30363d',
      borderRadius: '8px',
      padding: '10px',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '8px',
      boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
      minWidth: '220px'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        width: '100%',
        alignItems: 'center',
        fontSize: '11px',
        fontWeight: 600,
        color: '#c9d1d9',
        borderBottom: '1px solid #21262d',
        paddingBottom: '4px'
      }}>
        <span>{label}</span>
        <span style={{
          color: active ? '#3fb950' : '#8b949e',
          display: 'flex',
          alignItems: 'center',
          gap: '4px'
        }}>
          <span style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: active ? '#2ea043' : '#484f58',
            boxShadow: active ? '0 0 6px #2ea043' : 'none'
          }} />
          {status}
        </span>
      </div>

      {/* 12x8 LED grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(12, 12px)',
        gridTemplateRows: 'repeat(8, 12px)',
        gap: '3px',
        background: '#05070a',
        padding: '6px',
        borderRadius: '4px',
        border: '1px solid #161b22'
      }}>
        {Array.from({ length: 8 }).map((_, r) =>
          Array.from({ length: 12 }).map((_, c) => {
            const on = pixels[r]?.[c] ?? false
            return (
              <div
                key={`${r}-${c}`}
                style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '2px',
                  background: on ? '#ff3b30' : '#1f1618',
                  boxShadow: on ? '0 0 5px #ff453a, 0 0 2px #ff6961' : 'none',
                  transition: 'background 0.08s ease'
                }}
              />
            )
          })
        )}
      </div>
      <div style={{ fontSize: '9px', color: '#8b949e', letterSpacing: '0.5px' }}>
        ARDUINO UNO R4 · 12×8 MATRIX
      </div>
    </div>
  )
}

export function HardwareConsoleWidget({ env, run }: Props) {
  const [phase, setPhase] = useState(0)
  const [localAirgap, setLocalAirgap] = useState<boolean>(false)

  // 10 Hz animation tick
  useEffect(() => {
    const timer = setInterval(() => {
      setPhase((p) => (p + 1) % 96)
    }, 100)
    return () => clearInterval(timer)
  }, [])

  // Sync airgap from env if available
  const airgapEngaged = localAirgap || !!env.incident?.airgap_engaged || !!env.state?.airgap_engaged

  // Node 1: Tank T-101 / HALL-A Level & Waves
  const tank = env.state.tanks['T-101'] ?? env.state.tanks['HALL-A'] ?? Object.values(env.state.tanks)[0]
  const tankVol = Number(tank?.volume ?? 600)
  const tankCap = Number(tank?.capacity ?? 1000)
  const tankFrac = Math.max(0, Math.min(1, tankVol / (tankCap || 1)))
  const fillRows = Math.round(tankFrac * 8)
  const surface = 8 - fillRows

  const tankPixels: boolean[][] = Array.from({ length: 8 }, () => Array(12).fill(false))
  for (let y = surface + 1; y < 8; y++) {
    for (let x = 0; x < 12; x++) {
      tankPixels[y][x] = ((x + phase + y * 2) % 11) !== 0
    }
  }
  if (surface >= 0 && surface < 8) {
    for (let x = 0; x < 12; x++) {
      const crest = (x + phase) % 6
      tankPixels[surface][x] = crest !== 0 && crest !== 5
    }
  }
  if (surface > 0) {
    const drop = Math.floor(phase / 2) % 12
    tankPixels[surface - 1][drop] = true
  }
  // High-High alert strobe
  if (tankFrac >= 0.95 && Math.floor(phase / 3) % 2 === 0) {
    for (let x = 0; x < 12; x++) {
      tankPixels[0][x] = true
      tankPixels[1][x] = true
    }
  }

  // Node 2: Pump P-201 / CHP-1 Impeller & States
  const pump = env.state.pumps['P-201'] ?? env.state.pumps['CHP-1'] ?? Object.values(env.state.pumps)[0]
  const isTripped = pump?.run_state === 'TRIPPED' || env.state.faults.some((f) => f.type === 'PUMP_TRIP' && f.active)
  const pumpWear = Number(pump?.health ?? pump?.eff_health ?? 1.0)
  const isWorn = pumpWear < 0.5
  const isRunning = pump?.run_state === 'RUNNING'

  const pumpPixels: boolean[][] = Array.from({ length: 8 }, () => Array(12).fill(false))

  if (isTripped) {
    // Solid high-visibility 'X'
    for (let y = 0; y < 8; y++) {
      if (2 + y < 12) pumpPixels[y][2 + y] = true
      if (9 - y >= 0 && 9 - y < 12) pumpPixels[y][9 - y] = true
    }
  } else if (!isRunning) {
    // Idle ring
    for (let x = 4; x <= 7; x++) {
      pumpPixels[2][x] = true
      pumpPixels[5][x] = true
    }
    pumpPixels[3][4] = true
    pumpPixels[4][4] = true
    pumpPixels[3][7] = true
    pumpPixels[4][7] = true
  } else if (isWorn && Math.floor(phase / 4) % 2 === 0) {
    // Alternating Caution Triangle
    pumpPixels[0][6] = true
    pumpPixels[1][5] = true; pumpPixels[1][7] = true
    pumpPixels[2][4] = true; pumpPixels[2][8] = true
    pumpPixels[3][3] = true; pumpPixels[3][9] = true
    pumpPixels[4][2] = true; pumpPixels[4][10] = true
    pumpPixels[5][1] = true; pumpPixels[5][11] = true
    for (let x = 0; x < 12; x++) pumpPixels[6][x] = true
    pumpPixels[2][6] = true
    pumpPixels[3][6] = true
    pumpPixels[5][6] = true
  } else {
    // Rotating Impeller Vane Animation (speed modulated by flow)
    const angleStep = Math.floor(phase * 1.5) % 8
    const cx = 5.5, cy = 3.5
    // Draw outer circle
    for (let deg = 0; deg < 8; deg++) {
      const a = ((deg + angleStep) * Math.PI) / 4
      const px = Math.round(cx + 3 * Math.cos(a))
      const py = Math.round(cy + 2.5 * Math.sin(a))
      if (px >= 0 && px < 12 && py >= 0 && py < 8) {
        pumpPixels[py][px] = true
      }
      // Inner cross vanes
      const inX = Math.round(cx + 1.5 * Math.cos(a))
      const inY = Math.round(cy + 1.2 * Math.sin(a))
      if (inX >= 0 && inX < 12 && inY >= 0 && inY < 8) {
        pumpPixels[inY][inX] = true
      }
    }
    pumpPixels[3][5] = true
    pumpPixels[3][6] = true
    pumpPixels[4][5] = true
    pumpPixels[4][6] = true
  }

  // Node 3: Output Stream & Cyber Air-Gap Padlock
  const outputPixels: boolean[][] = Array.from({ length: 8 }, () => Array(12).fill(false))

  if (airgapEngaged) {
    // HIGH-CONTRAST AIR-GAP PADLOCK ICON
    // Shackle arch (rows 0..2)
    outputPixels[0][4] = true; outputPixels[0][5] = true; outputPixels[0][6] = true; outputPixels[0][7] = true
    outputPixels[1][3] = true; outputPixels[1][8] = true
    outputPixels[2][3] = true; outputPixels[2][8] = true
    // Padlock body (rows 3..7, columns 2..9)
    for (let y = 3; y < 8; y++) {
      for (let x = 2; x <= 9; x++) {
        outputPixels[y][x] = true
      }
    }
    // Keyhole cutout (dark pixels in center)
    outputPixels[4][5] = false; outputPixels[4][6] = false
    outputPixels[5][5] = false; outputPixels[5][6] = false
    outputPixels[6][5] = false; outputPixels[6][6] = false
  } else {
    // Flowing water ripple stream across all 12 columns
    for (let y = 1; y < 7; y++) {
      for (let x = 0; x < 12; x++) {
        const flowWave = (x - phase * 2 + y * 3) % 7
        outputPixels[y][x] = flowWave === 0 || flowWave === 1
      }
    }
  }

  const handleToggleAirgap = async () => {
    const nextState = !airgapEngaged
    setLocalAirgap(nextState)
    try {
      await api.incidentAirgap(nextState, 'modulino_button_a')
    } catch {
      // dry-run / fallback handled cleanly
    }
  }

  const handleTripPump = async () => {
    if (run) {
      await run(async () => {
        if (isTripped) {
          const fault = env.state.faults.find((f) => f.type === 'PUMP_TRIP' && f.active)
          if (fault) await api.clearFault(fault.id)
        } else {
          await api.injectFault('PUMP_TRIP', pump?.role === 'duty' ? 'P-201' : 'P-203', { reason: 'Modulino Button B trip' })
        }
      })
    }
  }

  return (
    <div style={{
      background: 'var(--panel, #161b22)',
      borderRadius: '10px',
      padding: '16px',
      border: '1px solid var(--border, #30363d)',
      marginTop: '12px'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '14px',
        borderBottom: '1px solid #30363d',
        paddingBottom: '8px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '18px' }}>🖥️</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: '14px', color: '#f0f6fc' }}>
              Arduino Matrix HIL Console (3-Node Topology)
            </div>
            <div style={{ fontSize: '11px', color: '#8b949e' }}>
              10 Hz live hardware simulation bridge · Tank (Node 1) · Pump (Node 2) · Output &amp; Air-Gap (Node 3)
            </div>
          </div>
        </div>

        {/* Global Air-Gap Badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '4px 10px',
          borderRadius: '6px',
          background: airgapEngaged ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.15)',
          border: `1px solid ${airgapEngaged ? '#ef4444' : '#22c55e'}`
        }}>
          <span style={{ fontSize: '14px' }}>{airgapEngaged ? '🔒' : '🌐'}</span>
          <span style={{
            fontSize: '11px',
            fontWeight: 700,
            color: airgapEngaged ? '#ef4444' : '#22c55e'
          }}>
            {airgapEngaged ? 'AIR-GAP ENGAGED' : 'WAN EGRESS ONLINE'}
          </span>
        </div>
      </div>

      {/* 3 Virtual LED Matrix Displays */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
        gap: '16px'
      }}>
        {/* Node 1: Tank */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center' }}>
          <LedMatrix
            pixels={tankPixels}
            label="NODE 1 · TANK (T-101)"
            status={tankFrac >= 0.95 ? 'HIGH-HIGH' : 'NORMAL'}
          />
          <div style={{ fontSize: '11px', color: '#8b949e', textAlign: 'center', width: '100%' }}>
            Level: <strong style={{ color: '#58a6ff' }}>{tankVol.toFixed(0)}</strong> / {tankCap} bbl ({(tankFrac * 100).toFixed(0)}%)
          </div>
        </div>

        {/* Node 2: Pump */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center' }}>
          <LedMatrix
            pixels={pumpPixels}
            label="NODE 2 · PUMP (P-201)"
            status={isTripped ? 'TRIPPED' : isWorn ? 'DEGRADED' : isRunning ? 'RUNNING' : 'STOPPED'}
          />
          <div style={{ display: 'flex', gap: '6px', width: '100%', justifyContent: 'center' }}>
            <button
              style={{
                fontSize: '11px',
                padding: '4px 10px',
                borderRadius: '4px',
                background: isTripped ? '#238636' : '#da3633',
                color: '#fff',
                border: 'none',
                cursor: 'pointer'
              }}
              onClick={handleTripPump}
            >
              {isTripped ? 'Reset Trip (Btn C)' : 'Trip Pump (Btn B)'}
            </button>
          </div>
        </div>

        {/* Node 3: Output Stream & Security */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center' }}>
          <LedMatrix
            pixels={outputPixels}
            label="NODE 3 · OUTPUT &amp; AIR-GAP"
            status={airgapEngaged ? 'AIR-GAPPED' : 'STREAMING'}
          />
          <div style={{ display: 'flex', gap: '6px', width: '100%', justifyContent: 'center' }}>
            <button
              style={{
                fontSize: '11px',
                padding: '4px 10px',
                borderRadius: '4px',
                background: airgapEngaged ? '#238636' : '#b91c1c',
                color: '#fff',
                fontWeight: 600,
                border: 'none',
                cursor: 'pointer',
                boxShadow: airgapEngaged ? '0 0 8px rgba(35,134,54,0.4)' : '0 0 8px rgba(185,28,28,0.4)'
              }}
              onClick={handleToggleAirgap}
            >
              {airgapEngaged ? '🔓 Release Air-Gap' : '🔒 Modulino Btn A: Killswitch'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
