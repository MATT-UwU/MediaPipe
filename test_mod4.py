#!/usr/bin/env python3
"""Test rápido del Módulo 4 — sin hardware."""
import sys
import os
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0

def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name} {detail}")
        FAIL += 1

print("=" * 56)
print("  Test Módulo 4 — Prueba de Campo")
print("=" * 56)

# 1. tracking_db
print("\n[tracking_db]")
import tracking_db as db
db.init_db()
check("init_db crea tablas", os.path.exists("tracking.db"))

sid = db.create_session("Test")
check("create_session() returns ID", sid > 0)

db.log_eye_contact(sid, 3200, phase=1)
db.log_eye_contact(sid, 4100, phase=2)
db.log_joint_attention(sid, trial=1, success=True, latency_ms=1500)
db.log_joint_attention(sid, trial=2, success=False, latency_ms=0)
db.log_false_belief(sid, trial=1, correct=True, latency_ms=2100)
db.log_false_belief(sid, trial=2, correct=False, latency_ms=1800, error_pattern="distractor")
db.log_response_time(sid, "pregunta_1", 1200)
db.log_response_time(sid, "pregunta_2", 950)
db.log_initiative(sid, "toco el brazo")
db.save_calibration(sid, yaw_center=2.5, pitch_center=-1.0)

summary = db.get_session_summary(sid)
check("summary tiene session", "session" in summary)
check("summary OE1 avg ~3.65s", abs(summary["oe1"]["avg_duration_s"] - 3.65) < 0.01)
check("summary OE3 accuracy 0.5", summary["oe3"]["accuracy"] == 0.5)

db.close_session(sid)
sessions = db.get_sessions()
check("get_sessions() > 0", len(sessions) >= 1)

cross = db.get_cross_session_summary()
check("cross_session_summary OK", len(cross) >= 1)

print(f"\n[tracking_db] {PASS}/{PASS+FAIL} passed")

# 2. Math helpers
print("\n[head_pose math]")
from run_module4 import compute_yaw, compute_pitch

# Identity matrix → 0 yaw, 0 pitch
y = compute_yaw([1,0,0, 0,1,0, 0,0,1])
p = compute_pitch([1,0,0, 0,1,0, 0,0,1])
check("identity yaw ≈ 0", abs(y) < 0.01)
check("identity pitch ≈ 0", abs(p) < 0.01)

# Looking 45° left
y = compute_yaw([0.707,0,-0.707, 0,1,0, 0.707,0,0.707])
check("45° yaw ≈ ±45", abs(abs(y) - 45) < 2)

# 3. Database queries via REST (start server in background)
print("\n[REST API]")
import subprocess, json, urllib.request, urllib.error

server_proc = subprocess.Popen(
    [sys.executable, "server.py"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    start_new_session=True,
)
time.sleep(2)

try:
    r = urllib.request.urlopen("http://localhost:8000/api/status", timeout=3)
    status = json.loads(r.read())
    check("GET /api/status OK", status.get("active_module") is None)

    r = urllib.request.urlopen("http://localhost:8000/api/sessions", timeout=3)
    ses = json.loads(r.read())
    check("GET /api/sessions OK", isinstance(ses, list))

    r = urllib.request.urlopen("http://localhost:8000/api/dashboard", timeout=3)
    dash = json.loads(r.read())
    check("GET /api/dashboard OK", isinstance(dash, list))

    # Clean up — POST /api/sessions/close in case session open
    try:
        req = urllib.request.Request("http://localhost:8000/api/sessions/close",
                                     method="POST",
                                     data=b"{}",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req)
    except Exception:
        pass

except Exception as e:
    check(f"server reachable on :8000", False, str(e))
finally:
    server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except Exception:
        pass

# 4. Frontend build (already verified)
print("\n[frontend]")
check("vite build OK", os.path.exists("web/dist/index.html"))
check("dist JS exists", any(f.endswith(".js") for f in os.listdir("web/dist/assets/")))

print(f"\n{'=' * 56}")
print(f"  Total: {PASS} passed, {FAIL} failed")
print(f"{'=' * 56}")

# Cleanup test DB
os.remove("tracking.db")
sys.exit(0 if FAIL == 0 else 1)
