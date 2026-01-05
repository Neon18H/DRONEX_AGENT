import argparse
import os
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response


class FrameSource:
    def __init__(self, camera_index: int, simulation_fps: float = 10.0) -> None:
        self.camera_index = camera_index
        self.simulation_fps = simulation_fps
        self._lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._simulation_mode = False

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2)

    def get_latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def _set_latest(self, jpeg_bytes: bytes) -> None:
        with self._lock:
            self._latest_jpeg = jpeg_bytes

    def _capture_loop(self) -> None:
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self._simulation_mode = True
        else:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        while not self._stop_event.is_set():
            if self._simulation_mode:
                frame = self._simulation_frame()
            else:
                ok, frame = cap.read()
                if not ok:
                    self._simulation_mode = True
                    continue
            ok, buffer = cv2.imencode(".jpg", frame)
            if ok:
                self._set_latest(buffer.tobytes())
            time.sleep(1 / self.simulation_fps)

        if not self._simulation_mode:
            cap.release()

    def _simulation_frame(self) -> np.ndarray:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            "SIMULATION FEED",
            (40, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return frame


app = Flask(__name__)
frame_source: FrameSource | None = None


def mjpeg_stream():
    while True:
        if frame_source is None:
            time.sleep(0.1)
            continue
        jpeg = frame_source.get_latest_jpeg()
        if jpeg is None:
            time.sleep(0.05)
            continue
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"


@app.route("/stream.mjpg")
def stream():
    return Response(
        mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="MJPEG streaming server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MJPEG_PORT", "8080")),
        help="Port to bind the MJPEG server",
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera index")
    parser.add_argument(
        "--fps",
        type=float,
        default=10.0,
        help="Capture rate for simulation/capture loop",
    )
    args = parser.parse_args()

    global frame_source
    frame_source = FrameSource(args.camera, simulation_fps=args.fps)
    frame_source.start()

    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
