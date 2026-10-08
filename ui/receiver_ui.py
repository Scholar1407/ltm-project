"""
Smoke Alert Protocol (SAP) - Receiver GUI
Course: Network Programming (LTM)
Specification: prompt/smoke-alert-protocol-spec.md Section 8 & Section 4

Tkinter modern emergency monitoring dashboard for Receiver Node:
- Listens on UDP port for incoming SAP packets
- Reassembles chunked JPEG alert images
- Verifies per-chunk and end-to-end CRC32 integrity
- Visual emergency notification banner (red flashing)
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

from network.receiver.receiver import SmokeAlertReceiver


class ReceiverApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🚨 Building Emergency Monitoring Center — Receiver Node (UDP SAP)")
        self.geometry("1150x760")
        self.minsize(980, 700)
        self.configure(bg="#12131a")

        self.receiver: Optional[SmokeAlertReceiver] = None
        self.is_listening = False

        self.last_image_bytes: Optional[bytes] = None
        self.last_img_id: Optional[int] = None
        self.last_timestamp: str = ""
        self.photo_image = None
        self.alert_flash_state = False

        self._build_ui()
        self._start_receiver()

    def _build_ui(self):
        # 1. Header Banner
        header = tk.Frame(self, bg="#1c1d29", height=65, padx=16, pady=10)
        header.pack(fill=tk.X)

        title_lbl = tk.Label(
            header,
            text="🚨 BUILDING EMERGENCY MONITORING CENTER (SAP RECEIVER)",
            font=("Segoe UI", 15, "bold"),
            fg="#f72585",
            bg="#1c1d29",
        )
        title_lbl.pack(side=tk.LEFT)

        subtitle_lbl = tk.Label(
            header,
            text="Smoke Alert Protocol | Selective NACK Retransmission | End-to-End CRC32",
            font=("Segoe UI", 10),
            fg="#8d99ae",
            bg="#1c1d29",
        )
        subtitle_lbl.pack(side=tk.RIGHT)

        # 2. Emergency Status Banner
        self.banner_frame = tk.Frame(self, bg="#2d6a4f", height=42, padx=14, pady=6)
        self.banner_frame.pack(fill=tk.X)

        self.lbl_banner = tk.Label(
            self.banner_frame,
            text="🟢 ALL ZONES SECURED — LISTENING FOR ALERTS",
            font=("Segoe UI", 12, "bold"),
            fg="#d8f3dc",
            bg="#2d6a4f",
        )
        self.lbl_banner.pack(side=tk.LEFT)

        self.btn_ack = tk.Button(
            self.banner_frame,
            text="✓ Acknowledge & Reset",
            font=("Segoe UI", 9, "bold"),
            bg="#1b4332",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            command=self._reset_alert_state,
        )
        self.btn_ack.pack(side=tk.RIGHT)

        # 3. Main Paned Layout
        main_paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#12131a", sashwidth=4)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left Column: Image Canvas & Alert Metadata
        left_col = tk.Frame(main_paned, bg="#1a1c26", padx=12, pady=10)
        main_paned.add(left_col, minsize=560)

        # Config row
        cfg_frame = tk.Frame(left_col, bg="#1a1c26")
        cfg_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(cfg_frame, text="Listen Port:", bg="#1a1c26", fg="#edf2f4", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.entry_port = tk.Entry(cfg_frame, width=7, font=("Segoe UI", 9), bg="#12131a", fg="#edf2f4", insertbackground="white")
        self.entry_port.insert(0, "5005")
        self.entry_port.pack(side=tk.LEFT, padx=(5, 15))

        self.btn_listen = tk.Button(
            cfg_frame,
            text="Restart Receiver",
            bg="#4361ee",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            command=self._restart_receiver,
        )
        self.btn_listen.pack(side=tk.LEFT)

        self.btn_save_img = tk.Button(
            cfg_frame,
            text="💾 Save Image",
            bg="#3a0ca3",
            fg="white",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=10,
            command=self._save_current_image,
        )
        self.btn_save_img.pack(side=tk.RIGHT)

        # Alert Metadata Cards Box
        meta_box = tk.LabelFrame(
            left_col,
            text="  Latest Alert Information  ",
            bg="#1a1c26",
            fg="#72efdd",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=6,
        )
        meta_box.pack(fill=tk.X, pady=(0, 10))

        # 2x2 grid for metrics
        self.lbl_event_id = tk.Label(meta_box, text="Event ID: --", bg="#1a1c26", fg="#edf2f4", font=("Segoe UI", 10))
        self.lbl_event_id.grid(row=0, column=0, sticky="w", padx=10, pady=2)

        self.lbl_time = tk.Label(meta_box, text="Timestamp: --", bg="#1a1c26", fg="#edf2f4", font=("Segoe UI", 10))
        self.lbl_time.grid(row=0, column=1, sticky="w", padx=10, pady=2)

        self.lbl_integrity = tk.Label(meta_box, text="CRC32 Check: --", bg="#1a1c26", fg="#edf2f4", font=("Segoe UI", 10))
        self.lbl_integrity.grid(row=1, column=0, sticky="w", padx=10, pady=2)

        self.lbl_size = tk.Label(meta_box, text="Payload: --", bg="#1a1c26", fg="#edf2f4", font=("Segoe UI", 10))
        self.lbl_size.grid(row=1, column=1, sticky="w", padx=10, pady=2)

        # Received Image Canvas
        self.canvas = tk.Canvas(left_col, bg="#0b0c10", highlightthickness=1, highlightbackground="#3d405b")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Right Column: Monospace Live Network Packet Log
        right_col = tk.Frame(main_paned, bg="#161822", padx=10, pady=10)
        main_paned.add(right_col, minsize=420)

        log_hdr = tk.Frame(right_col, bg="#161822")
        log_hdr.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            log_hdr,
            text="📜 RECV PACKET STREAM (SAP SPEC SECTION 5)",
            bg="#161822",
            fg="#4cc9f0",
            font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT)

        btn_clear = tk.Button(
            log_hdr,
            text="Clear",
            font=("Segoe UI", 8),
            bg="#2b2d42",
            fg="white",
            relief=tk.FLAT,
            command=self._clear_logs,
        )
        btn_clear.pack(side=tk.RIGHT)

        self.log_text = tk.Text(
            right_col,
            bg="#0c0d12",
            fg="#70e000",
            font=("Consolas", 9),
            wrap=tk.NONE,
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scroll_y = tk.Scrollbar(right_col, command=self.log_text.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll_y.set)

    def _start_receiver(self):
        try:
            port = int(self.entry_port.get().strip())
        except ValueError:
            port = 5005

        if self.receiver:
            self.receiver.stop()

        self.receiver = SmokeAlertReceiver(
            listen_host="0.0.0.0",
            listen_port=port,
            inactivity_timeout=0.3,
            max_retries=5,
            on_image_received=self._on_image_arrived,
            log_callback=self._append_log,
        )
        self.receiver.start()
        self.is_listening = True
        self._append_log(f"[INIT] Receiver listening on UDP 0.0.0.0:{port}")

    def _restart_receiver(self):
        self._start_receiver()
        messagebox.showinfo("Receiver", f"Receiver restarted on port {self.entry_port.get().strip()}")

    def _append_log(self, text: str):
        def _insert():
            self.log_text.insert(tk.END, text + "\n")
            self.log_text.see(tk.END)
        self.after(0, _insert)

    def _clear_logs(self):
        self.log_text.delete("1.0", tk.END)

    def _on_image_arrived(self, img_id: int, image_bytes: bytes, timestamp_str: str):
        """Called automatically by SmokeAlertReceiver upon full CRC32-verified reassembly."""
        def _handle():
            self.last_image_bytes = image_bytes
            self.last_img_id = img_id
            self.last_timestamp = timestamp_str or time.strftime("%Y-%m-%d %H:%M:%S")

            # Update Metadata Cards
            self.lbl_event_id.config(text=f"Event ID: #{img_id}", fg="#ffd166")
            self.lbl_time.config(text=f"Timestamp: {self.last_timestamp}", fg="#ffd166")
            self.lbl_integrity.config(text="CRC32 Check: PASSED ✓ (100% Match)", fg="#06d6a0")
            self.lbl_size.config(text=f"Payload: {len(image_bytes):,} Bytes", fg="#72efdd")

            # Trigger Visual Alarm Banner
            self._trigger_visual_alarm()

            # Render image
            self._render_received_image(image_bytes)

        self.after(0, _handle)

    def _trigger_visual_alarm(self):
        self.banner_frame.config(bg="#d90429")
        self.lbl_banner.config(
            text=f"🚨 CRITICAL ALERT: SMOKE DETECTED IN BUILDING! (EVENT #{self.last_img_id})",
            bg="#d90429",
            fg="#ffffff",
        )
        self._flash_banner(count=6)

    def _flash_banner(self, count: int):
        if count <= 0:
            return
        current_bg = self.banner_frame.cget("bg")
        next_bg = "#ef233c" if current_bg == "#d90429" else "#d90429"
        self.banner_frame.config(bg=next_bg)
        self.lbl_banner.config(bg=next_bg)
        self.after(300, lambda: self._flash_banner(count - 1))

    def _reset_alert_state(self):
        self.banner_frame.config(bg="#2d6a4f")
        self.lbl_banner.config(
            text="🟢 ALL ZONES SECURED — LISTENING FOR ALERTS",
            bg="#2d6a4f",
            fg="#d8f3dc",
        )

    def _render_received_image(self, image_bytes: bytes):
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_bgr is None:
                return

            h, w = img_bgr.shape[:2]
            canvas_w = max(self.canvas.winfo_width(), 320)
            canvas_h = max(self.canvas.winfo_height(), 240)

            scale = min(canvas_w / w, canvas_h / h)
            nw, nh = int(w * scale), int(h * scale)
            resized = cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_AREA)

            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            im = Image.fromarray(rgb)
            photo = ImageTk.PhotoImage(image=im)

            self.photo_image = photo
            self.canvas.delete("all")
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=photo, anchor=tk.CENTER)
        except Exception as e:
            self._append_log(f"[ERROR] Failed to render image: {e}")

    def _save_current_image(self):
        if not self.last_image_bytes:
            messagebox.showwarning("Warning", "No image currently loaded.")
            return

        out_path = filedialog.asksaveasfilename(
            title="Save Alert Image",
            defaultextension=".jpg",
            filetypes=[("JPEG Image", "*.jpg"), ("All files", "*.*")],
            initialfile=f"smoke_alert_{self.last_img_id or 'snapshot'}.jpg",
        )
        if out_path:
            with open(out_path, "wb") as f:
                f.write(self.last_image_bytes)
            messagebox.showinfo("Saved", f"Alert image saved to:\n{out_path}")

    def destroy(self):
        if self.receiver:
            self.receiver.stop()
        super().destroy()


if __name__ == "__main__":
    app = ReceiverApp()
    app.mainloop()
