"""
Smoke Alert Protocol (SAP) - Headless Receiver CLI
Course: Network Programming (LTM)
Specification: prompt/Lan-upgrade-prompt-2.md Task 4

Headless receiver for servers, VMs, WSL, and Android (via Termux):
- Listens on UDP port for incoming SAP packets
- Reassembles chunked JPEG alert images with CRC32 verification
- Saves each reassembled JPEG as received/<timestamp>_<sender>_<img_id>.jpg
- Supports --notify-cmd with {path}, {img_id}, {sender} placeholders
- Zero external dependencies (standard library only)
"""

from __future__ import annotations
import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from network.receiver.receiver import SmokeAlertReceiver


def sanitize_filename_component(name: str) -> str:
    """Replaces characters invalid in filenames across Windows/Linux/Android."""
    return name.replace(":", "_").replace("/", "_").replace("\\", "_")


def build_transfer_callback(out_dir: Path, notify_cmd: Optional[str] = None):
    out_dir.mkdir(parents=True, exist_ok=True)

    def on_transfer_complete(
        sender_addr: Tuple[str, int],
        img_id: int,
        image_bytes: bytes,
        stats: Dict[str, Any],
    ):
        t_stamp = time.strftime("%Y%m%d_%H%M%S")
        sender_clean = sanitize_filename_component(f"{sender_addr[0]}_{sender_addr[1]}")
        filename = f"{t_stamp}_{sender_clean}_{img_id}.jpg"
        file_path = out_dir / filename

        with open(file_path, "wb") as f:
            f.write(image_bytes)

        sender_str = f"{sender_addr[0]}:{sender_addr[1]}"
        print(
            f"[SAVED] Alert #{img_id} from {sender_str} ({len(image_bytes)} B) -> {file_path}",
            flush=True,
        )

        if notify_cmd:
            try:
                tokens = shlex.split(notify_cmd)
                argv = [
                    token.replace("{path}", str(file_path.resolve()))
                         .replace("{img_id}", str(img_id))
                         .replace("{sender}", sender_str)
                         .replace("{timestamp}", str(stats.get("timestamp", "")))
                    for token in tokens
                ]
                subprocess.Popen(argv)
            except Exception as e:
                print(f"[ERROR] Failed to execute notify command: {e}", file=sys.stderr, flush=True)

    return on_transfer_complete


def main():
    parser = argparse.ArgumentParser(
        description="Headless Smoke Alert Protocol (SAP) Receiver CLI"
    )
    parser.add_argument("--bind", default="0.0.0.0", help="Bind IP address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5005, help="Bind UDP port (default: 5005)")
    parser.add_argument("--out", default="received", help="Directory to save reassembled JPEGs")
    parser.add_argument(
        "--notify-cmd",
        default=None,
        help="Command template with {path}, {img_id}, {sender} placeholders (e.g. for termux-notification)",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    callback = build_transfer_callback(out_path, args.notify_cmd)

    receiver = SmokeAlertReceiver(
        listen_host=args.bind,
        listen_port=args.port,
        on_transfer_complete=callback,
    )

    receiver.start()
    print(f"Receiver CLI running on {args.bind}:{args.port} (output dir: {out_path}). Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping receiver...")
        receiver.stop()


if __name__ == "__main__":
    main()
