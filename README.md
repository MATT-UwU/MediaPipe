# Sistema TEA — Aprendizaje Socioemocional con Robot Animatrónico

Sistema de reconocimiento de objetos y expresión facial para un robot animatrónico,
diseñado para trabajar habilidades socioemocionales en niños con TEA (Trastorno del Espectro Autista).

## Arquitectura del Sistema

```
                    ┌───────────────────────────────────────────┐
                    │          Frontend Web (React + Vite)      │
                    │          localhost:5173 (dev)             │
                    │          localhost:8000  (prod)           │
                    └──────────────────┬────────────────────────┘
                                       │ WebSocket + REST API
                    ┌──────────────────▼────────────────────────┐
                    │         Backend (FastAPI + Python 3.11)   │
                    │         server.py — localhost:8000        │
                    │                                           │
                    │  ┌────────┐ ┌─────────┐ ┌────────────┐   │
                    │  │ Mód. 1 │ │ Mód. 2  │ │  Mód. 3    │   │
                    │  │ YOLO   │ │MediaPipe│ │Lazo Cerrado│   │
                    │  │ Objetos│ │Rostro   │ │PID + 2 cams│   │
                    │  ├────────┤ ├─────────┤ ├────────────┤   │
                    │  │ Mód. 4 │ │ Mód. 5  │ │             │   │
                    │  │Prueba  │ │Grasp +  │ │             │   │
                    │  │Campo   │ │YOLO crop│ │             │   │
                    │  └────────┘ └─────────┘ └────────────┘   │
                    └──────────────────┬────────────────────────┘
                                       │ Serial (9600 baud)
                    ┌──────────────────▼────────────────────────┐
                    │         Arduino Uno + PCA9685             │
                    │         Servos × 6+ (cara + brazos)       │
                    └───────────────────────────────────────────┘
```

## Hardware Requerido

| Componente             | Especificación                           |
|------------------------|------------------------------------------|
| Cámara A (escena)      | Webcam USB 720p mínimo (índice 0)        |
| Cámara B (robot)       | Webcam USB 720p mínimo (índice 1)        |
| Microcontrolador       | Arduino Uno (o compatible)               |
| Driver PWM             | PCA9685 (módulo I2C)                     |
| Servos cara            | 6 servos (mandíbula, cejas, ojos, boca)  |
| Servo brazo            | 1 servo (CHECK / DESAPRUEBO)             |
| PC                     | Linux o Windows, CPU con AVX (YOLO v11)  |

> El Módulo 1 funciona con 1 cámara. El Módulo 2 funciona con 1 cámara.
> El Módulo 3 requiere **2 cámaras** (una apuntando a la persona, otra al robot).
> El Módulo 4 funciona con 1 cámara (enfocando al niño).
> El Módulo 5 funciona con 1 cámara (enfocando las manos del niño).

## Instalación

### 1. Clonar e instalar dependencias

```bash
git clone <repo>
cd MediaPipeHELL
uv sync                 # instala el entorno virtual con todas las dependencias
```

### 2. Verificar modelo MediaPipe

El modelo `face_landmarker_v2_with_blendshapes.task` (~10 MB) se descarga
automáticamente la primera vez que se ejecuta cualquier módulo que lo requiera.

### 3. Verificar modelo YOLO

YOLO v11 descarga `yolo11s.pt` automáticamente al iniciar el Módulo 1.

### 4. (Opcional) Compilar frontend

```bash
cd web
npm install
npm run build          # produce dist/
```

En desarrollo, usar `npm run dev` (Vite en puerto 5173).

## Uso

### Servidor backend (siempre necesario)

```bash
# Linux / WSL
.venv/bin/python server.py
make server

# Windows (PowerShell)
.\make.ps1 server
# o directamente
uv run python server.py
```

Esto levanta:
- **API REST** en `http://localhost:8000`
- **WebSocket** en `ws://localhost:8000/ws`
- **Streams MJPEG** en `/stream/1` a `/stream/5`

### Interfaz web

```bash
cd web
npm run dev            # desarrollo (proxy al backend)
# o abre http://localhost:8000 en el navegador (frontend servido por FastAPI)
```

## Módulos

### Módulo 1 — Reconocimiento de Objetos

```bash
make mod1     # lanza el backend internamente
# o desde la web: selecciona "Reconocimiento de Objetos"
```

- **Modelo**: YOLO v11 (`yolo11s.pt`)
- **Pipeline**: `server.py` → `run_module1.py` → `tea_object_emotion.py`
- **Detecta**: 30+ objetos (manzana, libro, tijeras, pelota, etc.)
- **Reacciona**: asigna emoción al objeto detectado y envía gesto al robot
- **Capturas**: guarda automáticamente la reacción del objeto detectado

**Mapeo objeto → emoción** (parcial):

| Objetos               | Emoción  | Gesto brazo |
|-----------------------|----------|-------------|
| apple, banana, book   | feliz    | CHECK       |
| knife, scissors, gun  | miedo    | DESAPRUEBO  |
| battery, trash        | enojo    | DESAPRUEBO  |
| clock, vase, balloon  | asombro  | CHECK       |
| bottle, cup, spoon    | neutral  | CHECK       |

**Entrenamiento personalizado**: presiona `t` en la ventana YOLO para entrenar
un detector de objetos de enojo (pilas, vidrio roto) tras capturar 10-20 muestras.

### Módulo 2 — Reacción Duplicada

```bash
make mod2     # lanza el backend internamente
# o desde la web: selecciona "Reacción Duplicada"
```

- **Modelo**: MediaPipe FaceLandmarker (LIVE_STREAM)
- **Pipeline**: `run_face_capture.py` → `classify_gesture.py` → `gesture_serial.py`
- **Blendshapes**: 52 coeficientes ARKit (jawOpen, browInnerUp, eyeBlinkLeft, etc.)
- **Gestos clasificados**: sonrisa, ceño, sorpresa, párpados, etc.
- **Salida serial**: número de gesto (`0\n`–`10\n`), Arduino ejecuta la expresión

### Módulo 3 — Lazo Cerrado (PID)

```bash
make feedback  # lanza servidor + visual_feedback_controller
# o desde la web: selecciona "Lazo Cerrado"
```

- **Modelo**: MediaPipe FaceLandmarker (IMAGE — síncrono)
- **Control**: PID digital sobre `jawOpen`
- **2 cámaras**: cámara A = referencia humana, cámara B = robot
- **Documentación detallada**: ver [control.md](control.md)

```python
# PID: valores por defecto ajustables por flag
Kp=0.8, Ki=0.05, Kd=0.1
```

### Módulo 4 — Prueba de Campo (Evaluación Estructurada)

```bash
# Desde la web: selecciona "Prueba de Campo"
# O en modo autónomo (sin frontend):
.venv/bin/python run_module4.py --dry-run --seed 42 --auto-eval
```

- **Modelo**: MediaPipe FaceLandmarker (head pose yaw/pitch)
- **Pipeline**: `server.py` → `run_module4.py` → `tracking_db.py`
- **Duración**: ~15 min (7 fases: inicio, quieto, mira, señala, falsa creencia, preguntas, libre)
- **Mide 5 objetivos (OE)**:

| OE | Métrica | Método |
|----|---------|--------|
| OE1 | Contacto visual sostenido | Head pose (yaw/pitch) ventana 3s |
| OE2 | Atención conjunta | Cambio de mirada post-señalamiento |
| OE3 | Falsa creencia | Respuesta del evaluador (botones C/X) |
| OE4 | Tiempo de reacción | Latencia de mirada o respuesta |
| OE5 | Iniciativas espontáneas | Registro del evaluador (botón I) |

- **Persistencia**: SQLite (`tracking.db`) con tabla por OE
- **Dashboard web**: 5 cards de progreso + tabla comparativa cross-session
- **Atajos de teclado**: `C` Correcto, `X` Incorrecto, `I` Iniciativa

### Módulo 5 — Detección por Agarre (YOLO en crop de mano)

```bash
# Desde la web: selecciona "Deteccion por Agarre"
# O standalone con cámara:
.venv/bin/python mod5_grasp_detector.py --debug
# Con video grabado:
.venv/bin/python mod5_grasp_detector.py --video ruta.mp4
```

- **Modelos**: MediaPipe HandLandmarker + YOLO v11 (`yolo11s.pt`)
- **Pipeline**: `server.py` → `run_module5.py` → `mod5_grasp_detector.py`
- **Detección de agarre**: clasifica mano como puño, pinza, palma abierta
- **Crop ROI**: recorta área alrededor de la mano (70% margen) y corre YOLO ahí
- **Reacciones**: mismo mapeo objeto→emoción que Módulo 1 (serial + TTS)
- **Modos**:
  - `--debug`: overlay con distancias de dedos y todas las detecciones YOLO
  - `--video path`: prueba con video grabado (loop infinito)
  - Tecla `D`: toggle debug en vivo

## Protocolo Serial

### Módulo 1, 2, 4 y 5 (gestos discretos)

```
cmd = f"{gesture_id}\n"         # gesture_serial.py:60
# gesture_id: 0=neutro, 8=enojo, 9=sorpresa, 10=feliz
```

### Módulo 3 (ángulos continuos)

```
packet = f"${jaw:.2f},0,0,0,0,0#\n"   # visual_feedback_controller.py:107
# Formato: $jaw,smileL,smileR,blinkL,blinkR,yaw#
# jaw en grados [0.0, 20.0]
```

Velocidad: **9600 baud**, 8N1.

### Módulo 3 (legacy bridge)

```
packet = "$" + ";".join(parts) + "#"   # serial_bridge.py:33
# Formato: $key:hex;key:hex;...#  (115200 baud)
```

## Makefile

### Targets principales

| Comando            | Acción                                        |
|--------------------|-----------------------------------------------|
| `make help`        | Muestra ayuda completa con todos los targets  |
| `make server`      | Inicia servidor backend FastAPI               |
| `make web`         | Inicia frontend de desarrollo (Vite)          |
| `make web-build`   | Compila frontend para producción              |

### Módulo 1 — Reconocimiento de Objetos

| Comando | Acción |
|---------|--------|
| `make mod1` | Lanza server + módulo, abre interfaz web |

### Módulo 2 — Reacción Duplicada

| Comando         | Pipeline                                    |
|-----------------|---------------------------------------------|
| `make mod2`     | `run_face_capture` → `classify` → `serial` (wrapper web) |
| `make face-gesture` | `face_capture` → `classify` → `serial` (legacy)    |
| `make face-stream`  | `face_capture` → `set_directions` → `serial_bridge` |
| `make pose-gesture` | `pose_capture` → `classify` → `serial`             |
| `make pose-stream`  | `pose_capture` → `set_directions` → `serial_bridge` |

### Módulo 3 — Lazo Cerrado (PID)

| Comando            | Acción                                      |
|--------------------|---------------------------------------------|
| `make feedback`    | PID con 2 cámaras (valores por defecto)     |
| `make feedback-cam`| Índices de cámara custom                    |
| `make feedback-tune`| Ganancias PID custom                       |

### Módulo 4 — Prueba de Campo

| Comando | Acción |
|---------|--------|
| `make mod4` | Rutina estructurada de 15 min (5 OEs) |
| `make mod4-dry` | Dry-run con auto-eval (sin cámara ni robot) |

### Módulo 5 — Detección por Agarre

| Comando | Acción |
|---------|--------|
| `make mod5` | Grasp + YOLO crop (cámara en vivo) |
| `make mod5-debug` | Modo debug con overlay de distancias |
| `make mod5-video` | Prueba con video (`VIDEO=ruta.mp4`) |

### Utilidades

| Comando             | Acción                                      |
|---------------------|---------------------------------------------|
| `make classify`     | Solo clasificador (pipe stdin → stdout)     |
| `make bridge`       | `serial_bridge` standalone                  |
| `make test-pipeline`| Datos de prueba                             |
| `make clean`        | Capturas, frames temporales, `__pycache__`  |
| `make lint`         | Verifica sintaxis de todos los `.py`        |

### Flags comunes

```bash
ARGS="..."             # Argumentos extra para el script
make feedback ARGS="--camera-a 2 --camera-b 3"
make face-gesture SERIAL_PORT=COM6
make mod5-debug ARGS="--video ruta.mp4"
```

### Windows (PowerShell)

En Windows sin `make`, usa `make.ps1` desde PowerShell:

```powershell
.\make.ps1 help              # Lista todos los targets
.\make.ps1 server            # Inicia backend
.\make.ps1 feedback -ARGS "--camera-a 2 --camera-b 3"
.\make.ps1 face-gesture -SERIAL_PORT COM6
.\make.ps1 mod2
```

También puedes ejecutar los comandos `uv run python` directamente:

```powershell
uv run python server.py
uv run python visual_feedback_controller.py --camera-a 0 --camera-b 1
uv run python face_capture.py | uv run python classify_gesture.py | uv run python gesture_serial.py
```

## Estructura del Proyecto

```
MediaPipeHELL/
├── server.py                       # Backend FastAPI (orquestador)
├── run_module1.py                  # Wrapper Módulo 1 (captura frames YOLO)
├── run_face_capture.py             # Wrapper Módulo 2 (captura frames MediaPipe)
├── visual_feedback_controller.py   # Módulo 3 (PID + 2 cámaras)
├── run_module4.py                  # Orquestador Módulo 4 (rutina 5 OEs)
├── run_module5.py                  # Wrapper Módulo 5 (captura frames grasp)
├── tea_object_emotion.py           # YOLO + emociones (legacy)
├── mod5_grasp_detector.py          # Módulo 5 (HandLandmarker + YOLO crop)
├── face_capture.py                 # MediaPipe FaceLandmarker (LIVE_STREAM)
├── classify_gesture.py             # Clasificador de gestos faciales
├── gesture_serial.py               # Envío serial de gestos
├── tracking_db.py                  # SQLite persistencia (Módulo 4)
├── mod4_routine.json               # Config de rutina Módulo 4
├── robot_face_landmarks.py         # FaceLandmarker en modo IMAGE (Módulo 3)
├── robot_face_state.py             # Mapeo blendshapes → ángulos servo
├── face_gestures_servo.py          # Prototipo original (LIVE_STREAM + serial)
├── set_directions.py               # Mapeo de direcciones (legacy)
├── serial_bridge.py                # Bridge serial a 115200 baud (legacy)
├── test_pipeline.py                # Genera datos de prueba para el pipeline
├── test_mod4.py                    # Tests unitarios Módulo 4 (15 tests)
├── Makefile                        # Comandos de uso común (Linux/WSL)
├── make.ps1                        # Comandos de uso común (Windows PowerShell)
├── control.md                      # Documentación del lazo cerrado (Módulo 3)
├── pyproject.toml                  # Dependencias Python
├── tracking.db                     # Base de datos SQLite (Módulo 4)
├── captures/                       # Capturas automáticas (Módulo 1)
└── web/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx                 # Componente principal React
        ├── App.css                 # Sistema de diseño (tema oscuro)
        ├── Icon.jsx                # Componente de iconos (Font Awesome)
        ├── Dashboard.jsx           # Dashboard OEs (Módulo 4)
        ├── RobotView.jsx           # Vista del robot (Módulo 4)
        └── Module5View.jsx         # Vista grasp detection (Módulo 5)

## Solución de Problemas

| Problema                     | Causa probable                         | Solución                                      |
|------------------------------|----------------------------------------|-----------------------------------------------|
| `SerialException`            | Puerto ocupado (Arduino IDE abierto)   | Cerrar Serial Monitor, verificar `/dev/ttyUSB0`|
| Cámara no abre               | Índice incorrecto                      | Probar `--camera-a 1 --camera-b 0`            |
| PID no corrige               | Cámara B no ve al robot                | Asegurar rostro del robot en cuadro            |
| Backend crashea al detener   | Falta `start_new_session` (fixed)      | `git pull`, actualizar server.py               |
| YOLO lento                   | CPU sin AVX                            | Usar modelo más pequeño (`yolo11n.pt`)         |
| `uv sync` falla              | Python < 3.9                           | Actualizar Python                              |

## Licencia

```
Derechos reservados — Proyecto académico
Osea usalo, pero ya pues.
```
