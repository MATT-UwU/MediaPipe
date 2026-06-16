const BACKEND_URL = `http://localhost:8000`

function GripIcon({ grasp }) {
  const icons = { fist: 'fa-hand-fist', pinch: 'fa-hand-peace', palm: 'fa-hand', open: 'fa-hand', none: 'fa-hand' }
  const labels = { fist: 'Puño', pinch: 'Pinza', palm: 'Palma', open: 'Abierta', none: '—' }
  return (
    <span className="m5-grip-icon">
      <i className={`fa-solid ${icons[grasp] ?? 'fa-hand'}`} />
      <span>{labels[grasp] ?? grasp}</span>
    </span>
  )
}

export default function Module5View({ onStop, detection, logs, startKey }) {
  const d = detection ?? {}
  const gtype = d.grasp ?? 'none'
  const isRaw = d.type === 'grasp_raw'
  const hasEmotion = !!d.emotion

  return (
    <section className="module-view">
      <div className="mod-topbar">
        <div className="mod-topbar-left">
          <div className="mod-icon-circle" style={{ background: '#ec4899' }}>
            <i className="fa-solid fa-hand" />
          </div>
          <div>
            <h2>Deteccion por Agarre</h2>
            <p>YOLO en area de la mano &mdash; objetos siendo sostenidos</p>
          </div>
        </div>
        <button className="btn btn-stop" onClick={onStop}>
          <i className="fa-solid fa-stop" /> Detener
        </button>
      </div>

      <div className="m5-layout">
        <div className="m5-main">
          <h3 className="section-title"><i className="fa-solid fa-video" /> Camara</h3>
          <div className="m5-stream-wrap">
            <img className="m5-stream" src={`${BACKEND_URL}/stream/5?_=${startKey}`} alt="camara" />
            {gtype !== 'none' && (
              <div className="m5-overlay-grip">
                <GripIcon grasp={gtype} />
              </div>
            )}
          </div>
        </div>
        <div className="m5-side">
          <div className="info-card m5-info">
            <h4><i className="fa-solid fa-hand" /> Estado de la Mano</h4>
            <p className="m5-grip-label">
              <GripIcon grasp={gtype} />
            </p>
          </div>

          <div className="info-card m5-info">
            <h4><i className="fa-solid fa-cube" /> Ultimo objeto</h4>
            {d.object ? (
              <>
                <p className="m5-obj-name">{d.object}</p>
                <div className="m5-detail-grid">
                  <span>Confianza</span><span>{(d.confidence * 100).toFixed(0)}%</span>
                  {isRaw && <span className="m5-raw-tag" style={{gridColumn:'1/-1'}}>Sin mapping emocional</span>}
                  {hasEmotion && <><span>Emocion</span><span>{d.emotion}</span></>}
                  {hasEmotion && <><span>Gesto brazo</span><span>{d.arm_gesture}</span></>}
                  {hasEmotion && <><span>Gesto cara</span><span>#{d.face_gesture}</span></>}
                  {hasEmotion && <><span>Frase</span><span className="m5-phrase">"{d.phrase}"</span></>}
                </div>
              </>
            ) : (
              <p className="m5-empty">Esperando deteccion...</p>
            )}
          </div>

          <div className="info-card m5-info">
            <h4><i className="fa-solid fa-terminal" /> Log</h4>
            <div className="m5-log">
              {logs.length === 0 && <p className="m5-empty">Sin eventos</p>}
              {logs.slice(-15).map((m, i) => <div key={i} className="log-line">{m}</div>)}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
