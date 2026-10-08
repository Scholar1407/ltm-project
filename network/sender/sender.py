"""
Smoke Alert Protocol (SAP) - Sender Implementation
Course: Network Programming (LTM)
Specification: prompt/smoke-alert-protocol-spec.md Section 3 & Section 5
"""

from __future__ import annotations
import math
import socket
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# Support both relative and absolute imports
try:
    from ..shared.protocol import (
        HEADER_SIZE,
        MAX_PAYLOAD,
        Packet,
        PacketType,
        compute_crc32,
        log_drop_chunk,
        log_info,
        log_recv_ack,
        log_recv_nack,
        log_send_chunk,
        log_send_meta,
        pack_packet,
        split_into_chunks,
        unpack_nack_payload,
        unpack_packet,
    )
except (ImportError, ValueError):
    from network.shared.protocol import (
        HEADER_SIZE,
        MAX_PAYLOAD,
        Packet,
        PacketType,
        compute_crc32,
        log_drop_chunk,
        log_info,
        log_recv_ack,
        log_recv_nack,
        log_send_chunk,
        log_send_meta,
        pack_packet,
        split_into_chunks,
        unpack_nack_payload,
        unpack_packet,
    )


class SmokeAlertSender:
    """
    Sends detected smoking alert images over raw UDP using the Smoke Alert Protocol (SAP).
    Implements reliable chunked transmission with NACK-based selective retransmission.
    """

    def __init__(
        self,
        target_host: str = "127.0.0.1",
        target_port: int = 5005,
        wait_timeout: float = 0.5,  # 500ms wait window per spec
        max_retries: int = 5,
        sock: Optional[socket.socket] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.target_host = target_host
        self.target_port = target_port
        self.target_addr = (target_host, target_port)
        self.wait_timeout = wait_timeout
        self.max_retries = max_retries
        self.log_callback = log_callback

        self._own_socket = sock is None
        if sock is not None:
            self.sock = sock
        else:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(self.wait_timeout)

    def close(self):
        """Closes the underlying socket if owned by this sender."""
        if self._own_socket and self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def send_image(
        self,
        img_id: int,
        image_bytes: bytes,
        timestamp_str: str = "",
    ) -> bool:
        """
        Transmits an image via the SAP state machine.
        Returns True if ACK is received and verified, False if max retries exceeded.
        """
        if not image_bytes:
            raise ValueError("image_bytes cannot be empty")

        # 1. Compute whole-image CRC32 & split into chunks
        whole_crc = compute_crc32(image_bytes)
        chunks: List[bytes] = split_into_chunks(image_bytes, MAX_PAYLOAD)
        total_chunks = len(chunks)

        # Precompute chunk CRC32s
        chunk_crcs = [compute_crc32(c) for c in chunks]

        # 2. Send META packet (img_id, total chunk count, whole-image crc32)
        meta_payload = timestamp_str.encode("utf-8") if timestamp_str else b""
        meta_pkt = pack_packet(
            pkt_type=PacketType.META,
            img_id=img_id,
            seq=0,
            total=total_chunks,
            crc32=whole_crc,
            payload=meta_payload,
        )
        self.sock.sendto(meta_pkt, self.target_addr)
        log_send_meta(img_id, total_chunks, whole_crc, self.log_callback)

        # 3. Send all CHUNK packets in sequence (seq 0 .. total-1)
        for seq, chunk_data in enumerate(chunks):
            chunk_crc = chunk_crcs[seq]
            pkt = pack_packet(
                pkt_type=PacketType.CHUNK,
                img_id=img_id,
                seq=seq,
                total=total_chunks,
                crc32=chunk_crc,
                payload=chunk_data,
            )
            self.sock.sendto(pkt, self.target_addr)
            log_send_chunk(
                img_id, seq, total_chunks, len(chunk_data), chunk_crc, self.log_callback
            )

        # 4. State machine: wait for ACK / NACK with timeout window
        retries = 0
        retransmit_rounds = 0
        self.sock.settimeout(self.wait_timeout)

        while retries <= self.max_retries:
            try:
                raw_data, addr = self.sock.recvfrom(65535)
                packet = unpack_packet(raw_data)

                # Ignore packets for different image transfers
                if packet.img_id != img_id:
                    continue

                if packet.is_ack:
                    log_recv_ack(img_id, total_chunks, retransmit_rounds, self.log_callback)
                    return True

                elif packet.is_nack:
                    missing_seqs = unpack_nack_payload(packet.payload)
                    log_recv_nack(img_id, missing_seqs, self.log_callback)
                    retransmit_rounds += 1

                    # Resend only the missing chunks requested by receiver
                    for seq in missing_seqs:
                        if 0 <= seq < total_chunks:
                            chunk_data = chunks[seq]
                            chunk_crc = chunk_crcs[seq]
                            pkt = pack_packet(
                                pkt_type=PacketType.CHUNK,
                                img_id=img_id,
                                seq=seq,
                                total=total_chunks,
                                crc32=chunk_crc,
                                payload=chunk_data,
                            )
                            self.sock.sendto(pkt, self.target_addr)
                            log_send_chunk(
                                img_id,
                                seq,
                                total_chunks,
                                len(chunk_data),
                                chunk_crc,
                                self.log_callback,
                            )

                    # Reset timeout window after retransmitting
                    self.sock.settimeout(self.wait_timeout)

            except socket.timeout:
                retries += 1
                if retries > self.max_retries:
                    break

                # If wait window timed out without response (NACK or ACK lost in network),
                # re-send META to prod receiver state and re-open wait window.
                log_info(
                    f"Wait window expired for img_id={img_id} (retry {retries}/{self.max_retries}). Re-announcing META...",
                    self.log_callback,
                )
                self.sock.sendto(meta_pkt, self.target_addr)
                self.sock.settimeout(self.wait_timeout)

            except Exception as e:
                log_info(f"Unexpected error in sender loop: {e}", self.log_callback)

        log_info(
            f"[FAIL] img_id={img_id} — max retries ({self.max_retries}) exhausted without ACK. Abandoning transfer.",
            self.log_callback,
        )
        return False


if __name__ == "__main__":
    import argparse
    import cv2
    import numpy as np

    parser = argparse.ArgumentParser(description="SAP Smoke Alert Protocol Sender CLI")
    parser.add_argument("--host", default="127.0.0.1", help="Receiver IP address")
    parser.add_argument("--port", type=int, default=5005, help="Receiver UDP port")
    parser.add_argument("--image", default="", help="Path to test image file (optional)")
    args = parser.parse_args()

    # Create or load image
    if args.image and Path(args.image).exists():
        with open(args.image, "rb") as f:
            img_bytes = f.read()
    else:
        # Create synthetic test alert image with OpenCV
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        test_frame[:] = (30, 30, 30)
        cv2.putText(
            test_frame,
            "TEST SMOKING ALERT (SAP DEMO)",
            (50, 200),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
        )
        t_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            test_frame,
            f"TIMESTAMP: {t_str}",
            (50, 260),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )
        _, enc = cv2.imencode(".jpg", test_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        img_bytes = enc.tobytes()

    sender = SmokeAlertSender(target_host=args.host, target_port=args.port)
    test_id = int(time.time()) % 10000
    print(f"Starting test send: img_id={test_id}, payload_size={len(img_bytes)}B to {args.host}:{args.port}")
    success = sender.send_image(test_id, img_bytes, time.strftime("%Y-%m-%d %H:%M:%S"))
    sender.close()
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")
