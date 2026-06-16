import { useState, useEffect } from 'react'

const BACKEND = `http://localhost:8000`
const OE_META = {
  1: { icon: 'fa-eye',        title: 'Contacto Visual',           target: '>= 3s por episodio / +20% S1→S3', color: '#6366f1' },
  2: { icon: 'fa-hand-pointer', title: 'Atencion Conjunta',       target: '>= 2 episodios por sesion',        color: '#0ea5e9' },
  3: { icon: 'fa-brain',     title: 'Falsa Creencia',             target: '> 50% de aciertos',                 color: '#10b981' },
  4: { icon: 'fa-gauge-high', title: 'Tiempo de Respuesta',       target: '±500ms precision / -15% S1→S3',    color: '#f59e0b' },
  5: { icon: 'fa-comment',   title: 'Iniciativas Espontaneas',    target: '>= 1 por sesion / aumento S1→S3',  color: '#ef4444' },
}

function OECard({ oe, data, sessions }) {
  const meta = OE_META[oe]
  if (!meta) return null

  function StatusIcon({ ok }) {
    return (
      <span className={`oe-status ${ok ? 'oe-ok' : 'oe-pending'}`}>
        <i className={`fa-solid ${ok ? 'fa-circle-check' : 'fa-circle'}`} />
      </span>
    )
  }

  let value = null
  let status = false

  if (oe === 1) {
    const avg = data?.avg_duration_s ?? 0
    value = `${avg.toFixed(1)}s`
    status = avg >= 3.0
  } else if (oe === 2) {
    const cnt = data?.count ?? 0
    const rate = data?.success_rate ?? 0
    value = `${cnt} ep. (${(rate * 100).toFixed(0)}% ok)`
    status = cnt >= 2
  } else if (oe === 3) {
    const acc = data?.accuracy ?? 0
    const cnt = data?.count ?? 0
    value = cnt > 0 ? `${(acc * 100).toFixed(0)}% (${cnt} trials)` : '—'
    status = acc > 0.5
  } else if (oe === 4) {
    const lat = data?.avg_latency_ms ?? 0
    value = `${lat.toFixed(0)}ms`
    status = lat > 0
  } else if (oe === 5) {
    const cnt = data?.count ?? 0
    value = `${cnt} iniciativas`
    status = cnt >= 1
  }

  return (
    <div className="oe-card" style={{ '--accent': meta.color }}>
      <div className="oe-card-head">
        <div className="oe-icon" style={{ background: `${meta.color}22`, color: meta.color }}>
          <i className={`fa-solid ${meta.icon}`} />
        </div>
        <div className="oe-title">
          <span className="oe-label">OE{oe}</span>
          <strong>{meta.title}</strong>
        </div>
        <StatusIcon ok={status} />
      </div>
      <div className="oe-value">{value}</div>
      <div className="oe-target">{meta.target}</div>
      <div className="oe-card-bar">
        <div className="oe-bar-bg">
          <div className="oe-bar-fill" style={{
            width: oe === 1 ? `${Math.min((data?.avg_duration_s ?? 0) / 5 * 100, 100)}%` :
                   oe === 2 ? `${Math.min((data?.count ?? 0) / 5 * 100, 100)}%` :
                   oe === 3 ? `${Math.max((data?.accuracy ?? 0) * 100, 5)}%` :
                   oe === 5 ? `${Math.min((data?.count ?? 0) / 5 * 100, 100)}%` :
                   '50%',
            background: meta.color
          }} />
        </div>
      </div>
    </div>
  )
}

function SessionRow({ s }) {
  if (!s) return null
  const ses = s.session ?? {}
  return (
    <div className="ses-row">
      <div className="ses-label">{ses.label ?? `Sesion #${ses.id}`}</div>
      <div className="ses-oe">
        <span>{s.oe1?.avg_duration_s?.toFixed(1) ?? '—'}s</span>
        <span>{s.oe2?.count ?? 0}</span>
        <span>{s.oe3?.accuracy != null ? `${(s.oe3.accuracy * 100).toFixed(0)}%` : '—'}</span>
        <span>{s.oe4?.avg_latency_ms?.toFixed(0) ?? '—'}ms</span>
        <span>{s.oe5?.count ?? 0}</span>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [sessions, setSessions] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(`${BACKEND}/api/dashboard`)
        if (r.ok) {
          const data = await r.json()
          setSessions(data)
          if (data.length > 0) {
            setSelected(data[data.length - 1].session?.id ?? null)
          }
        }
      } catch {}
    }
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (selected == null) return
    const load = async () => {
      try {
        const r = await fetch(`${BACKEND}/api/sessions/${selected}`)
        if (r.ok) setDetail(await r.json())
      } catch {}
    }
    load()
    const id = setInterval(load, 3000)
    return () => clearInterval(id)
  }, [selected])

  return (
    <div className="dashboard">
      <div className="dash-header">
        <div className="dash-title-row">
          <div className="dash-icon"><i className="fa-solid fa-chart-simple" /></div>
          <div>
            <h2>Dashboard — Prueba de Campo</h2>
            <p>Seguimiento de objetivos OE1–OE5 a traves de sesiones</p>
          </div>
        </div>
        <div className="dash-sel">
          <label>Sesion:</label>
          <select value={selected ?? ''} onChange={e => setSelected(Number(e.target.value) || null)}>
            {sessions.map(s => (
              <option key={s.session?.id} value={s.session?.id}>
                {s.session?.label ?? `Sesion #${s.session?.id}`}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="oe-grid">
        {[1, 2, 3, 4, 5].map(oe => (
          <OECard key={oe} oe={oe} data={detail?.[`oe${oe}`]} sessions={sessions} />
        ))}
      </div>

      {sessions.length > 1 && (
        <>
          <div className="section-header" style={{ marginTop: '2rem' }}>
            <div className="section-title-row">
              <i className="fa-solid fa-table sec-icon" />
              <h3>Comparativa entre Sesiones</h3>
            </div>
          </div>
          <div className="cross-table">
            <div className="ses-row ses-row-header">
              <div className="ses-label">Sesion</div>
              <div className="ses-oe">
                <span>OE1</span><span>OE2</span><span>OE3</span><span>OE4</span><span>OE5</span>
              </div>
            </div>
            {sessions.map(s => (
              <SessionRow key={s.session?.id} s={s} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
