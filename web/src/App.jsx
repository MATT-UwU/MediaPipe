import { useState, useEffect, useRef, useCallback } from 'react'
import Dashboard from './Dashboard.jsx'
import RobotView from './RobotView.jsx'
import Module5View from './Module5View.jsx'

const WS          = `ws://${location.host}/ws`
const BACKEND_URL = `http://localhost:8000`

const EMOTION_META = {
  feliz:   { icon: 'fa-face-smile',    color: '#10b981', label: 'Feliz'   },
  asombro: { icon: 'fa-face-surprise', color: '#8b5cf6', label: 'Asombro' },
  miedo:   { icon: 'fa-face-grimace',  color: '#3b82f6', label: 'Miedo'   },
  enojo:   { icon: 'fa-face-angry',    color: '#ef4444', label: 'Enojo'   },
  triste:  { icon: 'fa-face-sad-tear', color: '#6b7280', label: 'Triste'  },
  neutral: { icon: 'fa-face-meh',      color: '#94a3b8', label: 'Neutral' },
}

const GESTURE_NAMES = {
  0:'Reposo', 1:'Parpadeo Der', 2:'Parpadeo Izq', 3:'Parpadeo Doble',
  4:'Ojos Arriba', 5:'Ojos Abajo', 6:'Cejas Arriba', 7:'Cejas Abajo',
  8:'Enojo', 9:'Sorpresa', 10:'Sonrisa', 11:'Mover Labio',
  12:'Mejillas', 13:'Abrir Mandibula', 14:'Hablar',
}

const GESTURE_HINTS = [
  ['fa-face-smile',          'Sonrisa',          'Sonrie ampliamente'],
  ['fa-face-surprise',       'Sorpresa',         'Abre boca y cejas'],
  ['fa-face-angry',          'Enojo',            'Frunce cejas, presiona labios'],
  ['fa-face-wink',           'Guino derecho',    'Cierra el ojo derecho'],
  ['fa-face-wink',           'Guino izquierdo',  'Cierra el ojo izquierdo'],
  ['fa-face-laugh-squint',   'Parpadeo doble',   'Cierra ambos ojos fuerte'],
  ['fa-arrows-up-to-line',   'Cejas arriba',     'Levanta las cejas'],
  ['fa-arrows-down-to-line', 'Cejas abajo',      'Baja las cejas'],
  ['fa-comments',            'Hablar',           'Habla normalmente'],
  ['fa-face-surprise',       'Mandibula',        'Abre mucho la boca'],
]

function Icon({ name, className }) {
  return <i className={`fa-solid ${name}${className ? ' ' + className : ''}`} />
}

function StatusBadge({ ok, icon, label }) {
  return (
    <div className={`status-badge ${ok ? 'badge-ok' : 'badge-off'}`}>
      <span className={`badge-dot${ok ? ' pulse-green' : ''}`} />
      <Icon name={icon} />
      <span>{label}</span>
    </div>
  )
}

function SectionTitle({ icon, children, count }) {
  return (
    <div className="section-header">
      <div className="section-title-row">
        {icon && <Icon name={icon} className="sec-icon" />}
        <h3>{children}</h3>
      </div>
      {count != null && <span className="count-pill">{count}</span>}
    </div>
  )
}

function EventLog({ logs }) {
  const containerRef = useRef(null)
  const pinnedRef    = useRef(true)   // true = seguir al fondo automáticamente

  const onScroll = () => {
    const el = containerRef.current
    if (!el) return
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
  }

  useEffect(() => {
    if (!pinnedRef.current) return
    const el = containerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [logs])

  return (
    <div className="event-log" ref={containerRef} onScroll={onScroll}>
      {logs.length === 0
        ? (
          <div className="log-empty">
            <Icon name="fa-circle-dot" className="log-empty-icon" />
            <p>Esperando eventos...</p>
          </div>
        )
        : logs.map((l, i) => (
          <div key={i} className={`log-line${
            l.includes('->') ? ' log-gesture'
            : l.includes('Objeto:') || l.includes('Emocion:') ? ' log-detect'
            : l.includes('ERROR') ? ' log-error' : ''
          }`}>
            <Icon name="fa-chevron-right" className="log-arrow" />
            <span>{l}</span>
          </div>
        ))
      }
    </div>
  )
}

function GestureFlash({ gesture }) {
  const [visible, setVisible] = useState(false)
  const [current, setCurrent] = useState(null)
  useEffect(() => {
    if (!gesture) return
    setCurrent(gesture)
    setVisible(true)
    const t = setTimeout(() => setVisible(false), 3000)
    return () => clearTimeout(t)
  }, [gesture])
  if (!current) return null
  const name = GESTURE_NAMES[current.gesture_id] ?? current.name ?? `#${current.gesture_id}`
  return (
    <div className={`gesture-flash${visible ? ' flash-visible' : ' flash-hidden'}`}>
      <div className="flash-robot-icon"><Icon name="fa-robot" /></div>
      <div className="flash-content">
        <span className="flash-label">Robot ejecuto</span>
        <strong className="flash-name">{name}</strong>
      </div>
      <div className="flash-progress" />
    </div>
  )
}

function CameraStream({ mid, startKey }) {
  const [streamState, setStreamState] = useState('loading')
  const imgRef = useRef(null)

  useEffect(() => {
    setStreamState('loading')
    // Comprobar si llegan frames reales (naturalWidth > 0 después del primer frame)
    const t = setInterval(() => {
      const el = imgRef.current
      if (el && el.naturalWidth > 0) { setStreamState('ok'); clearInterval(t) }
    }, 400)
    return () => clearInterval(t)
  }, [mid, startKey])   // startKey cambia en cada inicio → reconexión forzada

  // URL con ?_=startKey para que el browser reconecte en vez de reusar la conexión vieja
  const src = `${BACKEND_URL}/stream/${mid}?_=${startKey}`

  return (
    <div className={`stream-wrap${streamState === 'ok' ? ' stream-active' : ''}`}>
      {streamState === 'ok' && (
        <div className="live-badge">
          <span className="live-dot" />EN VIVO
        </div>
      )}
      {streamState === 'loading' && (
        <div className="stream-overlay">
          <div className="stream-spinner" />
          <p>Iniciando camara</p>
          <small>Cargando modelo de IA...</small>
        </div>
      )}
      {streamState === 'error' && (
        <div className="stream-overlay stream-overlay-error">
          <Icon name="fa-video-slash" className="stream-err-icon" />
          <p>Sin senal de camara</p>
        </div>
      )}
      <img
        ref={imgRef}
        src={src}
        className={`stream-img${streamState === 'ok' ? ' stream-visible' : ''}`}
        onError={() => setStreamState('error')}
        alt="Camara en vivo"
      />
    </div>
  )
}

function DetectionPanel({ detection }) {
  const meta = EMOTION_META[detection?.emotion] ?? EMOTION_META.neutral
  if (!detection?.object) return (
    <div className="det-empty">
      <div className="det-empty-circle">
        <Icon name="fa-eye" />
      </div>
      <p>Acerca un objeto a la camara</p>
      <small>El sistema lo reconocera y el robot reaccionara</small>
    </div>
  )
  return (
    <div className="det-card" style={{ '--accent': meta.color }}>
      <div className="det-header" style={{ background: `linear-gradient(135deg, ${meta.color}, ${meta.color}99)` }}>
        <div className="det-emo-icon"><Icon name={meta.icon} /></div>
        <div className="det-emo-info">
          <span className="det-emo-label">{meta.label.toUpperCase()}</span>
          {detection.confidence && <span className="det-conf">{detection.confidence}</span>}
        </div>
      </div>
      <div className="det-body">
        <div className="det-row">
          <span className="det-label"><Icon name="fa-box" /> Objeto</span>
          <span className="det-value">{detection.object}</span>
        </div>
        {detection.gesture_arm && (
          <div className="det-row">
            <span className="det-label"><Icon name="fa-hand" /> Brazo</span>
            <span className="det-value">{detection.gesture_arm}</span>
          </div>
        )}
        {detection.phrase && (
          <div className="det-phrase">
            <Icon name="fa-quote-left" className="quote-icon" />
            {detection.phrase}
          </div>
        )}
      </div>
    </div>
  )
}

function CaptureGallery({ captures }) {
  if (captures.length === 0) return (
    <div className="gallery-empty">
      <Icon name="fa-images" className="gallery-empty-icon" />
      <p>Las capturas apareceran aqui</p>
      <small>Automatico en cada deteccion</small>
    </div>
  )
  return (
    <div className="gallery-grid">
      {[...captures].reverse().slice(0, 18).map((cap, idx) => {
        const meta = EMOTION_META[cap.emotion] ?? EMOTION_META.neutral
        return (
          <div key={cap.id} className="gallery-item" style={{ animationDelay: `${idx * 0.05}s` }}>
            {cap.thumbnail
              ? <img src={`data:image/jpeg;base64,${cap.thumbnail}`} alt={cap.object} />
              : <div className="gallery-placeholder"><Icon name={meta.icon} /></div>
            }
            <div className="gallery-footer" style={{ background: meta.color }}>
              <Icon name={meta.icon} />
              <span>{cap.object}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function Module1View({ onStop, detection, captures, logs, startKey }) {
  return (
    <section className="module-view">
      <div className="mod-topbar mod1-topbar">
        <div className="mod-topbar-left">
          <div className="mod-icon-circle mod1-circle">
            <Icon name="fa-magnifying-glass" />
          </div>
          <div>
            <h2>Reconocimiento de Objetos</h2>
            <p>YOLO detecta objetos y el robot reacciona con emociones</p>
          </div>
        </div>
        <button className="btn btn-stop" onClick={onStop}>
          <Icon name="fa-stop" /> Detener
        </button>
      </div>

      <div className="m1-layout">
        <div className="m1-main">
          <SectionTitle icon="fa-video">Camara en vivo</SectionTitle>
          <CameraStream mid={1} startKey={startKey} />
          <SectionTitle icon="fa-crosshairs">Ultima deteccion</SectionTitle>
          <DetectionPanel detection={detection} />
        </div>
        <div className="m1-side">
          <SectionTitle icon="fa-camera-retro" count={captures.length}>Capturas de reacciones</SectionTitle>
          <p className="hint-text">Captura automatica del objeto detectado</p>
          <CaptureGallery captures={captures} />
          <SectionTitle icon="fa-terminal">Log en vivo</SectionTitle>
          <EventLog logs={logs} />
        </div>
      </div>
    </section>
  )
}

function Module2View({ onStop, lastGesture, logs, startKey }) {
  return (
    <section className="module-view">
      <div className="mod-topbar mod2-topbar">
        <div className="mod-topbar-left">
          <div className="mod-icon-circle mod2-circle">
            <Icon name="fa-person-rays" />
          </div>
          <div>
            <h2>Reaccion Duplicada</h2>
            <p>MediaPipe detecta tus expresiones y el robot las imita</p>
          </div>
        </div>
        <button className="btn btn-stop" onClick={onStop}>
          <Icon name="fa-stop" /> Detener
        </button>
      </div>

      <div className="m2-layout">
        <div className="m2-main">
          <SectionTitle icon="fa-video">Camara en vivo</SectionTitle>
          <CameraStream mid={2} startKey={startKey} />
          <GestureFlash gesture={lastGesture} />
        </div>
        <div className="m2-side">
          <div className="info-card">
            <div className="info-card-head">
              <Icon name="fa-circle-info" className="info-head-icon" />
              <h3>Como usar</h3>
            </div>
            <ol className="steps">
              <li><Icon name="fa-circle-check" /> Cierra el Serial Monitor de Arduino IDE</li>
              <li><Icon name="fa-circle-check" /> Coloca frente a la camara con buena luz</li>
              <li><Icon name="fa-circle-check" /> Haz expresiones y el robot las imitara</li>
            </ol>
          </div>
          <div className="info-card">
            <div className="info-card-head">
              <Icon name="fa-masks-theater" className="info-head-icon" />
              <h3>Expresiones reconocidas</h3>
            </div>
            <div className="hints-grid">
              {GESTURE_HINTS.map(([icon, name, desc]) => (
                <div key={name} className="hint-item">
                  <div className="hint-icon-wrap"><Icon name={icon} /></div>
                  <div>
                    <strong>{name}</strong>
                    <small>{desc}</small>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <SectionTitle icon="fa-terminal">Pipeline en vivo</SectionTitle>
          <EventLog logs={logs} />
        </div>
      </div>
    </section>
  )
}

function Module3View({ onStop, feedbackState, logs, startKey }) {
  const f = feedbackState
  const target = f?.target_jaw ?? 0
  const actual = f?.feedback_jaw ?? 0
  const error   = target - actual
  const errPct  = Math.abs(error) > 0.001 ? ((error / (target || 0.5)) * 100).toFixed(1) : '0.0'
  const errSign = error > 0 ? '+' : ''
  const angles  = f?.servo_angles ?? {}
  const pid     = f?.pid ?? { Kp: 0, Ki: 0, Kd: 0 }

  return (
    <section className="module-view">
      <div className="mod-topbar mod3-topbar">
        <div className="mod-topbar-left">
          <div className="mod-icon-circle mod3-circle">
            <Icon name="fa-rotate" />
          </div>
          <div>
            <h2>Lazo Cerrado &mdash; PID</h2>
            <p>Control por retroalimentacion visual del robot</p>
          </div>
        </div>
        <button className="btn btn-stop" onClick={onStop}>
          <Icon name="fa-stop" /> Detener
        </button>
      </div>

      <div className="m3-layout">
        <div className="m3-main">
          <SectionTitle icon="fa-video">Robot &mdash; Camara B</SectionTitle>
          <CameraStream mid={3} startKey={startKey} />
        </div>
        <div className="m3-side">
          <SectionTitle icon="fa-chart-line">PID &mdash; Mandibula</SectionTitle>
          <div className="pid-cards">
            <div className="pid-card pid-target">
              <span className="pid-label">
                <Icon name="fa-bullseye" /> Objetivo
              </span>
              <span className="pid-val">{target.toFixed(3)}</span>
              <div className="pid-bar-bg">
                <div className="pid-bar pid-bar-target" style={{ width: `${Math.min(target * 100, 100)}%` }} />
              </div>
            </div>
            <div className="pid-card pid-feedback">
              <span className="pid-label">
                <Icon name="fa-arrow-left" /> Retroalimentacion
              </span>
              <span className="pid-val">{actual.toFixed(3)}</span>
              <div className="pid-bar-bg">
                <div className="pid-bar pid-bar-feedback" style={{ width: `${Math.min(actual * 100, 100)}%` }} />
              </div>
            </div>
            <div className="pid-card pid-error">
              <span className="pid-label">
                <Icon name="fa-circle-exclamation" /> Error
              </span>
              <span className="pid-val">{errSign}{error.toFixed(3)}</span>
              <div className="pid-bar-bg">
                <div className="pid-bar pid-bar-error" style={{ width: `${Math.min(Math.abs(error) / 0.5 * 100, 100)}%` }} />
              </div>
              <span className="pid-err-pct">{errSign}{errPct}%</span>
            </div>
            <div className="pid-card pid-correction">
              <span className="pid-label">
                <Icon name="fa-wrench" /> Correccion
              </span>
              <span className="pid-val">{f?.correction?.toFixed(3) ?? '0.000'}</span>
            </div>
          </div>

          <SectionTitle icon="fa-microchip">Angulos de Servo</SectionTitle>
          <div className="servo-grid">
            {Object.entries(angles).length === 0
              ? <div className="servo-empty">Esperando datos...</div>
              : Object.entries(angles).map(([k, v]) => (
                <div key={k} className="servo-item">
                  <span className="servo-name">{k}</span>
                  <span className="servo-deg">{v.toFixed(1)}&deg;</span>
                  <div className="servo-bar-wrap">
                    <div className="servo-bar" style={{ width: `${((v + 90) / 180) * 100}%` }} />
                  </div>
                </div>
              ))
            }
          </div>

          <SectionTitle icon="fa-sliders">Ganancias PID</SectionTitle>
          <div className="pid-gains">
            <div className="gain-item">
              <span className="gain-label">Kp</span>
              <span className="gain-val">{pid.Kp.toFixed(2)}</span>
            </div>
            <div className="gain-item">
              <span className="gain-label">Ki</span>
              <span className="gain-val">{pid.Ki.toFixed(3)}</span>
            </div>
            <div className="gain-item">
              <span className="gain-label">Kd</span>
              <span className="gain-val">{pid.Kd.toFixed(3)}</span>
            </div>
          </div>

          <SectionTitle icon="fa-terminal">Log en vivo</SectionTitle>
          <EventLog logs={logs} />
        </div>
      </div>
    </section>
  )
}

function Module4View({ onStop, logs, startKey, mod4Phase, mod4Speech, mod4Waiting, mod4Gesture, mod4SessionId, wsRef }) {
  const [showDashboard, setShowDashboard] = useState(false)

  const handleM4Response = useCallback((value, latency) => {
    const msg = JSON.stringify({ type: 'eval_response', value, latency })
    if (wsRef?.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(msg)
    }
  }, [wsRef])

  const handleM4Initiative = useCallback(() => {
    const msg = JSON.stringify({ type: 'eval_initiative' })
    if (wsRef?.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(msg)
    }
  }, [wsRef])

  const handleDownloadReport = useCallback(async () => {
    if (!mod4SessionId) return
    try {
      const r = await fetch(`/api/sessions/${mod4SessionId}/report`)
      if (!r.ok) throw new Error()
      const data = await r.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `sesion_${mod4SessionId}.json`
      a.click(); URL.revokeObjectURL(url)
    } catch {}
  }, [mod4SessionId])

  return (
    <section className="module-view">
      <div className="mod-topbar mod4-topbar">
        <div className="mod-topbar-left">
          <div className="mod-icon-circle mod4-circle">
            <Icon name="fa-flask" />
          </div>
          <div>
            <h2>Prueba de Campo</h2>
            <p>Rutina estructurada de evaluacion &mdash; OE1 a OE5</p>
          </div>
        </div>
        <div className="mod4-header-btns">
          <button className={`btn ${showDashboard ? 'btn-active' : 'btn-ghost'}`}
                  onClick={() => setShowDashboard(d => !d)}>
            <Icon name={showDashboard ? 'fa-robot' : 'fa-chart-simple'} />
            {showDashboard ? 'Robot' : 'Dashboard'}
          </button>
          <button className="btn btn-ghost" onClick={handleDownloadReport}
                  disabled={!mod4SessionId} title="Exportar reporte JSON">
            <Icon name="fa-download" />
          </button>
          <button className="btn btn-stop" onClick={onStop}>
            <Icon name="fa-stop" /> Detener
          </button>
        </div>
      </div>

      {showDashboard ? (
        <Dashboard />
      ) : (
        <div className="m4-layout">
          <div className="m4-main">
            <SectionTitle icon="fa-video">Nino — Camara</SectionTitle>
            <CameraStream mid={4} startKey={startKey} />
          </div>
          <div className="m4-side">
            <SectionTitle icon="fa-robot">Estado del Robot</SectionTitle>
            <RobotView
              phase={mod4Phase}
              speech={mod4Speech}
              gesture={mod4Gesture}
              waitingForResponse={mod4Waiting}
              onResponse={handleM4Response}
              onInitiative={handleM4Initiative}
            />
            <SectionTitle icon="fa-terminal">Log en vivo</SectionTitle>
            <EventLog logs={logs} />
          </div>
        </div>
      )}
    </section>
  )
}

function ModuleCard({ id, icon, title, desc, tags, color, onStart, enabled }) {
  return (
    <div
      className={`module-card${enabled ? ' card-enabled' : ' card-disabled'}`}
      style={{ '--card-color': color }}
      onClick={() => enabled && onStart(id)}
    >
      <div className="card-shine" />
      <div className="card-top">
        <div className="card-icon-bg">
          <Icon name={icon} />
        </div>
        <span className="card-num">0{id}</span>
      </div>
      <h3 className="card-title">{title}</h3>
      <p className="card-desc">{desc}</p>
      <div className="card-tags">
        {tags.map(t => <span key={t} className="tag">{t}</span>)}
      </div>
      <button className="card-btn" disabled={!enabled}>
        {enabled
          ? <><Icon name="fa-play" /> Iniciar modulo</>
          : <><Icon name="fa-spinner fa-spin" /> Esperando backend...</>
        }
      </button>
    </div>
  )
}

function ModuleSelector({ onStart, backendOk }) {
  return (
    <section className="selector">
      <div className="selector-hero">
        <div className="hero-badge">
          <Icon name="fa-brain" /> Sistema TEA
        </div>
        <h2>Que modulo quieres usar hoy?</h2>
        <p>Cada modulo trabaja habilidades socioemocionales distintas con el robot animatronico</p>
      </div>
      <div className="selector-grid">
        <ModuleCard
          id={1} icon="fa-magnifying-glass"
          title="Reconocimiento de Objetos"
          desc="Muestra objetos al robot. Los reconocera y reaccionara con emociones. Se capturan automaticamente las reacciones."
          tags={['YOLO v11', 'Emociones', 'Capturas auto']}
          color="#6366f1"
          onStart={onStart} enabled={backendOk}
        />
        <ModuleCard
          id={2} icon="fa-person-rays"
          title="Reaccion Duplicada"
          desc="El robot imita en tiempo real tus expresiones faciales. Trabaja reconocimiento emocional y empatia."
          tags={['MediaPipe', 'Expresiones', 'Tiempo real']}
          color="#0ea5e9"
          onStart={onStart} enabled={backendOk}
        />
        <ModuleCard
          id={3} icon="fa-rotate"
          title="Lazo Cerrado"
          desc="Control PID por retroalimentacion visual. Dos camaras: una ve la referencia, otra ve al robot."
          tags={['PID', '2 Camaras', 'MediaPipe']}
          color="#10b981"
          onStart={onStart} enabled={backendOk}
        />
        <ModuleCard
          id={4} icon="fa-flask"
          title="Prueba de Campo"
          desc="Rutina estructurada de 15 min. Mide 5 objetivos: contacto visual, atencion conjunta, falsa creencia, TR, iniciativas."
          tags={['Rutina', '5 OEs', 'Robot']}
          color="#f59e0b"
          onStart={onStart} enabled={backendOk}
        />
        <ModuleCard
          id={5} icon="fa-hand"
          title="Deteccion por Agarre"
          desc="Detecta objetos siendo sostenidos. YOLO en el area de la mano, no en toda la imagen."
          tags={['MediaPipe Hands', 'YOLO', 'Crop ROI']}
          color="#ec4899"
          onStart={onStart} enabled={backendOk}
        />
      </div>
    </section>
  )
}

export default function App() {
  const [activeModule, setActiveModule] = useState(null)
  const [startKey,    setStartKey]     = useState(0)
  const [robotOk,     setRobotOk]      = useState(false)
  const [wsOk,        setWsOk]         = useState(false)
  const [backendOk,   setBackendOk]    = useState(false)
  const [detection,   setDetection]    = useState({})
  const [captures,    setCaptures]     = useState([])
  const [logs,        setLogs]         = useState([])
  const [lastGesture, setLastGesture]  = useState(null)
  const [feedbackState, setFeedbackState] = useState(null)
  const [mod4Phase, setMod4Phase] = useState(null)
  const [mod4Speech, setMod4Speech] = useState(null)
  const [mod4Waiting, setMod4Waiting] = useState(false)
  const [mod4Gesture, setMod4Gesture] = useState(null)
  const [mod4SessionId, setMod4SessionId] = useState(null)
  const [graspDetection, setGraspDetection] = useState({})
  const wsRef = useRef(null)

  useEffect(() => {
    let alive = true
    const connect = () => {
      const sock = new WebSocket(WS)
      wsRef.current = sock
      sock.onopen  = () => alive && setWsOk(true)
      sock.onclose = () => { setWsOk(false); if (alive) setTimeout(connect, 2000) }
      sock.onerror = () => sock.close()
      sock.onmessage = ({ data }) => {
        const msg = JSON.parse(data)
        switch (msg.type) {
          case 'module_started':     setActiveModule(msg.module); break
          case 'module_stopped':     setActiveModule(null); break
          case 'module4_started':    setActiveModule(4); setMod4Phase(0); setMod4SessionId(msg.session_id); break
          case 'module4_stopped':    setActiveModule(null); setMod4SessionId(null); break
          case 'detection':          setDetection(msg); break
          case 'capture':            setCaptures(p => [...p, msg]); break
          case 'gesture_sent':       setLastGesture(msg); setMod4Gesture(msg.gesture_id); break
          case 'log':                setLogs(p => [...p.slice(-300), msg.message]); break
          case 'robot_connected':    setRobotOk(true); break
          case 'robot_disconnected': setRobotOk(false); break
          case 'feedback_state':     setFeedbackState(msg); break
          case 'phase_change':       setMod4Phase(msg.phase); setMod4Waiting(false); break
          case 'robot_speech':       setMod4Speech(msg.text); break
          case 'trial_start':        if (msg.oe >= 3) setMod4Waiting(true); break
          case 'trial_result':       setMod4Waiting(false); break
          case 'grasp_detection':    setGraspDetection(msg); break
          case 'grasp_raw':          setGraspDetection(msg); break
          case 'module5_stopped':    setActiveModule(null); break
        }
      }
    }
    connect()
    return () => { alive = false; wsRef.current?.close() }
  }, [])

  useEffect(() => {
    const poll = async () => {
      try {
        const r = await fetch('/api/status')
        if (!r.ok) throw new Error()
        const d = await r.json()
        setBackendOk(true); setRobotOk(d.robot_connected)
      } catch { setBackendOk(false); setRobotOk(false) }
    }
    poll(); const id = setInterval(poll, 3000); return () => clearInterval(id)
  }, [])

  const startModule = useCallback(async (id) => {
    setDetection({}); setCaptures([]); setLogs([]); setLastGesture(null); setFeedbackState(null)
    setGraspDetection({}); setStartKey(k => k + 1)
    try { await fetch(`/api/module/${id}/start`, { method: 'POST' }) } catch {}
    setActiveModule(id)
  }, [])

  const stopModule = useCallback(async () => {
    try { await fetch('/api/module/stop', { method: 'POST' }) } catch {}
    setActiveModule(null)
  }, [])

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <div className="header-logo"><Icon name="fa-robot" /></div>
          <div>
            <h1>Sistema TEA</h1>
            <p>Aprendizaje socioemocional con robot animatronico</p>
          </div>
        </div>
        <div className="header-status">
          <StatusBadge ok={robotOk}   icon="fa-microchip" label={robotOk ? 'Robot COM6' : 'Sin robot'} />
          <StatusBadge ok={backendOk} icon="fa-server"    label={backendOk ? 'Backend' : 'Offline'} />
          <StatusBadge ok={wsOk}      icon="fa-bolt"      label={wsOk ? 'WebSocket' : 'Conectando'} />
          {activeModule && (
            <div className="badge-module-active">
              <Icon name="fa-circle-play" /> Modulo {activeModule}
            </div>
          )}
        </div>
      </header>

      {!backendOk && (
        <div className="offline-banner">
          <Icon name="fa-triangle-exclamation" className="banner-warn-icon" />
          <div>
            <strong>Backend no disponible</strong>
            <span> - Ejecuta: </span>
            <code>.\.venv\Scripts\python.exe server.py</code>
            <span> o doble click en </span>
            <code>iniciar.bat</code>
          </div>
          <div className="banner-spinner" />
        </div>
      )}

      <main className="main">
        {!activeModule && <ModuleSelector onStart={startModule} backendOk={backendOk} />}
        {activeModule === 1 && (
          <Module1View onStop={stopModule} detection={detection} captures={captures} logs={logs} startKey={startKey} />
        )}
        {activeModule === 2 && (
          <Module2View onStop={stopModule} lastGesture={lastGesture} logs={logs} startKey={startKey} />
        )}
        {activeModule === 3 && (
          <Module3View onStop={stopModule} feedbackState={feedbackState} logs={logs} startKey={startKey} />
        )}
        {activeModule === 4 && (
          <Module4View onStop={stopModule} logs={logs} startKey={startKey}
            mod4Phase={mod4Phase} mod4Speech={mod4Speech}
            mod4Waiting={mod4Waiting} mod4Gesture={mod4Gesture}
            mod4SessionId={mod4SessionId} wsRef={wsRef}
          />
        )}
        {activeModule === 5 && (
          <Module5View onStop={stopModule} detection={graspDetection} logs={logs} startKey={startKey} />
        )}
      </main>

      <footer className="footer">
        <Icon name="fa-robot" />
        <span>Sistema TEA - Arduino Uno - PCA9685 - MediaPipe - YOLO v11</span>
        <Icon name="fa-heart" className="footer-heart" />
      </footer>
    </div>
  )
}
