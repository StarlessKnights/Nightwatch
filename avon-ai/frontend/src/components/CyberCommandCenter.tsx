import React, { useState, useEffect } from 'react'
import type { Envelope } from '../types'
import { api } from '../api'
import { HardwareConsoleWidget } from './HardwareConsoleWidget'

interface Props {
  env: Envelope
  run?: (fn: () => Promise<unknown>) => Promise<void>
  onClose?: () => void
}

interface CommsMessage {
  id: string
  timestamp: string
  sender: string
  role: string
  role_badge: string
  message: string
}

interface ScopeItem {
  status: string
  notes?: string
  last_updated?: string
  actor?: string
}

const NIST_STAGES = ['DETECTION', 'CONTAINMENT', 'ERADICATION', 'RECOVERY']

export function CyberCommandCenter({ env, run, onClose }: Props) {
  const [airgap, setAirgap] = useState<boolean>(
    env.incident?.airgap_engaged ?? env.state?.airgap_engaged ?? false
  )
  const [stage, setStage] = useState<string>(env.incident?.stage ?? 'DETECTION')
  const [level, setLevel] = useState<string>(env.incident?.level ?? 'HIGH')
  const [scope, setScope] = useState<Record<string, ScopeItem>>({
    COMPUTE_POD_A: { status: 'HEALTHY', notes: 'Primary compute cluster' },
    STORAGE_SAN: { status: 'DEGRADED', notes: 'Unusual exfiltration pattern flagged' },
    CHILLED_WATER_LOOP: { status: 'HEALTHY', notes: 'Thermal cooling telemetry active' },
    EXTERNAL_WAN: { status: 'HEALTHY', notes: 'Upstream gateway egress' },
  })
  const [comms, setComms] = useState<CommsMessage[]>([
    {
      id: 'init-1',
      timestamp: new Date().toLocaleTimeString(),
      sender: 'Incident Commander',
      role: 'incident_commander',
      role_badge: 'INCIDENT-COMMAND',
      message: 'Winstead Cyber Incident Command initiated. Monitoring telemetry and WAN egress.',
    },
  ])
  const [chatInput, setChatInput] = useState('')
  const [senderName, setSenderName] = useState('Officer J. Vance')
  const [senderRole, setSenderRole] = useState('incident_commander')
  const [isUpdating, setIsUpdating] = useState(false)

  // Polling / fetching incident status and comms
  useEffect(() => {
    let mounted = true
    const fetchData = async () => {
      try {
        const [statusData, scopeData, commsData] = await Promise.all([
          api.incidentStatus().catch(() => null),
          api.incidentScope().catch(() => null),
          api.incidentComms().catch(() => null),
        ])
        if (!mounted) return
        if (statusData && typeof statusData === 'object') {
          if (typeof statusData.airgap_engaged === 'boolean') setAirgap(statusData.airgap_engaged)
          if (statusData.stage) setStage(statusData.stage)
          if (statusData.level) setLevel(statusData.level)
        }
        if (scopeData && typeof scopeData === 'object') {
          setScope(scopeData as Record<string, ScopeItem>)
        }
        if (Array.isArray(commsData) && commsData.length > 0) {
          setComms(commsData as CommsMessage[])
        }
      } catch {
        // Fallback gracefully
      }
    }

    fetchData()
    const timer = setInterval(fetchData, 2000)
    return () => {
      mounted = false
      clearInterval(timer)
    }
  }, [])

  const handleToggleAirgap = async () => {
    setIsUpdating(true)
    const nextState = !airgap
    setAirgap(nextState)
    try {
      await api.incidentAirgap(nextState, 'cyber_command_center')
      const statusData = await api.incidentStatus()
      if (statusData?.airgap_engaged !== undefined) {
        setAirgap(statusData.airgap_engaged)
      }
    } catch (e) {
      console.error('Airgap toggle error', e)
    } finally {
      setIsUpdating(false)
    }
  }

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!chatInput.trim()) return

    const newMsg: CommsMessage = {
      id: `local-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      sender: senderName,
      role: senderRole,
      role_badge: senderRole === 'admin' ? 'ADMIN-AUTH' : senderRole === 'operator' ? 'OPS-STATION' : 'INCIDENT-COMMAND',
      message: chatInput.trim(),
    }
    setComms((prev) => [...prev, newMsg])
    const textToSend = chatInput.trim()
    setChatInput('')

    try {
      await api.postComms(textToSend, senderName, senderRole)
    } catch {
      // Local message remains visible
    }
  }

  const handleUpdateAssetStatus = async (asset: string, newStatus: string) => {
    setScope((prev) => ({
      ...prev,
      [asset]: { ...prev[asset], status: newStatus },
    }))
    try {
      await api.updateScope(asset, newStatus, `Manual update by ${senderName}`, senderName)
    } catch {
      // Fallback
    }
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
      color: '#e6edf3',
      fontFamily: 'Inter, system-ui, sans-serif'
    }}>
      {/* Top Banner: Winstead PC Command Header */}
      <div style={{
        background: 'linear-gradient(135deg, #161b22 0%, #0d1117 100%)',
        padding: '16px 20px',
        borderRadius: '10px',
        border: '1px solid #30363d',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '20px' }}>🛡️</span>
            <span style={{ fontSize: '18px', fontWeight: 800, letterSpacing: '0.5px', color: '#f0f6fc' }}>
              WINSTEAD CYBER INCIDENT COMMAND
            </span>
            <span style={{
              fontSize: '10px',
              padding: '2px 8px',
              borderRadius: '12px',
              background: '#238636',
              color: '#ffffff',
              fontWeight: 700
            }}>
              NIST SP 800-61
            </span>
          </div>
          <div style={{ fontSize: '12px', color: '#8b949e', marginTop: '4px' }}>
            Mission-Critical Datacenter Security &amp; Hardware Air-Gap Isolation Console
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            fontSize: '11px',
            color: '#8b949e',
            background: '#21262d',
            padding: '4px 10px',
            borderRadius: '6px'
          }}>
            Incident Level: <strong style={{ color: level === 'CRITICAL' ? '#f85149' : '#d29922' }}>{level}</strong>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              style={{
                background: '#21262d',
                border: '1px solid #30363d',
                color: '#c9d1d9',
                padding: '4px 10px',
                borderRadius: '6px',
                cursor: 'pointer'
              }}
            >
              ✕ Close
            </button>
          )}
        </div>
      </div>

      {/* NIST SP 800-61 Lifecycle Stage Indicator */}
      <div style={{
        display: 'flex',
        gap: '8px',
        alignItems: 'center',
        background: '#0d1117',
        padding: '8px 12px',
        borderRadius: '8px',
        border: '1px solid #21262d',
        overflowX: 'auto'
      }}>
        <span style={{ fontSize: '11px', fontWeight: 700, color: '#8b949e', marginRight: '6px' }}>
          LIFECYCLE:
        </span>
        {NIST_STAGES.map((s, idx) => {
          const isActive = s === stage
          return (
            <React.Fragment key={s}>
              <div style={{
                padding: '4px 12px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 700,
                background: isActive ? '#1f6feb' : '#161b22',
                color: isActive ? '#ffffff' : '#8b949e',
                border: `1px solid ${isActive ? '#388bfd' : '#30363d'}`,
                boxShadow: isActive ? '0 0 10px rgba(31,111,235,0.4)' : 'none'
              }}>
                {idx + 1}. {s}
              </div>
              {idx < NIST_STAGES.length - 1 && (
                <span style={{ color: '#484f58', fontSize: '12px' }}>→</span>
              )}
            </React.Fragment>
          )
        })}
      </div>

      {/* Winstead #1: Secure & Isolated (Air-Gap Status Callout) */}
      <div style={{
        background: airgap ? 'rgba(239, 68, 68, 0.12)' : 'rgba(34, 197, 94, 0.08)',
        border: `2px solid ${airgap ? '#ef4444' : '#22c55e'}`,
        borderRadius: '10px',
        padding: '16px 20px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            fontSize: '32px',
            background: airgap ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.2)',
            borderRadius: '50%',
            width: '56px',
            height: '56px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: airgap ? '0 0 16px rgba(239,68,68,0.4)' : 'none'
          }}>
            {airgap ? '🔒' : '🌐'}
          </div>
          <div>
            <div style={{
              fontSize: '16px',
              fontWeight: 800,
              color: airgap ? '#f85149' : '#3fb950',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              {airgap ? 'PHYSICAL AIR-GAP SEVERED' : 'EXTERNAL WAN EGRESS ONLINE'}
              <span style={{
                fontSize: '10px',
                padding: '2px 6px',
                borderRadius: '4px',
                background: airgap ? '#b91c1c' : '#238636',
                color: '#fff'
              }}>
                {airgap ? 'QUARANTINE ENFORCED' : 'NORMAL LINK'}
              </span>
            </div>
            <div style={{ fontSize: '12px', color: '#8b949e', marginTop: '2px' }}>
              {airgap
                ? 'Modulino Button A / Winstead trigger severed all outbound network egress. Local Arduino matrices display padlock security icon.'
                : 'All external telemetry and supervisory control networks are connected. Egress is active.'}
            </div>
          </div>
        </div>

        <button
          onClick={handleToggleAirgap}
          disabled={isUpdating}
          style={{
            padding: '10px 20px',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 700,
            background: airgap ? '#238636' : '#da3633',
            color: '#ffffff',
            border: 'none',
            cursor: 'pointer',
            boxShadow: airgap ? '0 0 12px rgba(35,134,54,0.4)' : '0 0 12px rgba(218,54,51,0.4)',
            transition: 'all 0.15s ease'
          }}
        >
          {airgap ? '🔓 De-escalate & Reconnect Network' : '🔒 Engage Hardware Air-Gap Killswitch'}
        </button>
      </div>

      {/* Embedded Hardware Console (3 Arduino LED Matrix Displays) */}
      <HardwareConsoleWidget env={env} run={run} />

      {/* Two-Column Grid: Compromised Scope Definitions & Out-of-Band Incident Comms */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: '16px'
      }}>
        {/* Winstead #4: Compromised Scope Definitions */}
        <div style={{
          background: '#161b22',
          border: '1px solid #30363d',
          borderRadius: '10px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderBottom: '1px solid #21262d',
            paddingBottom: '8px'
          }}>
            <div style={{ fontWeight: 700, fontSize: '13px', color: '#f0f6fc' }}>
              Scope &amp; Asset Compromise Registry
            </div>
            <span style={{ fontSize: '10px', color: '#8b949e' }}>Winstead Requirement #4</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {Object.entries(scope).map(([asset, item]) => {
              const status = item.status
              const isCompromised = status === 'LOCKED_RANSOMWARE' || status === 'DATA_EXFILTRATED'
              const isDegraded = status === 'DEGRADED'
              const badgeCol = isCompromised ? '#f85149' : isDegraded ? '#d29922' : '#3fb950'

              return (
                <div key={asset} style={{
                  background: '#0d1117',
                  border: `1px solid ${isCompromised ? '#da3633' : '#30363d'}`,
                  borderRadius: '6px',
                  padding: '10px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '12px', color: '#f0f6fc' }}>
                      {asset}
                    </div>
                    {item.notes && (
                      <div style={{ fontSize: '11px', color: '#8b949e', marginTop: '2px' }}>
                        {item.notes}
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <select
                      value={status}
                      onChange={(e) => handleUpdateAssetStatus(asset, e.target.value)}
                      style={{
                        background: '#161b22',
                        border: `1px solid ${badgeCol}`,
                        color: badgeCol,
                        fontSize: '11px',
                        fontWeight: 700,
                        padding: '3px 6px',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      <option value="HEALTHY">HEALTHY</option>
                      <option value="DEGRADED">DEGRADED</option>
                      <option value="LOCKED_RANSOMWARE">LOCKED RANSOMWARE</option>
                      <option value="DATA_EXFILTRATED">EXFILTRATED</option>
                    </select>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Winstead #5: Out-of-Band Real-Time Incident Comms Feed */}
        <div style={{
          background: '#161b22',
          border: '1px solid #30363d',
          borderRadius: '10px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderBottom: '1px solid #21262d',
            paddingBottom: '8px'
          }}>
            <div style={{ fontWeight: 700, fontSize: '13px', color: '#f0f6fc' }}>
              Out-of-Band Incident Comms Feed
            </div>
            <span style={{ fontSize: '10px', color: '#8b949e' }}>Winstead Requirement #5</span>
          </div>

          {/* Messages list */}
          <div style={{
            background: '#0d1117',
            border: '1px solid #21262d',
            borderRadius: '6px',
            padding: '10px',
            height: '180px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px'
          }}>
            {comms.map((m) => (
              <div key={m.id} style={{ fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{
                    fontSize: '9px',
                    padding: '1px 5px',
                    borderRadius: '4px',
                    background: m.role_badge === 'INCIDENT-COMMAND' ? '#1f6feb' : m.role_badge === 'ADMIN-AUTH' ? '#8957e5' : '#238636',
                    color: '#ffffff',
                    fontWeight: 700
                  }}>
                    {m.role_badge || m.role}
                  </span>
                  <strong style={{ color: '#c9d1d9' }}>{m.sender}</strong>
                  <span style={{ color: '#6e7681', fontSize: '10px', marginLeft: 'auto' }}>{m.timestamp}</span>
                </div>
                <div style={{ color: '#e6edf3', paddingLeft: '4px' }}>
                  {m.message}
                </div>
              </div>
            ))}
          </div>

          {/* Post out-of-band input form */}
          <form onSubmit={handleSendMessage} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                placeholder="Responder Name"
                value={senderName}
                onChange={(e) => setSenderName(e.target.value)}
                style={{
                  width: '130px',
                  background: '#0d1117',
                  border: '1px solid #30363d',
                  borderRadius: '6px',
                  padding: '4px 8px',
                  color: '#f0f6fc',
                  fontSize: '11px'
                }}
              />
              <select
                value={senderRole}
                onChange={(e) => setSenderRole(e.target.value)}
                style={{
                  background: '#0d1117',
                  border: '1px solid #30363d',
                  borderRadius: '6px',
                  padding: '4px 8px',
                  color: '#f0f6fc',
                  fontSize: '11px',
                  cursor: 'pointer'
                }}
              >
                <option value="incident_commander">Incident Commander</option>
                <option value="admin">Admin</option>
                <option value="operator">Operator</option>
              </select>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                placeholder="Post incident directive (out-of-band)..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                style={{
                  flex: 1,
                  background: '#0d1117',
                  border: '1px solid #30363d',
                  borderRadius: '6px',
                  padding: '6px 10px',
                  color: '#f0f6fc',
                  fontSize: '12px'
                }}
              />
              <button
                type="submit"
                style={{
                  background: '#1f6feb',
                  color: '#fff',
                  border: 'none',
                  padding: '6px 14px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Send
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
