"""
Smoke Alert Protocol (SAP) - Headless Sender CLI
Course: Network Programming (LTM)
Specification: prompt/Lan-upgrade-prompt-2.md Task 4

Headless sender for plain terminals, VMs, WSL, and Android (via Termux):
- Sends an existing JPEG file through the SAP core and multi-receiver fan-out
- One socket per receiver, one independent worker per receiver
- No OpenCV, NumPy, PIL, or Ultralytics dependencies (standard library only)
"""

from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from network.sender.sender import SmokeAlertSender
from network.shared.protocol import parse_endpoints


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Headless Smoke Alert Protocol (SAP) Sender CLI"
    )
    parser.add_argument(
        "--to",
        action="append",
        dest="receivers",
        help="Receiver endpoint host:port (can be specified multiple times, e.g. --to 192.168.1.20:5005)",
    )
    parser.add_argument(
        "--send-file",
        required=True,
        help="Path to an existing JPEG alert image file to transmit",
    )
    parser.add_argument(
        "--img-id",
        type=int,
        default=None,
        help="Custom image event ID (default: timestamp-derived ID)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.5,
        help="ACK/NACK wait window timeout in seconds (default: 0.5s)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="Maximum retransmission attempts (default: 5)",
    )
    args = parser.parse_args(argv)

    # 1. Validate and load file
    file_path = Path(args.send_file)
    if not file_path.exists() or not file_path.is_file():
        print(f"[ERROR] File not found or not a valid file: {file_path}", file=sys.stderr)
        return 1

    try:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
    except Exception as e:
        print(f"[ERROR] Failed to read file {file_path}: {e}", file=sys.stderr)
        return 1

    if not image_bytes:
        print(f"[ERROR] File {file_path} is empty.", file=sys.stderr)
        return 1

    # 2. Parse destination endpoints
    endpoints_raw = args.receivers if args.receivers else ["127.0.0.1:5005"]
    try:
        endpoints = parse_endpoints(endpoints_raw, default_port=5005)
    except ValueError as e:
        print(f"[ERROR] Invalid target endpoints: {e}", file=sys.stderr)
        return 1

    # 3. Setup event ID and metadata
    img_id = args.img_id if args.img_id is not None else (int(time.time()) % 100000 + 1000)
    timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")

    print(f"Transmitting file: {file_path.name} ({len(image_bytes):,} B)")
    print(f"Target receivers: {', '.join(f'{h}:{p}' for h, p in endpoints)}")
    print(f"Event ID: #{img_id} | Timestamp: {timestamp_str}")

    sender = SmokeAlertSender(
        receivers=endpoints,
        wait_timeout=args.timeout,
        max_retries=args.retries,
    )

    try:
        success = sender.send_image(img_id, image_bytes, timestamp_str)
    finally:
        sender.close()

    print("\n--- Transfer Results ---")
    for endpoint, ok in sender.last_results.items():
        status = "✓ ACK RECEIVED" if ok else "✗ FAILED / TIMEOUT"
        print(f"  {endpoint[0]}:{endpoint[1]} -> {status}")

    if success:
        print("\n[SUCCESS] Alert delivery succeeded to at least one receiver.")
        return 0
    else:
        print("\n[FAILURE] Alert delivery failed to all configured receivers.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
