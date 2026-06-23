#!/usr/bin/env python3
"""Module 4 — Prueba de Campo: rutina estructurada para medir OE1–OE5."""

import argparse
import json
import math
import os
import queue
import random
import select
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

import tracking_db as db

BASE_DIR = Path(__file__).parent
FRAME_FILE = Path(tempfile.gettempdir()) / "tea_module4_frame.jpg"
JPEG_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, 72]


class TTS:
    def __init__(self):
        self._engine = None
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 150)
            self._engine.setProperty("volume", 0.8)
        except Exception:
            print("[TTS] pyttsx3 no disponible, simulando", file=sys.stderr)

    def say(self, text: str):
        if self._engine:
            self._engine.say(text)
            self._engine.runAndWait()
        else:
            print(f'[TTS] (simulacion): {text}', file=sys.stderr)


def compute_yaw(m):
    return math.degrees(math.atan2(-m[6], math.sqrt(m[0]**2 + m[3]**2)))


def compute_pitch(m):
    return math.degrees(math.atan2(m[7], m[8]))


class Mod4Routine:
    def __init__(self, session_id: int, serial_port: str = "COM6",
                 dry_run: bool = False, seed: int = None, auto_eval: bool = False):
        self.session_id = session_id
        self.serial_port = serial_port
        self.dry_run = dry_run
        self.auto_eval = auto_eval
        self.stop_flag = False
        self._rng = random.Random(seed)
        signal.signal(signal.SIGINT, lambda *a: setattr(self, 'stop_flag', True))
        try:
            signal.signal(signal.SIGTERM, lambda *a: setattr(self, 'stop_flag', True))
        except ValueError:
            pass
        self._load_routine()
        self._init_tts()
        self._init_serial()
        self._init_camera()
        self.cal_yaw = 0.0
        self.cal_pitch = 0.0
        self.is_calibrated = False
        self.ec_active = False
        self.ec_start = 0.0
        self.current_phase = -1
        self.phase_start = 0.0
        self.eval_queue = queue.Queue()
        self._stdin_thread = None
        self._initiatives_logged = 0

    def _load_routine(self):
        with open(BASE_DIR / "mod4_routine.json") as f:
            self.cfg = json.load(f)
        self.phases = self.cfg["phases"]
        self.t = self.cfg["oe_thresholds"]
        self.gz = self.cfg["gaze"]

    def _init_tts(self):
        self.tts = TTS()

    def _init_serial(self):
        self.ser = None
        try:
            import serial
            self.ser = serial.Serial(self.serial_port, 9600, timeout=0.1)
            time.sleep(2)
            self.ser.reset_input_buffer()
            self._dbg(f"Serial {self.serial_port} abierto")
        except Exception as e:
            self._dbg(f"Serial no disponible: {e}")

    def _init_camera(self):
        if self.dry_run:
            self._dbg("DRY RUN: camara simulada")
            self.latest = None
            self.cap = None
            self.det = None
            self._sim_t = 0.0
            self._sim_looking = True
            return
        mp_path = str(BASE_DIR / "face_landmarker_v2_with_blendshapes.task")
        url = ("https://storage.googleapis.com/mediapipe-models/"
               "face_landmarker/face_landmarker/float16/1/face_landmarker.task")
        if not os.path.exists(mp_path):
            self._dbg("Descargando modelo face_landmarker...")
            import urllib.request
            urllib.request.urlretrieve(url, mp_path)
        base = python.BaseOptions(model_asset_path=mp_path)
        opts = vision.FaceLandmarkerOptions(
            base_options=base,
            running_mode=vision.RunningMode.LIVE_STREAM,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            result_callback=self._cb,
        )
        self.det = vision.FaceLandmarker.create_from_options(opts)
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self._log("ERROR: no se pudo abrir la camara")
            sys.exit(1)
        self.latest = None
        self._dbg("Camara abierta")

    def _cb(self, result, out_img, ts_ms):
        self.latest = result

    def _dbg(self, msg):
        print(f"[mod4] {msg}", file=sys.stderr, flush=True)

    def _log(self, msg):
        self._json({"type": "log", "message": msg})
        self._dbg(msg)

    def _json(self, d):
        print(json.dumps(d), flush=True)

    def _frame(self, frame):
        try:
            ok, buf = cv2.imencode(".jpg", frame, JPEG_PARAMS)
            if ok:
                FRAME_FILE.write_bytes(buf.tobytes())
        except Exception:
            pass

    def _gesture(self, gid: int):
        if self.ser:
            self.ser.write(f"{gid}\n".encode())
        self._json({"type": "gesture_sent", "gesture_id": gid})

    def _arm(self, cmd: str):
        if self.ser:
            self.ser.write(f"{cmd}\n".encode())
        self._log(f"Brazo: {cmd}")

    def _speak(self, text: str):
        self._json({"type": "robot_speech", "text": text})
        self._dbg(f'Robot: "{text}"')
        self.tts.say(text)

    def _head_pose(self):
        if self.dry_run:
            return self._sim_head_pose()
        r = self.latest
        if not r or not r.face_landmarks:
            return None, None
        bs = {}
        if r.face_blendshapes:
            bs = {c.category_name: c.score for c in r.face_blendshapes[0]}
        if r.facial_transformation_matrixes:
            m = r.facial_transformation_matrixes[0]
            flat = [m[0, 0], m[0, 1], m[0, 2],
                    m[1, 0], m[1, 1], m[1, 2],
                    m[2, 0], m[2, 1], m[2, 2]]
            yaw = compute_yaw(flat)
            pitch = compute_pitch(flat)
        else:
            yaw, pitch = 0.0, 0.0
        return yaw, pitch

    def _sim_head_pose(self):
        if not self.is_calibrated:
            return 0.0, 0.0
        self._sim_t += 1
        cycle = (self._sim_t // 200) % 2
        noise = self._rng.uniform(-2, 2)
        if cycle == 0:
            if self._rng.random() < 0.1:
                return self.cal_yaw + self._rng.uniform(25, 40), self.cal_pitch + self._rng.uniform(5, 12)
            return self.cal_yaw + 2.0 + noise, self.cal_pitch + 1.0 + noise * 0.5
        else:
            if self._rng.random() < 0.15:
                return self.cal_yaw + self._rng.uniform(-3, 3), self.cal_pitch + self._rng.uniform(-3, 3)
            return self.cal_yaw + self._rng.uniform(28, 42), self.cal_pitch + self._rng.uniform(6, 14) + noise

    def _looking(self, yaw, pitch):
        if not self.is_calibrated:
            return False
        return (abs(yaw - self.cal_yaw) < self.gz["yaw_threshold_deg"]
                and abs(pitch - self.cal_pitch) < self.gz["pitch_threshold_deg"])

    def _calibrate(self, sec=3.0):
        if self.dry_run:
            sec = 0.5
            self.is_calibrated = True
            self.cal_yaw = 0.0
            self.cal_pitch = 0.0
            db.save_calibration(self.session_id, self.cal_yaw, self.cal_pitch)
            self._json({"type": "calibration", "yaw_center": 0.0, "pitch_center": 0.0})
            self._log("Calibracion instantanea (dry-run)")
            return
        self._log("Calibrando mirada...")
        yaws, pitches = [], []
        deadline = time.time() + sec
        while time.time() < deadline and not self.stop_flag:
            y, p = self._head_pose()
            if y is not None:
                yaws.append(y)
                pitches.append(p)
            self._cam_step()
        if yaws:
            self.cal_yaw = sum(yaws) / len(yaws)
            self.cal_pitch = sum(pitches) / len(pitches)
            self.is_calibrated = True
            db.save_calibration(self.session_id, self.cal_yaw, self.cal_pitch)
            self._json({"type": "calibration",
                        "yaw_center": round(self.cal_yaw, 2),
                        "pitch_center": round(self.cal_pitch, 2)})
            self._log(f"Calibracion: yaw={self.cal_yaw:.1f} pitch={self.cal_pitch:.1f}")
        else:
            self._log("Calibracion fallo: sin rostro")

    def _cam_step(self):
        if self.dry_run:
            time.sleep(1 / 30)
            return
        ok, f = self.cap.read()
        if not ok:
            return
        f = cv2.flip(f, 1)
        ts = int(time.time() * 1000)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        self.det.detect_async(mp_img, ts)
        self._frame(f)

    def _wait(self, sec):
        if self.dry_run:
            sec = max(sec * 0.05, 0.4)
        deadline = time.time() + sec
        while time.time() < deadline and not self.stop_flag:
            self._cam_step()
            time.sleep(1 / 30)

    def _start_stdin_reader(self):
        def _reader():
            buf = ""
            while not self.stop_flag:
                r, _, _ = select.select([sys.stdin], [], [], 0.3)
                if r:
                    buf += sys.stdin.read(1)
                    if "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if line:
                            try:
                                self._handle_stdin_line(line)
                            except Exception as ex:
                                self._dbg(f"stdin handler error: {ex}")
        self._stdin_thread = threading.Thread(target=_reader, daemon=True)
        self._stdin_thread.start()

    def _handle_stdin_line(self, line):
        ev = json.loads(line)
        t = ev.get("type")
        if t == "eval_response":
            self.eval_queue.put(ev)
            self._json({"type": "eval_routed", "value": ev["value"],
                        "latency": ev.get("latency", 0)})
        elif t == "eval_initiative":
            self._log("Iniciativa espontanea registrada")
            db.log_initiative(self.session_id, "iniciativa espontanea")
            self._initiatives_logged += 1
            self._json({"type": "initiative_recorded", "count": self._initiatives_logged})

    def _wait_for_eval(self, timeout):
        dl = time.time() + timeout
        if self.auto_eval:
            delay = self._rng.uniform(2, min(timeout - 1, 8))
            auto_deadline = time.time() + delay
            while time.time() < auto_deadline and not self.stop_flag:
                try:
                    ev = self.eval_queue.get(timeout=0.2)
                    return ev.get("value")
                except queue.Empty:
                    pass
                self._cam_step()
            val = self._rng.random() < 0.7
            self._log(f"[auto-eval] Respuesta: {'correcto' if val else 'incorrecto'}")
            return val
        while time.time() < dl and not self.stop_flag:
            try:
                ev = self.eval_queue.get(timeout=0.2)
                return ev.get("value")
            except queue.Empty:
                pass
            self._cam_step()
        return None

    def _track_ec(self):
        y, p = self._head_pose()
        if y is None:
            return None
        look = self._looking(y, p)
        if look:
            if not self.ec_active:
                self.ec_active = True
                self.ec_start = time.time()
            return True
        if self.ec_active:
            elap = (time.time() - self.ec_start) * 1000
            self.ec_active = False
            if elap >= self.t["oe1_min_duration_ms"]:
                db.log_eye_contact(self.session_id, elap, self.current_phase)
                self._json({"type": "eye_contact", "duration_ms": round(elap, 1),
                            "threshold_ms": self.t["oe1_min_duration_ms"]})
            return False
        return False

    def _gaze_change(self):
        y, _ = self._head_pose()
        if y is None or not self.is_calibrated:
            return False, 0.0
        ch = abs(y - self.cal_yaw)
        return ch > self.gz["joint_attention_yaw_change_deg"], ch

    def run(self):
        db.init_db()
        self._log(f"Sesion #{self.session_id} iniciada")
        self._json({"type": "module4_started", "session_id": self.session_id})
        self._start_stdin_reader()
        for ph in self.phases:
            if self.stop_flag:
                break
            if self.dry_run:
                ph = dict(ph)
                ph["duration_s"] = max(ph["duration_s"] * 0.05, 2)
            self.current_phase = ph["id"]
            self.phase_start = time.time()
            self._json({"type": "phase_change", "phase": ph["id"], "name": ph["name"]})
            fn = getattr(self, f'_p{ph["id"]}', None)
            if fn:
                fn(ph)
        self._cleanup()

    # Phase 0 — Inicio + calibracion
    def _p0(self, ph):
        for t in ph.get("tts", []):
            self._speak(t)
            self._wait(2)
        if ph.get("calibrate"):
            self._calibrate(3.0)
        r = ph["duration_s"] - (time.time() - self.phase_start)
        if r > 0:
            self._wait(r)

    # Phase 1 — Quieto (OE1 + OE5)
    def _p1(self, ph):
        self._log("Fase Quieto: OE1 + OE5")
        self._gesture(ph.get("robot_gesture", 0))
        for t in ph.get("tts", []):
            self._speak(t)
        dl = self.phase_start + ph["duration_s"]
        while time.time() < dl and not self.stop_flag:
            self._cam_step()
            self._track_ec()

    # Phase 2 — Mira (OE1 + OE4)
    def _p2(self, ph):
        self._log("Fase Mira: OE1 + OE4")
        for t in ph.get("tts", []):
            self._speak(t)
        looked = False
        dl = self.phase_start + ph["duration_s"]
        while time.time() < dl and not self.stop_flag:
            self._cam_step()
            lk = self._track_ec()
            if lk and not looked:
                looked = True
                lat = (time.time() - self.phase_start) * 1000
                db.log_response_time(self.session_id, "fase_mira_inicio", lat)
                self._json({"type": "response_time",
                            "stimulus_type": "fase_mira_inicio",
                            "latency_ms": round(lat, 1)})

    # Phase 3 — Senala (OE2 + OE4)
    def _p3(self, ph):
        self._log("Fase Senala: OE2 + OE4")
        intro = ph.get("tts_intro", "")
        if intro:
            self._speak(intro)
            self._wait(2)
        for i, tr in enumerate(ph.get("trials", [])):
            if self.stop_flag:
                break
            n = i + 1
            self._speak(f"Mira {tr['object']}")
            self._wait(0.5)
            self._arm(tr["arm_gesture"])
            self._wait(0.3)
            self._json({"type": "trial_start", "oe": 2, "trial": n, "object": tr["object"]})
            ts = time.time()
            looked = False
            lat = 0
            while (time.time() - ts) < self.gz["joint_attention_window_s"] and not self.stop_flag:
                self._cam_step()
                if not looked:
                    ch, _ = self._gaze_change()
                    if ch:
                        looked = True
                        lat = (time.time() - ts) * 1000
            db.log_joint_attention(self.session_id, n, looked, lat)
            self._json({"type": "trial_result", "oe": 2,
                        "trial": n, "success": looked,
                        "latency_ms": round(lat, 1)})
            if looked:
                db.log_response_time(self.session_id, f"joint_attention_{n}", lat)
            self._wait(2)

    # Phase 4 — Falsa creencia (OE3 + OE4)
    def _p4(self, ph):
        self._log("Fase Falsa Creencia: OE3 + OE4")
        for txt in ph.get("story", []):
            self._speak(txt)
            self._wait(2)
        self._wait(1)
        q = ph.get("question", "")
        self._speak(q)
        qtime = time.time()
        trial_n = 1
        self._json({"type": "trial_start", "oe": 3,
                    "trial": trial_n, "question": q,
                    "options": ph.get("options", [])})
        val = self._wait_for_eval(15)
        lat = (time.time() - qtime) * 1000 if val is not None else 0
        correct = (val is True)
        if val is not None:
            self._log(f"Respuesta: {'correcto' if correct else 'incorrecto'} ({lat:.0f}ms)")
        else:
            self._log("Sin respuesta del evaluador (timeout)")
        db.log_false_belief(self.session_id, trial_n, correct if val is not None else None, lat)
        self._json({"type": "trial_result", "oe": 3,
                    "trial": trial_n, "correct": correct,
                    "answered": val is not None,
                    "latency_ms": round(lat, 1)})

    # Phase 5 — Preguntas (OE4)
    def _p5(self, ph):
        self._log("Fase Preguntas: OE4")
        for i, q in enumerate(ph.get("questions", [])):
            if self.stop_flag:
                break
            self._speak(q)
            self._json({"type": "trial_start", "oe": 4, "trial": i + 1, "question": q})
            qtime = time.time()
            val = self._wait_for_eval(12)
            lat = (time.time() - qtime) * 1000 if val is not None else 0
            if val is not None:
                self._log(f"Respondio a pregunta {i+1} ({lat:.0f}ms)")
            db.log_response_time(self.session_id, f"pregunta_{i+1}", lat)
            self._json({"type": "trial_result", "oe": 4,
                        "trial": i + 1, "answered": val is not None,
                        "latency_ms": round(lat, 1)})

    # Phase 6 — Libre (OE5)
    def _p6(self, ph):
        self._log("Fase Libre: OE5")
        for txt in ph.get("tts", []):
            self._speak(txt)
        dl = self.phase_start + ph["duration_s"]
        next_init = time.time() + self._rng.uniform(5, 15) if self.auto_eval else float("inf")
        while time.time() < dl and not self.stop_flag:
            self._cam_step()
            if self.auto_eval and time.time() >= next_init:
                self._log("[auto-eval] Iniciativa espontanea simulada")
                db.log_initiative(self.session_id, "auto-iniciativa")
                self._initiatives_logged += 1
                self._json({"type": "initiative_recorded", "count": self._initiatives_logged})
                next_init = time.time() + self._rng.uniform(5, 20)

    def _cleanup(self):
        self._log("Rutina finalizada")
        self._json({"type": "module4_stopped", "session_id": self.session_id})
        db.close_session(self.session_id)
        if self.dry_run:
            return
        try:
            self.det.close()
        except Exception:
            pass
        try:
            self.cap.release()
        except Exception:
            pass
        if self.ser:
            self.ser.close()


def main():
    parser = argparse.ArgumentParser(description="Mod4 — Prueba de Campo")
    parser.add_argument("--session-id", type=int, default=None,
                        help="ID de sesion existente (crea una nueva si se omite)")
    parser.add_argument("--serial-port", default="COM6")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simular rutina sin camara ni serial")
    parser.add_argument("--seed", type=int, default=None,
                        help="Semilla RNG para dry-run reproducible")
    parser.add_argument("--auto-eval", action="store_true",
                        help="Responder automaticamente a OE3/OE4 (modo prueba)")
    args = parser.parse_args()

    db.init_db()
    sid = args.session_id
    if sid is None:
        sid = db.create_session("Demo Dry-Run" if args.dry_run else "Demo")
    else:
        try:
            db.init_db()
        except Exception:
            pass

    routine = Mod4Routine(session_id=sid, serial_port=args.serial_port,
                          dry_run=args.dry_run, seed=args.seed,
                          auto_eval=args.auto_eval)
    routine.run()


if __name__ == "__main__":
    main()
