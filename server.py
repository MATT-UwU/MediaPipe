#!/usr/bin/env python3
"""
server.py — Backend FastAPI para la interfaz web TEA

Módulo 1: Lanza tea_object_emotion.py (ventana cv2 propia),
          parsea su stdout para eventos, captura pantalla en cada detección.

Módulo 2: Lanza pipeline face_capture | classify_gesture | gesture_serial
          (ventana cv2 propia), parsea stderr para el log de gestos.

Módulo 3: Lanza visual_feedback_controller.py (lazo cerrado con 2 cámaras),
          parsea su stdout para estado del PID y retroalimentación visual.

Cómo correr:
    python server.py
"""

import asyncio
import base64
import io
import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import tempfile

import serial as pyserial
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw

import tracking_db as db

# ============================================================
# CONFIGURACIÓN
# ============================================================
IS_WINDOWS = platform.system() == "Windows"
SERIAL_PORT  = "COM6" if IS_WINDOWS else "/dev/ttyUSB0"
BAUD_RATE    = 9600
CAPTURES_DIR = Path("captures")
CAPTURES_DIR.mkdir(exist_ok=True)
PYTHON       = sys.executable
BASE_DIR     = Path(__file__).parent

# ============================================================
# FASTAPI
# ============================================================
app = FastAPI(title="TEA Learning System")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ============================================================
# ESTADO
# ============================================================
class State:
    active_module: Optional[int] = None
    proc: Optional[subprocess.Popen] = None
    module_thread: Optional[threading.Thread] = None
    stop_event = threading.Event()
    captures: list = []
    last_detection: dict = {}

state = State()
event_loop: Optional[asyncio.AbstractEventLoop] = None

# ============================================================
# WEBSOCKET
# ============================================================
class WSManager:
    def __init__(self): self._conns: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept(); self._conns.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._conns: self._conns.remove(ws)

    async def broadcast(self, msg: dict):
        dead = []
        for ws in self._conns:
            try: await ws.send_json(msg)
            except: dead.append(ws)
        for ws in dead: self._conns.remove(ws)

ws = WSManager()

def push(msg: dict):
    """Enviar evento desde un hilo."""
    if event_loop and not event_loop.is_closed():
        asyncio.run_coroutine_threadsafe(ws.broadcast(msg), event_loop)

# ============================================================
# STARTUP
# ============================================================
@app.on_event("startup")
async def on_start():
    global event_loop
    event_loop = asyncio.get_event_loop()
    db.init_db()

# ============================================================
# REST API
# ============================================================
@app.get("/api/status")
def api_status():
    robot_ok = False
    try:
        s = pyserial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1); s.close(); robot_ok = True
    except: pass
    return {
        "active_module":  state.active_module,
        "robot_connected": robot_ok,
        "serial_port":    SERIAL_PORT,
        "captures_count": len(state.captures),
        "last_detection": state.last_detection,
    }

@app.post("/api/module/{mid}/start")
async def api_start(mid: int):
    _stop_all()
    # Borrar frame viejo para que el stream muestre spinner hasta que llegue uno real
    f = _FRAME_FILES.get(mid)
    if f:
        try: f.unlink(missing_ok=True)
        except: pass
    state.active_module = mid
    state.stop_event.clear()
    fn = {1: _run_module1, 2: _run_module2, 3: _run_module3, 4: _run_module4, 5: _run_module5}.get(mid)
    if fn is None:
        return {"error": "invalid module"}
    t = threading.Thread(target=fn, daemon=True)
    state.module_thread = t; t.start()
    await ws.broadcast({"type": "module_started", "module": mid})
    return {"status": "started", "module": mid}

@app.post("/api/module/stop")
async def api_stop():
    _stop_all()
    await ws.broadcast({"type": "module_stopped"})
    return {"status": "stopped"}

@app.get("/api/captures")
def api_captures():
    return [
        {k: v for k, v in c.items() if k != "thumbnail"}
        for c in state.captures
    ]

@app.get("/api/captures/{cid}/image")
def api_capture_image(cid: str):
    for cap in state.captures:
        if cap["id"] == cid:
            return StreamingResponse(
                io.BytesIO(base64.b64decode(cap["thumbnail"])),
                media_type="image/jpeg"
            )
    return {"error": "not found"}


# ============================================================
# SESSIONS / DASHBOARD API
# ============================================================
@app.get("/api/sessions")
def api_sessions():
    return db.get_sessions()

@app.post("/api/sessions")
def api_create_session(label: str = "Demo"):
    sid = db.create_session(label)
    return {"session_id": sid}

@app.post("/api/sessions/close")
def api_close_session():
    sessions = db.get_sessions()
    open_sessions = [s for s in sessions if s.get("ended_at") is None]
    if open_sessions:
        db.close_session(open_sessions[-1]["id"])
        return {"status": "closed", "session_id": open_sessions[-1]["id"]}
    return {"status": "no_open_session"}

@app.get("/api/sessions/{sid}")
def api_session(sid: int):
    return db.get_session_summary(sid)

@app.get("/api/sessions/{sid}/report")
def api_session_report(sid: int):
    return db.get_session_report(sid)

@app.get("/api/dashboard")
def api_dashboard():
    return db.get_cross_session_summary()


@app.websocket("/ws")
async def ws_endpoint(sock: WebSocket):
    await ws.connect(sock)
    try:
        while True:
            msg = json.loads(await sock.receive_text())
            t = msg.get("type")
            if t == "ping":
                await sock.send_json({"type": "pong"})
            elif t == "eval_response":
                if state.proc and state.proc.stdin and not state.proc.stdin.closed:
                    line = json.dumps({"type": "eval_response", "value": msg["value"], "latency": msg.get("latency", 0)}) + "\n"
                    state.proc.stdin.write(line)
                    state.proc.stdin.flush()
            elif t == "eval_initiative":
                if state.proc and state.proc.stdin and not state.proc.stdin.closed:
                    line = json.dumps({"type": "eval_initiative"}) + "\n"
                    state.proc.stdin.write(line)
                    state.proc.stdin.flush()
    except WebSocketDisconnect:
        ws.disconnect(sock)

# ============================================================
# STREAM MJPEG — lee frames escritos por run_module1.py / run_face_capture.py
# ============================================================
_TMP = Path(tempfile.gettempdir())
_FRAME_FILES = {
    1: _TMP / "tea_module1_frame.jpg",
    2: _TMP / "tea_module2_frame.jpg",
    3: _TMP / "tea_module3_frame.jpg",
    4: _TMP / "tea_module4_frame.jpg",
    5: _TMP / "tea_module5_frame.jpg",
}

def _make_placeholder() -> bytes:
    img = Image.new("RGB", (640, 360), color=(15, 23, 42))
    d   = ImageDraw.Draw(img)
    d.text((20, 170), "Abriendo camara...", fill=(100, 116, 139))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()

_PLACEHOLDER: Optional[bytes] = None

async def _mjpeg_gen(module_id: int):
    global _PLACEHOLDER
    frame_file = _FRAME_FILES.get(module_id)
    loop = asyncio.get_event_loop()

    if _PLACEHOLDER is None:
        _PLACEHOLDER = await loop.run_in_executor(None, _make_placeholder)

    while True:
        def _read():
            if frame_file and frame_file.exists():
                try:
                    data = frame_file.read_bytes()
                    # Validar magic bytes JPEG para descartar lecturas parciales
                    if len(data) > 4 and data[0] == 0xff and data[1] == 0xd8:
                        return data
                except Exception:
                    pass
            return None

        data = await loop.run_in_executor(None, _read) or _PLACEHOLDER
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n"
            + data + b"\r\n"
        )
        await asyncio.sleep(1 / 30)   # 30 fps

@app.get("/stream/{mid}")
async def stream_endpoint(mid: int):
    if mid not in _FRAME_FILES:
        return {"error": "invalid module"}
    return StreamingResponse(
        _mjpeg_gen(mid),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

# ============================================================
# CAPTURA DE PANTALLA — reacción humana
# ============================================================
def _cam_frame_b64(module_id: int) -> Optional[str]:
    """Lee el último frame de la cámara del módulo (escrito por el wrapper)."""
    f = _FRAME_FILES.get(module_id)
    if f and f.exists():
        try:
            return base64.b64encode(f.read_bytes()).decode()
        except Exception:
            pass
    return None

# ============================================================
# MÓDULO 1 — tea_object_emotion.py como subproceso
# ============================================================
# Patrón de la salida del script original:
# 📦 Objeto: apple (confianza: 85%)
# 😊 Emoción: feliz
# 💬 "Una manzana, qué rica y saludable"
_OBJ_RE    = re.compile(r"Objeto:\s*(.+?)\s*\(confianza:\s*([\d.]+%?)\)")
_EMO_RE    = re.compile(r"Emoci[oó]n:\s*(\w+)")
_FRASE_RE  = re.compile(r"\"(.+)\"")
_GESTO_RE  = re.compile(r"Gesto brazo:\s*(\w+)")

def _run_module1():
    MAX_RESTARTS = 3
    _env = {**os.environ, "PYTHONUNBUFFERED": "1"}

    for attempt in range(MAX_RESTARTS + 1):
        if state.stop_event.is_set():
            return

        msg = "Iniciando reconocimiento de objetos..." if attempt == 0 \
              else f"Reiniciando proceso (intento {attempt}/{MAX_RESTARTS})..."
        push({"type": "log", "message": msg})

        proc = subprocess.Popen(
            [PYTHON, str(BASE_DIR / "run_module1.py")],
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, bufsize=1, encoding="utf-8", errors="replace",
            env=_env,
            start_new_session=not IS_WINDOWS,
        )
        state.proc = proc

        # Buffer para agrupar las líneas del bloque de detección
        pending: dict = {}

        def _do_capture(det):
            """Captura asíncrona: espera 0.3s para que el frame anotado esté listo."""
            time.sleep(0.3)
            b64  = _cam_frame_b64(1)
            now  = time.time()
            cid  = f"cap_{int(now * 1000)}"
            entry = {"id": cid, "timestamp": now, **det}
            if b64:
                entry["thumbnail"] = b64
                try:
                    (CAPTURES_DIR / f"{cid}.jpg").write_bytes(base64.b64decode(b64))
                except Exception:
                    pass
            state.captures.append(entry)
            push({"type": "detection", **det})
            push({"type": "capture", "id": cid, "timestamp": now, **det,
                  "thumbnail": b64 or ""})

        def _read(stream, is_err=False):
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                if is_err:
                    push({"type": "log", "message": line})
                    continue

                # Parsear bloque de detección
                if mx := _OBJ_RE.search(line):
                    pending["object"]     = mx.group(1).strip()
                    pending["confidence"] = mx.group(2)
                elif mx := _EMO_RE.search(line):
                    pending["emotion"]    = mx.group(1).strip()
                elif mx := _FRASE_RE.search(line):
                    pending["phrase"]     = mx.group(1).strip()
                elif mx := _GESTO_RE.search(line):
                    pending["gesture_arm"] = mx.group(1).strip()

                # Cuando tenemos objeto + emoción + frase, disparar captura
                if all(k in pending for k in ("object", "emotion", "phrase")):
                    det = dict(pending)
                    pending.clear()
                    state.last_detection = det
                    # La captura se hace en un hilo para no bloquear la lectura de stdout
                    threading.Thread(target=_do_capture, args=(det,), daemon=True).start()

                push({"type": "log", "message": line})

        t_out = threading.Thread(target=_read, args=(proc.stdout,),      daemon=True)
        t_err = threading.Thread(target=_read, args=(proc.stderr, True), daemon=True)
        t_out.start(); t_err.start()

        crashed = False
        while not state.stop_event.is_set():
            if proc.poll() is not None:
                push({"type": "log", "message": f"Proceso finalizado (código {proc.returncode})."})
                crashed = True
                break
            time.sleep(0.5)

        _kill(proc)
        t_out.join(timeout=2)
        t_err.join(timeout=2)

        if not crashed or state.stop_event.is_set():
            return       # salida limpia (usuario detuvo o cap.read() eof sin error)

        if attempt < MAX_RESTARTS:
            push({"type": "log", "message": "Reiniciando en 2 segundos..."})
            time.sleep(2)

    push({"type": "log", "message": "No se pudo mantener el proceso activo (3 intentos)。"})

# ============================================================
# MÓDULO 2 — face_capture | classify_gesture | gesture_serial
# ============================================================
def _run_module2():
    push({"type": "log", "message": "Iniciando pipeline facial..."})

    pipeline = (
        f'"{PYTHON}" run_face_capture.py | '
        f'"{PYTHON}" classify_gesture.py | '
        f'"{PYTHON}" gesture_serial.py'
    )
    if IS_WINDOWS:
        cmd_str = f'cmd /c "{pipeline}"'
    else:
        cmd_str = pipeline
    _env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        cmd_str, cwd=str(BASE_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
        env=_env, shell=True,
        start_new_session=not IS_WINDOWS,
    )
    state.proc = proc

    def _read_stderr():
        for line in proc.stderr:
            line = line.strip()
            if not line: continue
            push({"type": "log", "message": line})

            # Parsear "[gesture_serial] -> '10' (sonrisa)"
            if "->" in line and "gesture_serial" in line:
                try:
                    parts = line.split("->")[1].strip().split("'")
                    gid   = int(parts[1])
                    name  = parts[2].strip().strip("() ")
                    push({"type": "gesture_sent", "gesture_id": gid, "name": name})
                    state.last_detection = {"gesture_id": gid, "name": name}
                except Exception: pass

    threading.Thread(target=_read_stderr, daemon=True).start()
    push({"type": "module2_ready"})

    while not state.stop_event.is_set():
        if proc.poll() is not None:
            push({"type": "log", "message": "Pipeline finalizado."}); break
        time.sleep(0.5)

    _kill(proc)

# ============================================================
# MÓDULO 3 — visual_feedback_controller (lazo cerrado)
# ============================================================
def _run_module3():
    push({"type": "log", "message": "Iniciando controlador de lazo cerrado..."})

    proc = subprocess.Popen(
        [PYTHON, str(BASE_DIR / "visual_feedback_controller.py")],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        start_new_session=not IS_WINDOWS,
    )
    state.proc = proc

    def _read_stdout():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "feedback_state":
                    state.last_detection = data
                    push({"type": "feedback_state", **data})
            except json.JSONDecodeError:
                pass

    def _read_stderr():
        for line in proc.stderr:
            line = line.strip()
            if not line:
                continue
            push({"type": "log", "message": line})

    threading.Thread(target=_read_stdout, daemon=True).start()
    threading.Thread(target=_read_stderr, daemon=True).start()

    while not state.stop_event.is_set():
        if proc.poll() is not None:
            push({"type": "log", "message": "Controlador de lazo cerrado finalizado."})
            break
        time.sleep(0.5)
    _kill(proc)


# ============================================================
# MÓDULO 4 — run_module4.py (prueba de campo)
# ============================================================
_MOD4_TIMEOUT = 60 * 20  # 20 min max

def _run_module4():
    push({"type": "log", "message": "Iniciando prueba de campo (Módulo 4)..."})

    sid = db.create_session("Demo")
    push({"type": "module4_started", "session_id": sid})

    proc = subprocess.Popen(
        [PYTHON, str(BASE_DIR / "run_module4.py"),
         "--session-id", str(sid),
         "--serial-port", SERIAL_PORT],
        cwd=str(BASE_DIR),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        start_new_session=not IS_WINDOWS,
    )
    state.proc = proc

    def _read_stdout():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                ev_type = ev.get("type", "")

                if ev_type == "log":
                    push({"type": "log", "message": ev["message"]})

                elif ev_type == "robot_speech":
                    push({"type": "log",
                          "message": f"🤖 Robot: \"{ev['text']}\""})

                elif ev_type == "phase_change":
                    state.last_detection = {"phase": ev["phase"], "name": ev["name"]}
                    push({"type": "phase_change", **ev})

                elif ev_type == "eye_contact":
                    push({"type": "metric_update", "oe": 1,
                          "duration_ms": ev["duration_ms"],
                          "threshold_ms": ev["threshold_ms"]})

                elif ev_type == "trial_result":
                    push({"type": "trial_result", **ev})

                elif ev_type == "response_time":
                    push({"type": "metric_update", "oe": 4,
                          "stimulus": ev.get("stimulus_type", ""),
                          "latency_ms": ev["latency_ms"]})

                elif ev_type == "calibration":
                    push({"type": "log",
                          "message": f"Calibración: yaw={ev['yaw_center']}°"})

                elif ev_type == "gesture_sent":
                    push({"type": "gesture_sent",
                          "gesture_id": ev["gesture_id"]})

                elif ev_type == "trial_start":
                    push({"type": "trial_start", **ev})

                elif ev_type == "module4_stopped":
                    push({"type": "module4_stopped"})

            except json.JSONDecodeError:
                pass

    def _read_stderr():
        for line in proc.stderr:
            line = line.strip()
            if not line:
                continue
            push({"type": "log", "message": line})

    threading.Thread(target=_read_stdout, daemon=True).start()
    threading.Thread(target=_read_stderr, daemon=True).start()

    deadline = time.time() + _MOD4_TIMEOUT
    while not state.stop_event.is_set():
        if proc.poll() is not None:
            push({"type": "log", "message": "Módulo 4 finalizado."})
            break
        if time.time() > deadline:
            push({"type": "log", "message": "Timeout Módulo 4."})
            break
        time.sleep(0.5)

    _kill(proc)


# ============================================================
# MÓDULO 5 — mod5_grasp_detector.py (agarre + YOLO crop)
# ============================================================
_MOD5_TIMEOUT = 60 * 30

def _run_module5():
    push({"type": "log", "message": "Iniciando modulo 5 (Grasp + YOLO crop)..."})

    proc = subprocess.Popen(
        [PYTHON, str(BASE_DIR / "run_module5.py")],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        start_new_session=not IS_WINDOWS,
    )
    state.proc = proc

    def _read_stdout():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                ev_type = ev.get("type", "")

                if ev_type == "grasp_detection":
                    push({"type": "grasp_detection", **ev})

                elif ev_type == "module5_stopped":
                    push({"type": "module5_stopped"})

                elif ev_type == "log":
                    push({"type": "log", "message": ev["message"]})

            except json.JSONDecodeError:
                pass

    def _read_stderr():
        for line in proc.stderr:
            line = line.strip()
            if not line:
                continue
            push({"type": "log", "message": line})

    threading.Thread(target=_read_stdout, daemon=True).start()
    threading.Thread(target=_read_stderr, daemon=True).start()

    deadline = time.time() + _MOD5_TIMEOUT
    while not state.stop_event.is_set():
        if proc.poll() is not None:
            push({"type": "log", "message": "Módulo 5 finalizado."})
            break
        if time.time() > deadline:
            push({"type": "log", "message": "Timeout Módulo 5."})
            break
        time.sleep(0.5)

    _kill(proc)


# ============================================================
# HELPERS
# ============================================================
def _kill(proc):
    if IS_WINDOWS:
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                capture_output=True, timeout=5
            )
        except Exception:
            pass
    else:
        try:
            own_pgid = os.getpgid(0)
            child_pgid = os.getpgid(proc.pid)
            if child_pgid != own_pgid:
                os.killpg(child_pgid, signal.SIGTERM)
        except Exception:
            pass
    try:
        proc.terminate()
        proc.wait(timeout=4)
    except Exception:
        try: proc.kill()
        except: pass

def _stop_all():
    state.stop_event.set()
    if state.proc: _kill(state.proc); state.proc = None
    if state.module_thread and state.module_thread.is_alive():
        state.module_thread.join(timeout=5)
    state.active_module = None
    state.stop_event.clear()

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("   TEA Learning System — Backend")
    print(f"   Puerto serial : {SERIAL_PORT}")
    print(f"   Capturas en   : {CAPTURES_DIR.absolute()}")
    print(f"   API            : http://localhost:8000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
