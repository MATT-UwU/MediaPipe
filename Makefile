# ─────────────────────────────────────────────────────────
#   MediaPipeHELL — Makefile
#   Usage: make <target> [ARGS="..."]
# ─────────────────────────────────────────────────────────
PYTHON    := uv run python
SERIAL_DEF := /dev/ttyUSB0

# ── Ayuda ─────────────────────────────────────────────────
.DEFAULT_GOAL := help
.PHONY: help
help:
	@echo 'Uso: make <target> [ARGS="..."]'
	@echo ''
	@echo '── Servidor ──'
	@echo '  server            Inicia backend FastAPI (todos los módulos)'
	@echo ''
	@echo '── Web ──'
	@echo '  web               Inicia frontend de desarrollo (Vite)'
	@echo '  web-build         Compila frontend para producción'
	@echo ''
	@echo '── Módulo 1 — Reconocimiento de Objetos ──'
	@echo '  mod1              Objetos + emociones + robot'
	@echo ''
	@echo '── Módulo 2 — Reacción Duplicada ──'
	@echo '  mod2              Pipeline completo (cara → gesto → serial)'
	@echo '  face-gesture      face_capture | classify_gesture | gesture_serial'
	@echo '  face-stream       face_capture | set_directions | serial_bridge'
	@echo ''
	@echo '── Módulo 2 — Pose ──'
	@echo '  pose-gesture      pose_capture | classify_gesture | gesture_serial'
	@echo '  pose-stream       pose_capture | set_directions | serial_bridge'
	@echo ''
	@echo '── Módulo 3 — Lazo Cerrado (PID) ──'
	@echo '  feedback          PID con 2 cámaras (valores por defecto)'
	@echo '  feedback-cam      PID con índices de cámara explicitos'
	@echo '  feedback-tune     PID con ganancias custom'
	@echo ''
	@echo '── Módulo 4 — Prueba de Campo ──'
	@echo '  mod4              Rutina estructurada (5 OEs) via web'
	@echo '  mod4-dry          Dry-run sin cámara ni robot'
	@echo ''
	@echo '── Módulo 5 — Grasp + YOLO Crop ──'
	@echo '  mod5              Deteccion por agarre (camara en vivo)'
	@echo '  mod5-debug        Modo debug (overlay distancias dedos)'
	@echo '  mod5-video        Probar con video (VIDEO=ruta.mp4)'
	@echo ''
	@echo '── Utilidades ──'
	@echo '  classify          Solo clasificador (pipe stdin → stdout)'
	@echo '  bridge            serial_bridge standalone'
	@echo '  test-pipeline     Genera datos de prueba para el pipeline'
	@echo '  clean             Limpia capturas, frames temporales, caches'
	@echo '  lint              Verifica sintaxis de todos los .py'
	@echo '  help              Muestra esta ayuda'
	@echo ''
	@echo '── Flags comunes ──'
	@echo '  ARGS="..."        Argumentos extra para el script'
	@echo '  SERIAL_PORT=...   Puerto serial (def: $(SERIAL_DEF))'
	@echo ''
	@echo 'Ejemplos:'
	@echo '  make feedback ARGS="--camera-a 2 --camera-b 3"'
	@echo '  make face-gesture SERIAL_PORT=COM6'
	@echo '  make mod2'

# ── Servidor ──────────────────────────────────────────────
server: .uv-ready
	$(PYTHON) server.py

# ── Web ───────────────────────────────────────────────────
web:
	cd web && npm run dev

web-build:
	cd web && npm run build

# ── Módulo 1 ──────────────────────────────────────────────
mod1: .uv-ready
	$(PYTHON) server.py &
	@echo "Backend iniciado. Abre http://localhost:8000"
	@echo "Selecciona 'Reconocimiento de Objetos' en la interfaz."

# ── Módulo 2: Face ────────────────────────────────────────
face-gesture: .uv-ready
	$(PYTHON) face_capture.py \
	| $(PYTHON) classify_gesture.py \
	| $(PYTHON) gesture_serial.py $(ARGS)

face-stream: .uv-ready
	$(PYTHON) face_capture.py \
	| $(PYTHON) set_directions.py \
	| $(PYTHON) serial_bridge.py $(ARGS)

mod2: .uv-ready
	$(PYTHON) run_face_capture.py \
	| $(PYTHON) classify_gesture.py \
	| $(PYTHON) gesture_serial.py $(ARGS)

# ── Módulo 2: Pose ────────────────────────────────────────
pose-gesture: .uv-ready
	$(PYTHON) pose_capture.py \
	| $(PYTHON) classify_gesture.py \
	| $(PYTHON) gesture_serial.py $(ARGS)

pose-stream: .uv-ready
	$(PYTHON) pose_capture.py \
	| $(PYTHON) set_directions.py \
	| $(PYTHON) serial_bridge.py $(ARGS)

# ── Módulo 3 ──────────────────────────────────────────────
feedback: .uv-ready
	$(PYTHON) visual_feedback_controller.py $(ARGS)

feedback-cam:
	$(PYTHON) visual_feedback_controller.py --camera-a 0 --camera-b 1 $(ARGS)

feedback-tune:
	$(PYTHON) visual_feedback_controller.py --kp 0.8 --ki 0.05 --kd 0.1 $(ARGS)

# ── Módulo 4 ──────────────────────────────────────────────
mod4: .uv-ready
	$(PYTHON) server.py &
	@echo "Backend iniciado. Abre http://localhost:8000"
	@echo "Selecciona 'Prueba de Campo' en la interfaz."

mod4-dry: .uv-ready
	$(PYTHON) run_module4.py --dry-run --seed 42 --auto-eval $(ARGS)

# ── Módulo 5 ──────────────────────────────────────────────
mod5: .uv-ready
	$(PYTHON) mod5_grasp_detector.py $(ARGS)

mod5-debug: .uv-ready
	$(PYTHON) mod5_grasp_detector.py --debug $(ARGS)

mod5-video: .uv-ready
	$(PYTHON) mod5_grasp_detector.py --video $(VIDEO) $(ARGS)

# ── Utilidades ────────────────────────────────────────────
classify: .uv-ready
	$(PYTHON) classify_gesture.py

bridge: .uv-ready
	$(PYTHON) serial_bridge.py

test-pipeline: .uv-ready
	$(PYTHON) test_pipeline.py

clean:
	rm -rf captures/
	rm -f /tmp/tea_module*_frame.jpg /tmp/tea_module*_frame.tmp
	rm -rf web/dist/
	rm -rf __pycache__ */__pycache__
	@echo "Limpieza completada."

lint:
	@echo "Verificando sintaxis..."
	@ok=1; for f in *.py; do \
		python3 -c "import ast; ast.parse(open('$$f').read())" 2>/dev/null \
		|| { echo "  ERROR: $$f"; ok=0; }; \
	done; \
	if [ $$ok = 1 ]; then echo "  Todo correcto."; else exit 1; fi

# ── Verificación interna ─────────────────────────────────
.uv-ready:
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "ERROR: 'uv' no encontrado. Instala https://docs.astral.sh/uv/"; \
		exit 1; \
	fi
	@if [ ! -d ".venv" ]; then \
		echo "Entorno .venv no encontrado. Ejecuta 'uv sync' primero."; \
		exit 1; \
	fi
