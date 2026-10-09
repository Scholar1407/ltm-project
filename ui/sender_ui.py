"""
Smoke Alert Protocol (SAP) - Sender GUI
Course: Network Programming (LTM)
Specification: prompt/smoke-alert-protocol-spec.md Section 8 & Section 9

Tkinter modern dark-mode GUI for Sender Node:
- Video source selection (Webcam 0, Video File, or Manual Trigger)
- Real-time YOLOv8s-P2 smoke detection overlay
- Cooldown timer indicator
- Queue-decoupled UDP transmission over Smoke Alert Protocol
- Live structured packet log terminal (Section 5)
"""

from __future__ import annotations
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk

# Setup path imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from network.sender.sender import SmokeAlertSender
from network.sender.detector_bridge import DetectorBridge, DEFAULT_MODEL_PATH
from network.shared.protocol import MAX_PAYLOAD, parse_endpoints


class SenderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🚬 Smoke Alert System — Sender Node (YOLOv8s-P2 + UDP SAP)")
        self.geometry("1100x750")
        self.minsize(960, 680)
        self.configure(bg="#1e1e24")

        self.sender: Optional[SmokeAlertSender] = None
        self.bridge: Optional[DetectorBridge] = None

        self.cap: Optional[cv2.VideoCapture] = None
        self.is_streaming = False
        self.stream_thread: Optional[threading.Thread] = None
        self.current_source = "0"
        self.photo_image = None

        self._build_ui()
        self._init_network_and_bridge()

    def _build_ui(self):
        # Header banner
        header = tk.Frame(self, bg="#2b2d42", height=60, padx=16, pady=10)
        header.pack(fill=tk.X)

        title_lbl = tk.Label(
            header,
            text="🚬 SMOKE ALERT PROTOCOL (SAP) — SENDER NODE",
            font=("Segoe UI", 15, "bold"),
            fg="#edf2f4",
            bg="#2b2d42",
        )
        title_lbl.pack(side=tk.LEFT)

        subtitle_lbl = tk.Label(
            header,
            text="YOLOv8s-P2 | Event Cooldown: 8s | Raw UDP Socket",
            font=("Segoe UI", 10),
            fg="#8d99ae",
            bg="#2b2d42",
        )
        subtitle_lbl.pack(side=tk.RIGHT)

        # Main horizontal split
        main_paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#1e1e24", sashwidth=4)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel: Video & Controls
        left_panel = tk.Frame(main_paned, bg="#242632", padx=10, pady=10)
        main_paned.add(left_panel, minsize=560)

        # Configuration Box
        config_frame = tk.LabelFrame(
            left_panel,
            text="  Network & Detection Configuration  ",
            bg="#242632",
            fg="#edf2f4",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=8,
        )
        config_frame.pack(fill=tk.X, pady=(0, 10))

        # Config Row 1: Receiver Endpoints (host:port list)
        cfg_r1 = tk.Frame(config_frame, bg="#242632")
        cfg_r1.pack(fill=tk.X, pady=3)

        tk.Label(cfg_r1, text="Receivers (host:port):", bg="#242632", fg="#edf2f4", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.entry_receivers = tk.Entry(cfg_r1, width=28, font=("Segoe UI", 9), bg="#1e1e24", fg="#edf2f4", insertbackground="white")
        self.entry_receivers.insert(0, "127.0.0.1:5005")
        self.entry_receivers.pack(side=tk.LEFT, padx=(5, 8))

        self.btn_apply = tk.Button(
            cfg_r1,
            text="Apply",
            font=("Segoe UI", 8, "bold"),
            bg="#3a86ff",
            fg="white",
            relief=tk.FLAT,
            padx=6,
            command=self._apply_endpoints,
        )
        self.btn_apply.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(cfg_r1, text="Conf Thresh:", bg="#242632", fg="#edf2f4", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.conf_scale = tk.Scale(cfg_r1, from_=0.1, to=0.9, resolution=0.05, orient=tk.HORIZONTAL, bg="#242632", fg="#edf2f4", highlightthickness=0, length=80)
        self.conf_scale.set(0.50)
        self.conf_scale.pack(side=tk.LEFT, padx=5)

        # Video source & action buttons
        action_frame = tk.Frame(left_panel, bg="#242632")
        action_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_camera = tk.Button(
            action_frame,
            text="📹 Webcam",
            bg="#3a5a40",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            command=self._use_webcam,
        )
        self.btn_camera.pack(side=tk.LEFT, padx=3)

        self.btn_file = tk.Button(
            action_frame,
            text="📂 Open Video",
            bg="#4a4e69",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            command=self._choose_video_file,
        )
        self.btn_file.pack(side=tk.LEFT, padx=3)

        self.btn_stream = tk.Button(
            action_frame,
            text="▶ Start Stream",
            bg="#2a9d8f",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=12,
            command=self._toggle_stream,
        )
        self.btn_stream.pack(side=tk.LEFT, padx=5)

        self.btn_trigger = tk.Button(
            action_frame,
            text="🚨 Trigger Alert Frame",
            bg="#e63946",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            command=self._manual_trigger_alert,
        )
        self.btn_trigger.pack(side=tk.RIGHT, padx=3)

        # Video Canvas
        self.canvas = tk.Canvas(left_panel, bg="#0d0e15", highlightthickness=1, highlightbackground="#3d405b")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Video Status footer
        status_bar = tk.Frame(left_panel, bg="#1a1c24", height=28, padx=6)
        status_bar.pack(fill=tk.X, pady=(6, 0))

        self.lbl_status = tk.Label(status_bar, text="Status: Ready", bg="#1a1c24", fg="#a8dadc", font=("Segoe UI", 9))
        self.lbl_status.pack(side=tk.LEFT)

        self.lbl_cooldown = tk.Label(status_bar, text="Cooldown: Idle", bg="#1a1c24", fg="#f4a261", font=("Segoe UI", 9, "bold"))
        self.lbl_cooldown.pack(side=tk.RIGHT)

        # Right panel: Structured Logging Terminal
        right_panel = tk.Frame(main_paned, bg="#1a1c24", padx=10, pady=10)
        main_paned.add(right_panel, minsize=400)

        log_hdr = tk.Frame(right_panel, bg="#1a1c24")
        log_hdr.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            log_hdr,
            text="📜 LIVE NETWORK PACKET LOG",
            bg="#1a1c24",
            fg="#48cae4",
            font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT)

        btn_clear = tk.Button(
            log_hdr,
            text="Clear",
            font=("Segoe UI", 8),
            bg="#333533",
            fg="white",
            relief=tk.FLAT,
            command=self._clear_logs,
        )
        btn_clear.pack(side=tk.RIGHT)

        # Text widget for monospace logs
        self.log_text = tk.Text(
            right_panel,
            bg="#0c0d11",
            fg="#00f5d4",
            font=("Consolas", 9),
            wrap=tk.NONE,
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scroll_y = tk.Scrollbar(right_panel, command=self.log_text.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll_y.set)

    def _validate_and_parse_endpoints(self) -> Optional[List[Tuple[str, int]]]:
        """Validates host:port input string, returning list of (host, port) or None on error."""
        raw = self.entry_receivers.get().strip()
        if not raw:
            messagebox.showerror(
                "Validation Error",
                "Receiver endpoint list cannot be empty.\nExample: 127.0.0.1:5005 or 192.168.1.20:5005, 192.168.1.21:5005",
            )
            return None

        try:
            endpoints = parse_endpoints(raw, default_port=5005)
            return endpoints
        except ValueError as err:
            messagebox.showerror(
                "Validation Error",
                f"Invalid receiver endpoint:\n{err}\n\nFormat: host:port (e.g. 192.168.1.20:5005)",
            )
            return None

    def _init_network_and_bridge(self):
        """Initializes sender socket and bridge decoupling layer for all endpoints."""
        endpoints = self._validate_and_parse_endpoints()
        if not endpoints:
            endpoints = [("127.0.0.1", 5005)]

        if self.bridge:
            self.bridge.stop()
        if self.sender:
            self.sender.close()

        self.sender = SmokeAlertSender(
            receivers=endpoints,
            log_callback=self._append_log,
        )
        self.bridge = DetectorBridge(
            sender=self.sender,
            model_path=DEFAULT_MODEL_PATH,
            conf_threshold=self.conf_scale.get(),
            cooldown_seconds=8.0,
            on_alert_triggered=self._on_bridge_alert,
        )
        self.bridge.start()
        ep_strs = [f"{h}:{p}" for h, p in endpoints]
        self._append_log(f"[INIT] Sender initialized -> targeting {len(endpoints)} receiver(s): {', '.join(ep_strs)}")

    def _apply_endpoints(self):
        """Called when user clicks 'Apply' button to update receiver targets."""
        endpoints = self._validate_and_parse_endpoints()
        if not endpoints:
            return

        self._init_network_and_bridge()
        summary = "\n".join(f"• {h}:{p}" for h, p in endpoints)
        messagebox.showinfo("Config Updated", f"Active Target Receivers ({len(endpoints)}):\n{summary}")

    def _append_log(self, text: str):
        """Thread-safe log append to text widget."""
        def _insert():
            self.log_text.insert(tk.END, text + "\n")
            self.log_text.see(tk.END)
        self.after(0, _insert)

    def _clear_logs(self):
        self.log_text.delete("1.0", tk.END)

    def _on_bridge_alert(self, img_id: int, timestamp: str, conf: float):
        def _update():
            self.lbl_status.config(text=f"🚨 Alert Triggered: img_id={img_id} (conf={conf:.2f})")
            self._start_cooldown_indicator(8.0)
        self.after(0, _update)

    def _start_cooldown_indicator(self, seconds: float):
        start_t = time.monotonic()
        def _tick():
            elapsed = time.monotonic() - start_t
            remaining = seconds - elapsed
            if remaining > 0:
                self.lbl_cooldown.config(text=f"Cooldown: Active ({remaining:.1f}s)", fg="#e76f51")
                self.after(200, _tick)
            else:
                self.lbl_cooldown.config(text="Cooldown: Idle", fg="#2a9d8f")
        _tick()

    def _use_webcam(self):
        self.current_source = "0"
        self.lbl_status.config(text="Source set to: Webcam (0)")
        if self.is_streaming:
            self._stop_stream()
            self._start_stream()

    def _choose_video_file(self):
        path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")],
        )
        if path:
            self.current_source = path
            self.lbl_status.config(text=f"Source set to: {Path(path).name}")
            if self.is_streaming:
                self._stop_stream()
                self._start_stream()

    def _toggle_stream(self):
        if self.is_streaming:
            self._stop_stream()
        else:
            self._start_stream()

    def _start_stream(self):
        src = 0 if self.current_source == "0" else self.current_source
        self.cap = cv2.VideoCapture(src)
        if not self.cap.isOpened():
            messagebox.showerror("Error", f"Could not open video source: {self.current_source}")
            return

        self.is_streaming = True
        self.btn_stream.config(text="⏹ Stop Stream", bg="#e63946")
        self.lbl_status.config(text=f"Streaming: {self.current_source}")

        # Update bridge settings
        if self.bridge:
            self.bridge.conf_threshold = self.conf_scale.get()

        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.stream_thread.start()

    def _stop_stream(self):
        self.is_streaming = False
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
        self.btn_stream.config(text="▶ Start Stream", bg="#2a9d8f")
        self.lbl_status.config(text="Status: Stream stopped")

    def _stream_loop(self):
        while self.is_streaming and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                # Loop video if file
                if self.current_source != "0":
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    break

            # Process frame via YOLO detector bridge
            if self.bridge:
                annotated, _ = self.bridge.process_frame(frame)
            else:
                annotated = frame

            self._display_frame(annotated)
            time.sleep(0.03)  # ~30 fps

        self.after(0, self._stop_stream)

    def _display_frame(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        canvas_w = max(self.canvas.winfo_width(), 320)
        canvas_h = max(self.canvas.winfo_height(), 240)

        # Scale keeping aspect ratio
        scale = min(canvas_w / w, canvas_h / h)
        nw, nh = int(w * scale), int(h * scale)
        resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)

        # Convert to RGB PIL Image
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        im = Image.fromarray(rgb)
        photo = ImageTk.PhotoImage(image=im)

        def _update():
            self.photo_image = photo
            self.canvas.delete("all")
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=photo, anchor=tk.CENTER)

        self.after(0, _update)

    def _manual_trigger_alert(self):
        """Simulates immediate detection of a smoking event frame."""
        t_str = time.strftime("%Y-%m-%d %H:%M:%S")

        # Generate realistic smoking alert frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = (35, 35, 45)
        # Background gradient
        cv2.putText(frame, "BUILDING AREA B - SMOKING DETECTED", (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 255), 2)
        cv2.putText(frame, f"TIMESTAMP: {t_str}", (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
        cv2.putText(frame, "PROTOCOL: SAP (UDP RAW SOCKET)", (40, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

        # Add mock smoke bounding box
        detections = [{"class_id": 0, "confidence": 0.88, "box": (200, 120, 440, 360)}]

        if self.bridge:
            img_id = self.bridge.trigger_alert(frame, detections, t_str, force=True)
            self._display_frame(frame)
            self._append_log(f"[EVENT] Manual alert triggered: img_id={img_id}")

    def destroy(self):
        self._stop_stream()
        if self.bridge:
            self.bridge.stop()
        if self.sender:
            self.sender.close()
        super().destroy()


if __name__ == "__main__":
    app = SenderApp()
    app.mainloop()
