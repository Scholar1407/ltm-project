"""
Smoke Alert Protocol (SAP) - Detection to Network Bridge
Course: Network Programming (LTM)
Specification: prompt/smoke-alert-protocol-spec.md Section 9

Bridges YOLOv8s-P2 smoking detector with SmokeAlertSender:
- Loads model once at startup (model/weights/smoke_p2/best.pt)
- Prevents alert flooding with event-based cooldown (8 seconds)
- Decouples video inference loop from network I/O via thread-safe queue.Queue
"""

from __future__ import annotations
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union
import cv2
import numpy as np

try:
    from .sender import SmokeAlertSender
except (ImportError, ValueError):
    from network.sender.sender import SmokeAlertSender

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL_PATH = BASE_DIR / "model" / "weights" / "smoke_p2" / "best.pt"

# Tuning parameters per Section 9
DEFAULT_CONF_THRESHOLD = 0.5
DEFAULT_COOLDOWN_SECONDS = 8.0

FrameCallback = Callable[[np.ndarray, List[dict]], None]
AlertTriggerCallback = Callable[[int, str, float], None]


class DetectorBridge:
    """
    Connects OpenCV video stream, YOLOv8s-P2 detection, and UDP sender.
    Decoupled via a producer-consumer background worker thread.
    """

    def __init__(
        self,
        sender: SmokeAlertSender,
        model_path: Union[str, Path] = DEFAULT_MODEL_PATH,
        conf_threshold: float = DEFAULT_CONF_THRESHOLD,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        on_frame_processed: Optional[FrameCallback] = None,
        on_alert_triggered: Optional[AlertTriggerCallback] = None,
    ):
        self.sender = sender
        self.model_path = Path(model_path)
        self.conf_threshold = conf_threshold
        self.cooldown_seconds = cooldown_seconds
        self.on_frame_processed = on_frame_processed
        self.on_alert_triggered = on_alert_triggered

        self.last_alert_time: float = 0.0
        self._next_img_id: int = 1000

        # Producer-consumer queue to decouple video frame rate from network transmission
        self.alert_queue: queue.Queue = queue.Queue()
        self.running: bool = False

        self._model = None
        self._sender_thread: Optional[threading.Thread] = None

    def load_model(self):
        """Loads YOLOv8s-P2 model once at startup."""
        if self._model is not None:
            return

        from ultralytics import YOLO

        if not self.model_path.exists():
            print(f"⚠️ Warning: Model file {self.model_path} not found. Running in simulation mode.")
            self._model = None
            return

        print(f"Loading YOLO model from: {self.model_path}")
        self._model = YOLO(str(self.model_path))
        print("YOLOv8s-P2 model loaded successfully.")

    def start(self):
        """Starts background sender worker thread."""
        if self.running:
            return
        self.running = True
        self.load_model()

        self._sender_thread = threading.Thread(target=self._sender_worker, daemon=True)
        self._sender_thread.start()

    def stop(self):
        """Stops bridge and worker thread."""
        self.running = False
        self.alert_queue.put(None)  # Sentinel to unblock worker
        if self._sender_thread and self._sender_thread.is_alive():
            self._sender_thread.join(timeout=1.0)

    def _sender_worker(self):
        """Consumer worker thread that performs network UDP transmission."""
        while self.running:
            try:
                item = self.alert_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if item is None:
                break

            img_id, frame_bytes, timestamp_str = item
            try:
                # State machine execution runs asynchronously here
                self.sender.send_image(img_id, frame_bytes, timestamp_str)
            except Exception as e:
                print(f"[ERROR] Sender worker failed for img_id={img_id}: {e}", flush=True)
            finally:
                self.alert_queue.task_done()

    def trigger_alert(
        self, frame: np.ndarray, detections: List[dict], timestamp_str: str, force: bool = False
    ) -> Optional[int]:
        """
        Evaluates cooldown and enqueues frame for sending.
        Returns img_id if alert is enqueued, or None if suppressed by cooldown.
        """
        now = time.monotonic()
        if not force and (now - self.last_alert_time < self.cooldown_seconds):
            # Still inside cooldown window: suppress duplicate frame alert
            return None

        self.last_alert_time = now
        self._next_img_id += 1
        img_id = self._next_img_id

        # Make copy of frame with visual overlay (timestamp and alert banner)
        alert_frame = frame.copy()
        h, w = alert_frame.shape[:2]

        # Overlay red warning header
        cv2.rectangle(alert_frame, (0, 0), (w, 40), (0, 0, 180), -1)
        cv2.putText(
            alert_frame,
            f"SMOKE DETECTED | EVENT #{img_id} | {timestamp_str}",
            (10, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )

        # Draw bounding boxes if provided
        for det in detections:
            x1, y1, x2, y2 = det.get("box", (0, 0, 0, 0))
            conf = det.get("confidence", 0.0)
            cv2.rectangle(alert_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            label = f"smoke {conf:.2f}"
            cv2.putText(
                alert_frame,
                label,
                (x1, max(y1 - 6, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                2,
            )

        # Encode to JPEG
        success, enc = cv2.imencode(".jpg", alert_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not success:
            return None

        jpeg_bytes = enc.tobytes()

        # Decouple: Push to queue and return immediately
        self.alert_queue.put((img_id, jpeg_bytes, timestamp_str))

        if self.on_alert_triggered:
            top_conf = max((d.get("confidence", 0.0) for d in detections), default=1.0)
            self.on_alert_triggered(img_id, timestamp_str, top_conf)

        return img_id

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[dict]]:
        """
        Runs YOLO inference on a single frame, checks confidence threshold,
        and triggers alert if smoke is detected and outside cooldown.
        """
        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        detections: List[dict] = []

        if self._model is not None:
            # Ultralytics inference
            results = self._model(frame, conf=self.conf_threshold, verbose=False)
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    conf = float(box.conf[0])
                    coords = [int(v) for v in box.xyxy[0]]
                    cls_id = int(box.cls[0])
                    detections.append(
                        {
                            "class_id": cls_id,
                            "confidence": conf,
                            "box": tuple(coords),
                        }
                    )

        annotated_frame = frame.copy()
        # Draw on local display frame
        for det in detections:
            x1, y1, x2, y2 = det["box"]
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                annotated_frame,
                f"smoke {det['confidence']:.2f}",
                (x1, max(y1 - 5, 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2,
            )

        # Timestamp on local preview
        cv2.putText(
            annotated_frame,
            timestamp_str,
            (10, annotated_frame.shape[0] - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
        )

        if detections:
            self.trigger_alert(frame, detections, timestamp_str)

        if self.on_frame_processed:
            self.on_frame_processed(annotated_frame, detections)

        return annotated_frame, detections

    def run_video_stream(self, source: Union[int, str] = 0):
        """Runs continuous video stream from webcam or video file."""
        self.start()
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"Could not open video source: {source}")
            return

        print(f"Video stream started on source: {source}. Press 'q' to stop.")
        try:
            while self.running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                annotated, _ = self.process_frame(frame)
                cv2.imshow("Smoke Alert Sender - Camera Feed", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SAP Detector Bridge CLI")
    parser.add_argument("--source", default="0", help="Webcam index (0) or path to video file")
    parser.add_argument("--host", default="127.0.0.1", help="Receiver IP")
    parser.add_argument("--port", type=int, default=5005, help="Receiver port")
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH), help="Model weights path")
    parser.add_argument("--conf", type=float, default=0.5, help="Confidence threshold")
    parser.add_argument("--cooldown", type=float, default=8.0, help="Cooldown in seconds")
    args = parser.parse_args()

    src: Union[int, str] = int(args.source) if args.source.isdigit() else args.source

    sender = SmokeAlertSender(target_host=args.host, target_port=args.port)
    bridge = DetectorBridge(
        sender=sender,
        model_path=args.model,
        conf_threshold=args.conf,
        cooldown_seconds=args.cooldown,
    )

    try:
        bridge.run_video_stream(source=src)
    finally:
        sender.close()
