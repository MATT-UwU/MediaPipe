#!/usr/bin/env python3
"""
Module 5 — Grasp Detection + YOLO crop: detecta objetos siendo agarrados.

Modos de uso:
  python mod5_grasp_detector.py                  # cámara en vivo
  python mod5_grasp_detector.py --video ruta.mp4  # video grabado
  python mod5_grasp_detector.py --debug           # overlay verbose
"""

import argparse
import json
import math
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from ultralytics import YOLO

import tea_object_emotion as m5

BASE_DIR = Path(__file__).parent
FRAME_FILE = Path(tempfile.gettempdir()) / "tea_module5_frame.jpg"
JPEG_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, 72]
JPEG_PARAMS_ANNOT = [cv2.IMWRITE_JPEG_QUALITY, 85]

SERIAL_PORT = "COM6"
BAUD_RATE = 9600

OBJETOS = m5.OBJETOS_CONFIG
EMO_A_CARA = m5.EMOCION_A_GESTO_CARA

HAND_MODEL_NAME = "hand_landmarker.task"
HAND_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)

COOLDOWN = 2.0
CROP_MARGIN = 0.70
CONF_THRESHOLD = 0.25
CONF_REACT = 0.35
CROP_SIZE = 640


class TTS:
    def __init__(self):
        self._engine = None
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 160)
        except Exception:
            pass

    def speak(self, text):
        if self._engine:
            self._engine.say(text)
            self._engine.runAndWait()
        else:
            print(f"[TTS] {text}", file=sys.stderr, flush=True)


class GraspClassifier:
    FIST = "fist"
    PINCH = "pinch"
    PALM = "palm"
    OPEN = "open"
    NONE = "none"

    FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"]
    TIPS_MCP = [(4, 2), (8, 5), (12, 9), (16, 13), (20, 17)]

    def classify(self, landmarks, w, h):
        hand_size = self._hand_size(landmarks, w, h)
        if hand_size < 1:
            return self.NONE, {}

        tip_dists = []
        tip_positions = []
        for tip_idx, mcp_idx in self.TIPS_MCP:
            tip = (landmarks[tip_idx].x * w, landmarks[tip_idx].y * h)
            mcp = (landmarks[mcp_idx].x * w, landmarks[mcp_idx].y * h)
            d = math.dist(tip, mcp) / hand_size
            tip_dists.append(d)
            tip_positions.append(tip)

        thumb_tip = tip_positions[0]
        index_tip = tip_positions[1]
        thumb_index_dist = math.dist(thumb_tip, index_tip) / hand_size

        details = {
            "tip_dists": tip_dists,
            "thumb_index_dist": thumb_index_dist,
            "hand_size": hand_size,
        }

        all_curled = all(d < 0.35 for d in tip_dists)
        all_extended = all(d > 0.45 for d in tip_dists)
        thumb_index_close = thumb_index_dist < 0.15
        others_curled = all(d < 0.40 for d in tip_dists[2:])

        if all_curled:
            return self.FIST, details
        if thumb_index_close and others_curled:
            return self.PINCH, details
        if all_extended:
            return self.PALM, details
        return self.OPEN, details

    @staticmethod
    def _hand_size(landmarks, w, h):
        wrist = (landmarks[0].x * w, landmarks[0].y * h)
        mcp_mid = (landmarks[9].x * w, landmarks[9].y * h)
        return math.dist(wrist, mcp_mid)


def crop_hand_roi(frame, landmarks, w, h, margin=CROP_MARGIN):
    xs = [lm.x * w for lm in landmarks]
    ys = [lm.y * h for lm in landmarks]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    side = max(max(xs) - min(xs), max(ys) - min(ys)) * (1 + margin)
    x1 = int(max(cx - side / 2, 0))
    y1 = int(max(cy - side / 2, 0))
    x2 = int(min(cx + side / 2, w))
    y2 = int(min(cy + side / 2, h))
    roi = frame[y1:y2, x1:x2]
    return roi, (x1, y1, x2, y2)


def download_model(path, url):
    if not os.path.exists(path):
        print(f"Descargando {path}...", file=sys.stderr)
        try:
            urllib.request.urlretrieve(url, path)
        except Exception as e:
            print(f"Fallo descarga {path}: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Mod5 — Grasp + YOLO crop")
    parser.add_argument("--video", default=None, help="Ruta de video (opcional)")
    parser.add_argument("--debug", action="store_true", help="Overlay verbose")
    args = parser.parse_args()

    hand_model_path = str(BASE_DIR / HAND_MODEL_NAME)
    download_model(hand_model_path, HAND_URL)

    yolo = YOLO("yolo11s.pt")
    tts = TTS()

    hand_base = python.BaseOptions(model_asset_path=hand_model_path)
    hand_latest = [None]

    def hand_cb(result, out_img, ts):
        hand_latest[0] = result

    hand_opts = vision.HandLandmarkerOptions(
        base_options=hand_base,
        running_mode=vision.RunningMode.LIVE_STREAM,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_tracking_confidence=0.4,
        result_callback=hand_cb,
    )
    hand_det = vision.HandLandmarker.create_from_options(hand_opts)

    ser = None
    try:
        import serial
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        time.sleep(2)
        ser.reset_input_buffer()
        print(f"[mod5] Serial {SERIAL_PORT} abierto", file=sys.stderr)
    except Exception as e:
        print(f"[mod5] Serial no disponible: {e}", file=sys.stderr)

    if args.video:
        cap = cv2.VideoCapture(args.video)
        print(f"[mod5] Leyendo video: {args.video}", file=sys.stderr)
    else:
        cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("[mod5] ERROR: no se pudo abrir camara/video", file=sys.stderr)
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30

    last_detect_t = 0.0
    last_object = None
    last_grasp = GraspClassifier.NONE
    grasp_cls = GraspClassifier()
    debug = args.debug
    frame_idx = 0

    running = True
    while running:
        ok, frame = cap.read()
        if not ok:
            if args.video:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            time.sleep(0.02)
            continue

        frame_idx += 1
        if args.video and frame_idx % max(int(fps / 10), 1) != 0:
            continue

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        ts = int(time.time() * 1000)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        hand_det.detect_async(mp_img, ts)

        hr = hand_latest[0]
        hand_present = hr is not None and hr.hand_landmarks
        grasp_type = GraspClassifier.NONE
        grasp_details = {}
        roi_rect = None

        if hand_present:
            lm = hr.hand_landmarks[0]
            grasp_type, grasp_details = grasp_cls.classify(lm, w, h)
            last_grasp = grasp_type

            for i in range(21):
                x = int(lm[i].x * w)
                y = int(lm[i].y * h)
                cv2.circle(frame, (x, y), 3, (0, 200, 255), -1)

            if grasp_type in (GraspClassifier.FIST, GraspClassifier.PINCH, GraspClassifier.PALM):
                roi, roi_rect = crop_hand_roi(frame, lm, w, h)
                if roi.size > 0:
                    roi_resized = cv2.resize(roi, (CROP_SIZE, CROP_SIZE))
                    det_start = time.time()
                    results = yolo(roi_resized, conf=CONF_THRESHOLD, iou=0.45, verbose=False)
                    det_time = (time.time() - det_start) * 1000

                    all_boxes = []
                    if results and len(results[0].boxes) > 0:
                        x1_roi, y1_roi, x2_roi, y2_roi = roi_rect
                        for box in results[0].boxes:
                            conf = float(box.conf[0])
                            cls_id = int(box.cls[0])
                            name = results[0].names.get(cls_id, "").lower()
                            x1c, y1c, x2c, y2c = box.xyxyn[0].tolist()
                            all_boxes.append({
                                "name": name,
                                "conf": conf,
                                "box": (
                                    int(x1_roi + x1c * (x2_roi - x1_roi)),
                                    int(y1_roi + y1c * (y2_roi - y1_roi)),
                                    int(x1_roi + x2c * (x2_roi - x1_roi)),
                                    int(y1_roi + y2c * (y2_roi - y1_roi)),
                                ),
                            })

                    if all_boxes and debug:
                        overlay = frame.copy()
                        for b in all_boxes:
                            x1b, y1b, x2b, y2b = b["box"]
                            alpha = min(b["conf"] + 0.2, 0.6)
                            c = (0, 200, 255) if b["name"] in OBJETOS else (100, 100, 100)
                            cv2.rectangle(overlay, (x1b, y1b), (x2b, y2b), c, int(alpha * 3))
                            label = f"{b['name']} {b['conf']:.0%}"
                            cv2.putText(overlay, label, (x1b + 3, y1b - 5),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1)
                        frame = cv2.addWeighted(overlay, 0.3, frame, 0.7, 0)

                    best = max(all_boxes, key=lambda b: b["conf"]) if all_boxes else None

                    if best and best["conf"] >= CONF_REACT:
                        now = time.time()
                        is_new = best["name"] != last_object
                        is_cooldown = (not is_new) and (now - last_detect_t) < COOLDOWN

                        if not is_cooldown:
                            last_object = best["name"]
                            last_detect_t = now
                            info = OBJETOS.get(best["name"], {})
                            color = (0, 255, 0)
                            reaction = None

                            if info:
                                emotion = info.get("emocion", "neutral")
                                arm_gesture = info.get("gesto_brazo", "CHECK")
                                phrase = info.get("frase", f"Un {best['name']}")
                                color = info.get("color", (0, 255, 0))
                                gesture_id = EMO_A_CARA.get(emotion, 0)
                                arm_cmd = "OK\n" if arm_gesture == "CHECK" else "NO\n"

                                if ser:
                                    ser.write(f"{gesture_id}\n".encode())
                                    time.sleep(0.05)
                                    ser.write(arm_cmd.encode())

                                tts.speak(phrase)

                                reaction = {
                                    "emotion": emotion,
                                    "arm_gesture": arm_gesture,
                                    "face_gesture": gesture_id,
                                    "phrase": phrase,
                                }

                                print(json.dumps({
                                    "type": "grasp_detection",
                                    "object": best["name"],
                                    "confidence": round(best["conf"], 3),
                                    "grasp": grasp_type,
                                    **reaction,
                                    "detection_ms": round(det_time, 1),
                                }), flush=True)
                            else:
                                print(json.dumps({
                                    "type": "grasp_raw",
                                    "object": best["name"],
                                    "confidence": round(best["conf"], 3),
                                    "grasp": grasp_type,
                                    "detection_ms": round(det_time, 1),
                                }), flush=True)

                            x1b, y1b, x2b, y2b = best["box"]
                            cv2.rectangle(frame, (x1b, y1b), (x2b, y2b), color, 3)
                            label = f"{best['name']} {best['conf']:.0%}"
                            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                            cv2.rectangle(frame,
                                          (x1b, y1b - th - 8),
                                          (x1b + tw + 8, y1b), color, -1)
                            cv2.putText(frame, label, (x1b + 4, y1b - 6),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

                    if roi_rect:
                        x1, y1, x2, y2 = roi_rect
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                        cv2.putText(frame, "CROP", (x1 + 4, y1 + 18),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        y_off = 30
        gesture_label = {
            GraspClassifier.FIST: "PUÑO",
            GraspClassifier.PINCH: "PINZA",
            GraspClassifier.PALM: "PALMA",
            GraspClassifier.OPEN: "ABIERTA",
            GraspClassifier.NONE: "—",
        }.get(grasp_type, "—")
        cv2.putText(frame, f"Mano: {gesture_label}", (10, y_off),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        y_off += 28

        if last_object:
            cv2.putText(frame, f"Obj: {last_object}", (10, y_off),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            y_off += 24

        if debug and grasp_details.get("tip_dists"):
            for i, d in enumerate(grasp_details["tip_dists"]):
                name = GraspClassifier.FINGER_NAMES[i]
                cv2.putText(frame, f"  {name}: {d:.2f}", (10, y_off),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                            (0, 255, 0) if d > 0.45 else (0, 0, 255), 1)
                y_off += 18
            tix = grasp_details.get("thumb_index_dist", 0)
            cv2.putText(frame, f"  thumb-idx: {tix:.2f}", (10, y_off),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 255, 0) if tix < 0.15 else (0, 0, 255), 1)
            y_off += 18

        if debug:
            cv2.putText(frame, "DEBUG", (w - 80, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        try:
            ret, buf = cv2.imencode(".jpg", frame, JPEG_PARAMS_ANNOT)
            if ret:
                FRAME_FILE.write_bytes(buf.tobytes())
        except Exception:
            pass

        cv2.imshow("Mod5 - Grasp Detection", frame)
        key = cv2.waitKey(1 if not args.video else int(1000 / fps)) & 0xFF
        if key == 27:
            running = False
        elif key == ord("d"):
            debug = not debug
            print(f"[mod5] Debug: {'ON' if debug else 'OFF'}", file=sys.stderr)

    hand_det.close()
    cap.release()
    cv2.destroyAllWindows()
    if ser:
        ser.close()
    print(json.dumps({"type": "module5_stopped"}), flush=True)


if __name__ == "__main__":
    main()
