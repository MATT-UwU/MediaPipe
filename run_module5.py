#!/usr/bin/env python3
"""
Wrapper de mod5_grasp_detector.py: configura COM6 y captura frames para stream web.
mod5_grasp_detector.py NO se modifica.
"""
import sys
import time
import pathlib
import tempfile
import traceback
import threading
import cv2

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

_FRAME_FILE  = pathlib.Path(tempfile.gettempdir()) / "tea_module5_frame.jpg"
_PARAMS      = [cv2.IMWRITE_JPEG_QUALITY, 72]
_last_annot  = 0.0

def _write_frame(mat, annotated=False):
    global _last_annot
    try:
        ret, buf = cv2.imencode('.jpg', mat, _PARAMS)
        if ret:
            _FRAME_FILE.write_bytes(buf.tobytes())
            if annotated:
                _last_annot = time.time()
    except Exception:
        pass

_OrigVC = cv2.VideoCapture

class _VCWrapper:
    def __init__(self, *args, **kwargs):
        self._c      = _OrigVC(*args, **kwargs)
        self._latest = None
        self._run    = False
        self._thread = None
        self._lock   = threading.Lock()

    def _loop(self):
        while self._run:
            with self._lock:
                ret, frame = self._c.read()
            if ret and frame is not None:
                self._latest = frame
                if time.time() - _last_annot > 0.5:
                    _write_frame(frame)
            else:
                time.sleep(0.02)

    def _ensure_thread(self):
        if not self._run:
            self._run    = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            for _ in range(150):
                if self._latest is not None:
                    break
                time.sleep(0.02)

    def read(self):
        self._ensure_thread()
        frame = self._latest
        if frame is not None:
            return True, frame
        with self._lock:
            ret, frame = self._c.read()
        if ret and frame is not None:
            self._latest = frame
            _write_frame(frame)
        return ret, frame

    def set(self, propId, value, *args, **kw):
        if propId == cv2.CAP_PROP_FRAME_WIDTH:
            value = 640
        elif propId == cv2.CAP_PROP_FRAME_HEIGHT:
            value = 480
        return self._c.set(propId, value, *args, **kw)

    def get(self, *args, **kw):    return self._c.get(*args, **kw)
    def isOpened(self):            return self._c.isOpened()
    def release(self):
        self._run = False
        return self._c.release()
    def grab(self):                return self._c.grab()
    def retrieve(self, *a, **kw):  return self._c.retrieve(*a, **kw)
    def __getattr__(self, n):      return getattr(self._c, n)


cv2.VideoCapture      = _VCWrapper
cv2.imshow            = lambda winname, mat: _write_frame(mat, annotated=True)
cv2.waitKey           = lambda _=1: 0
cv2.destroyAllWindows = lambda: None
cv2.destroyWindow     = lambda _: None

try:
    import mod5_grasp_detector as m
    m.SERIAL_PORT = "COM6"
    m.main()
    print("[run_module5] main() terminó normalmente", file=sys.stderr, flush=True)
except Exception:
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
