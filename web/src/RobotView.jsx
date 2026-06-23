import { useState, useEffect, useCallback } from 'react'

const GESTURE_NAMES = {
  0: 'Reposo', 1: 'Parpadeo Der', 2: 'Parpadeo Izq', 3: 'Parpadeo Doble',
  4: 'Ojos Arriba', 5: 'Ojos Abajo', 6: 'Cejas Arriba', 7: 'Cejas Abajo',
  8: 'Enojo', 9: 'Sorpresa', 10: 'Sonrisa', 11: 'Mover Labio',
  12: 'Mejillas', 13: 'Abrir Mandibula', 14: 'Hablar',
}

const PHASE_NAMES = {
  0: 'Inicio', 1: 'Quieto', 2: 'Mira',
  3: 'Senala', 4: 'Falsa Creencia', 5: 'Preguntas', 6: 'Libre',
}

const PHASE_COLORS = {
  0: '#6366f1', 1: '#6b7280', 2: '#0ea5e9',
  3: '#f59e0b', 4: '#10b981', 5: '#8b5cf6', 6: '#ef4444',
}

export default function RobotView({ phase, speech, gesture, onResponse, onInitiative, waitingForResponse }) {
  const [responseLat, setResponseLat] = useState(null)
  const [responseStart, setResponseStart] = useState(null)
  const [flash, setFlash] = useState(null)
  const [initCount, setInitCount] = useState(0)

  useEffect(() => {
    if (waitingForResponse && !responseStart) {
      setResponseStart(Date.now())
      setResponseLat(null)
    }
    if (!waitingForResponse) {
      setResponseStart(null)
    }
  }, [waitingForResponse])

  const handleResponse = useCallback((value) => {
    const lat = responseStart ? Date.now() - responseStart : 0
    setResponseLat(lat)
    if (onResponse) onResponse(value, lat)
    setFlash(value ? 'correcto' : 'incorrecto')
    setTimeout(() => setFlash(null), 600)
  }, [responseStart, onResponse])

  const handleInitiative = useCallback(() => {
    setInitCount(c => c + 1)
    if (onInitiative) onInitiative()
    setFlash('iniciativa')
    setTimeout(() => setFlash(null), 600)
  }, [onInitiative])

  useEffect(() => {
    const onKey = (e) => {
      const key = e.key.toLowerCase()
      if (key === 'c' && waitingForResponse) {
        e.preventDefault(); handleResponse(true)
      } else if (key === 'x' && waitingForResponse) {
        e.preventDefault(); handleResponse(false)
      } else if (key === 'i') {
        e.preventDefault(); handleInitiative()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [waitingForResponse, handleResponse, handleInitiative])

  const pName = PHASE_NAMES[phase] ?? `Fase ${phase}`
  const pColor = PHASE_COLORS[phase] ?? '#6366f1'
  const gName = GESTURE_NAMES[gesture] ?? '—'
  const totalPhases = 7
  const pct = totalPhases > 0 ? ((phase + 1) / totalPhases * 100).toFixed(0) : 0

  return (
    <div className="robot-view">
      <div className="rv-phase-bar">
        <div className="rv-phase-track">
          <div className="rv-phase-fill" style={{ width: `${pct}%`, background: pColor }} />
        </div>
        <span className="rv-phase-label" style={{ color: pColor }}>{pName}</span>
      </div>

      <div className="rv-robot-area">
        <div className="rv-robot-icon" style={{ borderColor: pColor }}>
          <i className="fa-solid fa-robot" />
          <div className="rv-gesture-tag">{gName}</div>
        </div>

        <div className="rv-speech-bubble" style={{ borderColor: pColor }}>
          {speech
            ? <><i className="fa-solid fa-quote-left rv-quote" />{speech}</>
            : <span className="rv-waiting">Esperando...</span>
          }
        </div>
      </div>

      {waitingForResponse && (
        <div className="rv-response-area">
          <p className="rv-response-hint">
            <i className="fa-solid fa-hand-pointer" /> Registre la respuesta del nino:
          </p>
          <div className="rv-response-btns">
            <button className="rv-btn rv-btn-correct" onClick={() => handleResponse(true)}>
              <i className="fa-solid fa-check" /> Correcto <kbd>C</kbd>
            </button>
            <button className="rv-btn rv-btn-incorrect" onClick={() => handleResponse(false)}>
              <i className="fa-solid fa-xmark" /> Incorrecto <kbd>X</kbd>
            </button>
          </div>
          {responseLat != null && (
            <p className="rv-response-lat">TR: {responseLat}ms</p>
          )}
        </div>
      )}

      <div className="rv-extra-row">
        <button className="rv-btn rv-btn-initiative" onClick={handleInitiative}>
          <i className="fa-solid fa-bolt" /> Iniciativa <kbd>I</kbd>
        </button>
        {initCount > 0 && (
          <span className="rv-init-badge">{initCount} registrada{initCount !== 1 ? 's' : ''}</span>
        )}
      </div>

      {flash && (
        <div className={`rv-flash rv-flash-${flash}`}>
          {flash === 'correcto' && '✓ Correcto'}
          {flash === 'incorrecto' && '✗ Incorrecto'}
          {flash === 'iniciativa' && '⚡ Iniciativa!'}
        </div>
      )}

      <div className="rv-hint-bar">
        {waitingForResponse && <span><kbd>C</kbd> Correcto</span>}
        {waitingForResponse && <span><kbd>X</kbd> Incorrecto</span>}
        <span><kbd>I</kbd> Iniciativa</span>
      </div>

      <div className="rv-phase-dots">
        {[0, 1, 2, 3, 4, 5, 6].map(p => (
          <div key={p} className={`rv-dot${p <= phase ? ' rv-dot-active' : ''}`}
               style={p <= phase ? { background: PHASE_COLORS[p] } : {}} />
        ))}
      </div>
    </div>
  )
}
