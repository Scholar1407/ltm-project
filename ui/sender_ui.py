"""
Smoke Alert Protocol (SAP) - Sender GUI
Course: Network Programming (LTM)
Specification: prompt/upgrade-discovery-fps-prompt.md Task A & Task B

Tkinter modern dark-mode GUI for Sender Node:
- Video source selection (Webcam 0, Video File, or Manual Trigger)
- Decoupled producer-consumer video pipeline (Thread A: capture+YOLO, Thread B: UI render)
- Real-time native FPS playback & display (FPS: XX)
- Auto-discovery of active LAN receivers (UDP port 5006) with live status indicators
- Merged fan-out delivery to discovered + manual receivers
- Event-based cooldown timer (8s)
- Live structured packet log terminal (Section 5)
"""

from __future__ import annotations
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple
import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk

# Setup path imports
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from network.sender.sender import SmokeAlertSender
from network.sender.detector_bridge import DetectorBridge, DEFAULT_MODEL_PATH
from network.sender.discovery import DiscoveryListener
from network.shared.protocol import MAX_PAYLOAD, parse_endpoints


class SenderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🚬 Smoke Alert System — Sender Node (YOLOv8s-P2 + UDP SAP)")
        self.geometry("1120x760")
        self.minsize(980, 680)
        self.configure(bg="#1e1e24")

        self.sender: Optional[SmokeAlertSender] = None
        self.bridge: Optional[DetectorBridge] = None
        self.discovery: Optional[DiscoveryListener] = None

        # Thread A & Thread B video streaming pipeline state
        self.is_streaming = False
        self.stream_thread: Optional[threading.Thread] = None
        self.stream_stop_event = threading.Event()
        self.frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self.current_source = "0"
        self.photo_image = None
        self.render_frame_count = 0
        self.last_fps_time = time.monotonic()

        self._build_ui()
        self._init_network_and_discovery()

    def _build_ui(self):
        # 1. Header banner
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
            text="Auto-Discovery (Port 5006) | Decoupled FPS Pipeline | Cooldown 8s",
            font=("Segoe UI", 10),
            fg="#8d99ae",
            bg="#2b2d42",
        )
        subtitle_lbl.pack(side=tk.RIGHT)

        # 2. Main horizontal split
        main_paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#1e1e24", sashwidth=4)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel: Video, Discovery, & Controls
        left_panel = tk.Frame(main_paned, bg="#242632", padx=10, pady=10)
        main_paned.add(left_panel, minsize=580)

        # Configuration Box
        config_frame = tk.LabelFrame(
            left_panel,
            text="  Network & Auto-Discovery Configuration  ",
            bg="#242632",
            fg="#edf2f4",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=8,
        )
        config_frame.pack(fill=tk.X, pady=(0, 10))

        # Config Row 1: Manual Receiver Endpoints & Conf Threshold
        cfg_r1 = tk.Frame(config_frame, bg="#242632")
        cfg_r1.pack(fill=tk.X, pady=2)

        tk.Label(cfg_r1, text="Manual Endpoints:", bg="#242632", fg="#edf2f4", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.entry_receivers = tk.Entry(cfg_r1, width=22, font=("Segoe UI", 9), bg="#1e1e24", fg="#edf2f4", insertbackground="white")
        self.entry_receivers.insert(0, "127.0.0.1:5005")
        self.entry_receivers.pack(side=tk.LEFT, padx=(5, 6))

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
        self.btn_apply.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(cfg_r1, text="Conf Thresh:", bg="#242632", fg="#edf2f4", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.conf_scale = tk.Scale(cfg_r1, from_=0.1, to=0.9, resolution=0.05, orient=tk.HORIZONTAL, bg="#242632", fg="#edf2f4", highlightthickness=0, length=80)
        self.conf_scale.set(0.50)
        self.conf_scale.pack(side=tk.LEFT, padx=4)

        # Config Row 2: Discovered Receivers Panel (Task B)
        disc_frame = tk.Frame(config_frame, bg="#242632")
        disc_frame.pack(fill=tk.X, pady=(6, 2))

        disc_header = tk.Frame(disc_frame, bg="#242632")
        disc_header.pack(fill=tk.X, pady=(0, 3))

        tk.Label(
            disc_header,
            text="Discovered Receivers (LAN Port 5006):",
            bg="#242632",
            fg="#4cc9f0",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT)

        self.lbl_disc_count = tk.Label(
            disc_header,
            text="(0 active)",
            bg="#242632",
            fg="#8d99ae",
            font=("Segoe UI", 9),
        )
        self.lbl_disc_count.pack(side=tk.LEFT, padx=6)

        self.btn_probe = tk.Button(
            disc_header,
            text="🔍 Probe Now",
            font=("Segoe UI", 8, "bold"),
            bg="#4361ee",
            fg="white",
            relief=tk.FLAT,
            padx=8,
            command=self._on_probe_now,
        )
        self.btn_probe.pack(side=tk.RIGHT)

        # Listbox for discovered receivers
        list_box_frame = tk.Frame(disc_frame, bg="#1a1c24")
        list_box_frame.pack(fill=tk.X)

        self.list_discovered = tk.Listbox(
            list_box_frame,
            height=3,
            bg="#161822",
            fg="#00f5d4",
            font=("Consolas", 9),
            relief=tk.FLAT,
            selectmode=tk.BROWSE,
            highlightthickness=0,
        )
        self.list_discovered.pack(side=tk.LEFT, fill=tk.X, expand=True)

        scroll_disc = tk.Scrollbar(list_box_frame, command=self.list_discovered.yview)
        scroll_disc.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_discovered.config(yscrollcommand=scroll_disc.set)

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

        # Video Status footer (includes FPS counter per Task A acceptance criteria)
        status_bar = tk.Frame(left_panel, bg="#1a1c24", height=28, padx=6)
        status_bar.pack(fill=tk.X, pady=(6, 0))

        self.lbl_status = tk.Label(status_bar, text="Status: Ready", bg="#1a1c24", fg="#a8dadc", font=("Segoe UI", 9))
        self.lbl_status.pack(side=tk.LEFT)

        self.lbl_fps = tk.Label(status_bar, text="FPS: --", bg="#1a1c24", fg="#4cc9f0", font=("Segoe UI", 9, "bold"))
        self.lbl_fps.pack(side=tk.LEFT, padx=16)

        self.lbl_cooldown = tk.Label(status_bar, text="Cooldown: Idle", bg="#1a1c24", fg="#f4a261", font=("Segoe UI", 9, "bold"))
        self.lbl_cooldown.pack(side=tk.RIGHT)

        # Right panel: Structured Logging Terminal
        right_panel = tk.Frame(main_paned, bg="#1a1c24", padx=10, pady=10)
        main_paned.add(right_panel, minsize=420)

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

    # -------------------------------------------------------------------------
    # Network, Discovery, and Sender Lifecycle
    # -------------------------------------------------------------------------

    def _get_merged_receivers(self) -> List[Tuple[str, int]]:
        """
        Merges discovered LAN receivers with manually entered endpoints (deduplicated).
        Preserves order: discovered peers first, followed by unique manual endpoints.
        """
        discovered = self.discovery.get_receivers() if self.discovery else []
        manual: List[Tuple[str, int]] = []
        raw_manual = self.entry_receivers.get().strip() if hasattr(self, "entry_receivers") else ""
        if raw_manual:
            try:
                manual = parse_endpoints(raw_manual, default_port=5005)
            except Exception:
                pass

        merged: List[Tuple[str, int]] = []
        seen = set()
        for ep in discovered + manual:
            if ep not in seen:
                seen.add(ep)
                merged.append(ep)
        return merged

    def _sync_receivers_to_sender(self):
        """Updates sender's active receiver endpoints list."""
        if self.sender:
            merged = self._get_merged_receivers()
            self.sender.receivers = merged

    def _init_network_and_discovery(self):
        """Initializes DiscoveryListener, SmokeAlertSender, and DetectorBridge."""
        # 1. Start Auto-Discovery listener
        if self.discovery is None:
            self.discovery = DiscoveryListener(log_callback=self._append_log)
            self.discovery.start()

        # 2. Setup Sender & Bridge
        merged = self._get_merged_receivers()
        if not merged:
            merged = [("127.0.0.1", 5005)]

        if self.bridge:
            self.bridge.stop()
        if self.sender:
            self.sender.close()

        self.sender = SmokeAlertSender(
            receivers=merged,
            log_callback=self._append_log,
        )

        # Hook sender.send_image to validate non-empty receivers before sending
        original_send_image = self.sender.send_image

        def validated_send_image(img_id: int, image_bytes: bytes, timestamp_str: str = "") -> bool:
            active_eps = self._get_merged_receivers()
            if not active_eps:
                self.after(0, lambda: self._show_no_receivers_warning(img_id))
                return False
            self.sender.receivers = active_eps
            return original_send_image(img_id, image_bytes, timestamp_str)

        self.sender.send_image = validated_send_image

        self.bridge = DetectorBridge(
            sender=self.sender,
            model_path=DEFAULT_MODEL_PATH,
            conf_threshold=self.conf_scale.get(),
            cooldown_seconds=8.0,
            on_alert_triggered=self._on_bridge_alert,
        )
        self.bridge.start()

        self._append_log("[INIT] Sender initialized with auto-discovery on UDP port 5006.")
        self._refresh_discovery()

    def _show_no_receivers_warning(self, img_id: int):
        self.lbl_status.config(text=f"⚠️ Alert #{img_id} NOT sent: No receivers!")
        self._append_log(f"[WARN] Alert #{img_id} suppressed: Zero active discovered or manual receiver endpoints.")
        messagebox.showwarning(
            "No Receivers Configured",
            f"Alert #{img_id} was triggered, but NO active receivers were found!\n\n"
            "• Auto-discovery found no SAP receivers on port 5006.\n"
            "• Manual receiver endpoint field is empty or invalid.\n\n"
            "Alert frame was not transmitted.",
        )

    def _refresh_discovery(self):
        """Periodic background refresh (every 2s) of discovered peers UI."""
        peers = self.discovery.get_discovered_peers() if self.discovery else []
        active_count = sum(1 for p in peers if p["is_active"])

        self.lbl_disc_count.config(
            text=f"({active_count} active)",
            fg="#2a9d8f" if active_count > 0 else "#8d99ae",
        )

        self.list_discovered.delete(0, tk.END)
        if not peers:
            self.list_discovered.insert(tk.END, "  ○ No receivers discovered on LAN yet (listening on 5006...)")
        else:
            for p in peers:
                dot = "🟢" if p["is_active"] else "⚪"
                status_str = f"seen {p['age']:.1f}s ago" if p["is_active"] else f"stale: {p['age']:.1f}s ago"
                self.list_discovered.insert(tk.END, f"  {dot} {p['host']}:{p['port']} ({status_str})")

        self._sync_receivers_to_sender()
        self.after(2000, self._refresh_discovery)

    def _on_probe_now(self):
        """Immediately broadcasts a PROBE packet to query receivers on LAN."""
        if self.discovery:
            self.discovery.probe()
            self._append_log("[DISCOVERY] Broadcasted PROBE on port 5006...")
            self.after(350, self._refresh_discovery)

    def _apply_endpoints(self):
        """Applies manual endpoint changes."""
        raw = self.entry_receivers.get().strip()
        if raw:
            try:
                parsed = parse_endpoints(raw, default_port=5005)
                self._sync_receivers_to_sender()
                summary = "\n".join(f"• {h}:{p}" for h, p in parsed)
                messagebox.showinfo("Manual Endpoints Applied", f"Manual Receivers Configured:\n{summary}")
            except ValueError as err:
                messagebox.showerror("Invalid Endpoint", f"Could not parse manual endpoints:\n{err}")
        else:
            self._sync_receivers_to_sender()
            messagebox.showinfo("Manual Endpoints", "Manual endpoints cleared. Relying exclusively on Auto-Discovery.")

    def _append_log(self, text: str):
        """Thread-safe log append to text widget."""
        def _insert():
            try:
                if self.winfo_exists():
                    self.log_text.insert(tk.END, text + "\n")
                    self.log_text.see(tk.END)
            except Exception:
                pass
        try:
            if self.winfo_exists():
                self.after(0, _insert)
        except Exception:
            pass

    def _clear_logs(self):
        self.log_text.delete("1.0", tk.END)

    def _on_bridge_alert(self, img_id: int, timestamp: str, conf: float):
        def _update():
            self.lbl_status.config(text=f"🚨 Alert Triggered: #{img_id} (conf={conf:.2f})")
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

    # -------------------------------------------------------------------------
    # Task A: Decoupled Video Streaming Pipeline (Thread A & Thread B)
    # -------------------------------------------------------------------------

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
        src: Union[int, str] = 0 if self.current_source == "0" else self.current_source

        # Test video source can open
        test_cap = cv2.VideoCapture(src)
        if not test_cap.isOpened():
            messagebox.showerror("Error", f"Could not open video source: {self.current_source}")
            test_cap.release()
            return
        test_cap.release()

        self.is_streaming = True
        self.stream_stop_event.clear()
        self.render_frame_count = 0
        self.last_fps_time = time.monotonic()

        # Drain frame queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

        self.btn_stream.config(text="⏹ Stop Stream", bg="#e63946")
        self.lbl_status.config(text=f"Streaming: {Path(str(self.current_source)).name}")
        self.lbl_fps.config(text="FPS: 0")

        if self.bridge:
            self.bridge.conf_threshold = self.conf_scale.get()

        # Thread A: Background capture + YOLO inference (daemon=True, no UI calls)
        self.stream_thread = threading.Thread(
            target=self._capture_and_infer_worker,
            args=(src,),
            daemon=True,
        )
        self.stream_thread.start()

        # Thread B: UI render loop (~60Hz poll on Tkinter main thread)
        self.after(16, self._render_loop)

    def _stop_stream(self):
        """Cleanly stops the video stream and joins Thread A within 2 seconds."""
        if not self.is_streaming and not (self.stream_thread and self.stream_thread.is_alive()):
            return

        self.is_streaming = False
        self.stream_stop_event.set()

        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=2.0)
        self.stream_thread = None

        self.btn_stream.config(text="▶ Start Stream", bg="#2a9d8f")
        self.lbl_status.config(text="Status: Stream stopped")
        self.lbl_fps.config(text="FPS: --")

    def _capture_and_infer_worker(self, src):
        """
        Thread A: capture + YOLO inference in background.
        CRITICAL: Never calls any Tkinter widget method.
        Pushes annotated frames into maxsize=1 frame_queue with evict-on-full.
        Always releases cap in finally block.
        """
        cap = cv2.VideoCapture(src)
        try:
            if not cap.isOpened():
                return

            # Native FPS pacing for video files
            native_fps = cap.get(cv2.CAP_PROP_FPS)
            frame_delay = (1.0 / native_fps) if (native_fps and native_fps > 0 and str(src) != "0") else 0.0

            while not self.stream_stop_event.is_set():
                t0 = time.monotonic()
                ret, frame = cap.read()
                if not ret:
                    if str(src) != "0":
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    else:
                        break

                if self.bridge:
                    annotated, detections = self.bridge.process_frame(frame)
                else:
                    annotated, detections = frame, []

                # Put latest frame into maxsize=1 queue; evict stale frame if queue full
                try:
                    self.frame_queue.put_nowait(annotated)
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self.frame_queue.put_nowait(annotated)
                    except queue.Full:
                        pass

                # Pace video files to native framerate so they do not outrun video speed
                if frame_delay > 0:
                    elapsed = time.monotonic() - t0
                    sleep_time = frame_delay - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

        finally:
            try:
                cap.release()
            except Exception:
                pass
            # Cleanly signal UI if stream exited on its own (e.g. EOF)
            if not self.stream_stop_event.is_set():
                self.after(0, self._stop_stream)

    def _render_loop(self):
        """
        Thread B: UI render loop on main thread.
        Pulls newest frame from queue and updates Tkinter canvas.
        Measures and displays real-time FPS counter.
        """
        if not self.is_streaming:
            return

        try:
            frame = self.frame_queue.get_nowait()
            self._render_canvas_frame(frame)
            self.render_frame_count += 1

            now = time.monotonic()
            elapsed = now - self.last_fps_time
            if elapsed >= 0.5:
                fps = self.render_frame_count / elapsed
                self.lbl_fps.config(text=f"FPS: {fps:.0f}")
                self.render_frame_count = 0
                self.last_fps_time = now
        except queue.Empty:
            pass

        self.after(16, self._render_loop)

    def _render_canvas_frame(self, frame: np.ndarray):
        """Renders frame on canvas keeping aspect ratio (runs on Tkinter main thread)."""
        h, w = frame.shape[:2]
        canvas_w = max(self.canvas.winfo_width(), 320)
        canvas_h = max(self.canvas.winfo_height(), 240)

        scale = min(canvas_w / w, canvas_h / h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)

        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        im = Image.fromarray(rgb)
        photo = ImageTk.PhotoImage(image=im)

        self.photo_image = photo
        self.canvas.delete("all")
        self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=photo, anchor=tk.CENTER)

    def _manual_trigger_alert(self):
        """Simulates immediate detection of a smoking event frame."""
        merged = self._get_merged_receivers()
        if not merged:
            self._show_no_receivers_warning(9999)
            return

        t_str = time.strftime("%Y-%m-%d %H:%M:%S")

        # Generate realistic smoking alert frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = (35, 35, 45)
        cv2.putText(frame, "BUILDING AREA B - SMOKING DETECTED", (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 255), 2)
        cv2.putText(frame, f"TIMESTAMP: {t_str}", (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
        cv2.putText(frame, "PROTOCOL: SAP (UDP RAW SOCKET)", (40, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

        detections = [{"class_id": 0, "confidence": 0.88, "box": (200, 120, 440, 360)}]

        if self.bridge:
            img_id = self.bridge.trigger_alert(frame, detections, t_str, force=True)
            self._render_canvas_frame(frame)
            self._append_log(f"[EVENT] Manual alert triggered: img_id={img_id} to {len(merged)} receiver(s)")

    def destroy(self):
        self._stop_stream()
        if self.discovery:
            self.discovery.stop()
        if self.bridge:
            self.bridge.stop()
        if self.sender:
            self.sender.close()
        super().destroy()


if __name__ == "__main__":
    app = SenderApp()
    app.mainloop()
